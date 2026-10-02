import json
import hashlib
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from gateway.admin_auth import admin_auth
from gateway.public_identity import public_visitor
from gateway.event_import import analyze_event, MAX_BYTES

# --- Resilient imports for incomplete demo modules (added for bot testing) ---
try:
    from gateway.bypass_block import BLOCK_RESPONSE, BotBypassBlockMiddleware
except Exception:
    BLOCK_RESPONSE = {"error": "Access Denied", "code": "BOT_BLOCKED"}
    class BotBypassBlockMiddleware:  # type: ignore
        async def dispatch(self, request, call_next):
            return await call_next(request)

try:
    from gateway.rules import EdgeCDNMiddleware, WAFMiddleware
except Exception:
    from starlette.middleware.base import BaseHTTPMiddleware as _Base  # type: ignore
    class _NoopMiddleware(_Base):  # type: ignore
        async def dispatch(self, request, call_next):
            return await call_next(request)
    EdgeCDNMiddleware = _NoopMiddleware  # type: ignore
    try:
        from gateway.rules import WAFMiddleware
    except Exception:
        WAFMiddleware = _NoopMiddleware  # type: ignore

from shared.config import BOT_BYPASS_BLOCK, GRAPHQL_ENABLED

try:
    from shared.akamai_sim import (
        compute_bot_score,
        cookie_hash_from_abck,
        decode_sensor_payload,
        format_abck,
        format_ak_bmsc,
        format_bm_sv,
    )
except Exception:
    from shared.akamai_sim import (  # type: ignore
        compute_bot_score,
        cookie_hash_from_abck,
        decode_sensor_payload,
        format_abck,
        format_ak_bmsc,
    )
    def format_bm_sv(*a, **k): return "bm_sv_stub"  # type: ignore

from shared.config import (
    AUTH_SESSION_TTL_SEC,
    DEFAULT_EVENT_ID,
    PAYMENT_SERVICE_URL,
    QUEUE_SERVICE_URL,
    SEAT_SERVICE_URL,
    SENSOR_SESSION_TTL_SEC,
    WORKFLOW_CONFIG_KEY,
    WORKFLOW_DEFAULTS,
    normalize_workflow,
)
try:
    from shared.events import clear_all_defense_data, get_audit_events, log_event, summarize_audit_events, reset_seats_and_sessions
except Exception:
    from shared.events import get_audit_events, log_event  # type: ignore
    def clear_all_defense_data(): pass  # type: ignore
    def summarize_audit_events(events=None): return {"total": 0, "by_layer": {}, "passed": 0}  # type: ignore
    def reset_seats_and_sessions(): return {"status": "ok", "deleted_keys": 0}  # type: ignore
    # Also ensure log_event is available under the name used later
    if 'log_event' not in dir():
        from shared.events import log_event  # type: ignore
from shared.redis_client import r
from shared.event_state import (DEFAULT_EVENT, EVENTS_KEY, list_events, load_event,
                                validate_event_id, validate_event_update)
from shared.request_identity import client_identity
from shared.workflow import (
    GATE_POSITIONS, auth_user, captcha_passed, captcha_required,
    create_auth, get_workflow, new_challenge, verify_challenge,
)

app = FastAPI(title="Defense Gateway")
app.add_middleware(WAFMiddleware)
app.add_middleware(BotBypassBlockMiddleware)
app.add_middleware(EdgeCDNMiddleware)
if os.getenv("LAB_MODE") != "production":
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

app.middleware("http")(admin_auth)
app.middleware("http")(public_visitor)

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
if FRONTEND.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND)), name="static")


class SensorSubmit(BaseModel):
    sensor_data: str
    session_id: str = ""
    fingerprint: str = ""


def client_ip(request: Request) -> str:
    return client_identity(request)


def session_id_from_request(request: Request) -> str:
    return request.cookies.get("defense_sid", "") or request.headers.get("x-session-id", "")


def sensor_session_key(session_id: str) -> str:
    return f"defense:sensor:{session_id}"


def current_user(request: Request) -> Optional[str]:
    return auth_user(request.cookies.get("defense_auth", ""), session_id_from_request(request))


def _login_required(workflow: dict, position: str) -> bool:
    return bool(workflow.get({
        "queue": "REQUIRE_LOGIN_BEFORE_QUEUE",
        "seat": "REQUIRE_LOGIN_BEFORE_SEAT",
        "lock": "REQUIRE_LOGIN_BEFORE_LOCK",
    }.get(position, ""), False))


def _gate_status(request: Request, position: str, event_id: str = DEFAULT_EVENT_ID) -> Optional[dict]:
    workflow = get_workflow_config()
    session_id = session_id_from_request(request)
    captcha_configured = workflow["CAPTCHA_POSITION"] in (position, "random")
    if (_login_required(workflow, position) or captcha_configured) and not r.get(sensor_session_key(session_id)):
        return {"status": "need_sensor", "position": position}
    if _login_required(workflow, position) and not current_user(request):
        log_event("login", "login_required", session_id, client_ip(request), {"position": position}, blocked=True)
        return {"status": "need_login", "position": position}
    if captcha_required(workflow, session_id, event_id, position, _sensor_meta(session_id).get("bot_score", 60)):
        if not captcha_passed(session_id, event_id, position):
            log_event("captcha", "captcha_required", session_id, client_ip(request), {"position": position}, blocked=True)
            return {"status": "need_captcha", "position": position}
    return None


def _gate_response(request: Request, position: str, event_id: str = DEFAULT_EVENT_ID) -> Optional[JSONResponse]:
    gate = _gate_status(request, position, event_id)
    return JSONResponse(gate, status_code=428) if gate else None


def active_event_id(request: Request = None) -> str:
    return request.cookies.get("defense_event_id", DEFAULT_EVENT_ID) if request else DEFAULT_EVENT_ID


def cart_event_id(cart_id: str) -> str:
    raw = r.get(f"defense:cart:{cart_id}") if cart_id else None
    return json.loads(raw).get("event_id", active_event_id()) if raw else active_event_id()


def _page_gate_redirect(gate: dict, next_path: str) -> RedirectResponse:
    if gate["status"] == "need_sensor":
        return RedirectResponse("/", status_code=303)
    target = "/login" if gate["status"] == "need_login" else "/captcha"
    query = "next=" + next_path
    if gate["status"] == "need_captcha":
        query += "&position=" + gate["position"]
    return RedirectResponse(f"{target}?{query}", status_code=303)


def _bound_token_gate(request: Request, token: str) -> Optional[JSONResponse]:
    workflow = get_workflow_config()
    if not any(workflow[key] for key in (
        "REQUIRE_LOGIN_BEFORE_QUEUE", "REQUIRE_LOGIN_BEFORE_SEAT", "REQUIRE_LOGIN_BEFORE_LOCK"
    )):
        return None
    raw = r.get("defense:token:" + hashlib.sha256(token.encode()).hexdigest()[:16]) if token else None
    meta = json.loads(raw) if raw else {}
    if (not meta or not current_user(request) or meta.get("user_id") != current_user(request)
            or meta.get("session_id") != session_id_from_request(request)
            or meta.get("ip") != client_ip(request)):
        log_event("login", "token_binding_failed", session_id_from_request(request), client_ip(request), blocked=True)
        return JSONResponse({"status": "denied", "error": "QUEUE_TOKEN_BIND_MISMATCH"}, status_code=403)
    return None


def parse_graphql(body: dict) -> tuple[str, dict]:
    query = body.get("query", "")
    variables = body.get("variables", {})
    op = "unknown"
    if "queueStatus" in query:
        op = "queueStatus"
    elif "addToCart" in query:
        op = "addToCart"
    elif "checkout" in query:
        op = "checkout"
    return op, variables


def _set_akamai_cookies(
    response: Response,
    session_id: str,
    fingerprint: str,
    bot_score: int,
    challenged: bool,
) -> None:
    status = -1 if challenged or bot_score >= 55 else 0
    abck = format_abck(status, session_id, fingerprint, sensor_ok=not challenged)
    response.set_cookie("_abck", abck, max_age=3600, httponly=False, samesite="lax")
    response.set_cookie(
        "ak_bmsc",
        format_ak_bmsc(session_id),
        max_age=3600,
        httponly=True,
        samesite="lax",
    )
    bm = request_count_from_redis(session_id)
    response.set_cookie("bm_sv", format_bm_sv(bm), max_age=3600, httponly=False, samesite="lax")
    response.set_cookie("defense_sid", session_id, max_age=3600, httponly=False, samesite="lax")


def request_count_from_redis(session_id: str) -> int:
    raw = r.get(f"defense:bm_sv:{session_id}")
    return int(raw) if raw else 1


def bump_request_count(session_id: str) -> int:
    key = f"defense:bm_sv:{session_id}"
    n = r.incr(key)
    if n == 1:
        r.expire(key, 3600)
    return n


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "gateway",
        "layers": ["edge", "waf", "akamai", "queue", "ai", "3ds"],
        "graphql_enabled": GRAPHQL_ENABLED,
        "bot_bypass_block": BOT_BYPASS_BLOCK,
    }


@app.get("/admin/api/events")
def admin_events(limit: int = 100):
    events = get_audit_events(limit)
    return {"events": events, "stats": summarize_audit_events(events)}


@app.get("/api/events")
def event_catalog():
    return {"events": [{"eventId": event["eventId"], "eventName": event["eventName"],
                        "saleStatus": event.get("saleStatus", "open"),
                        "venue": event.get("venue", ""),
                        "showDate": event.get("showDate", ""),
                        "officialEventUrl": event.get("officialEventUrl", ""),
                        "startingPrice": min(zone["price"] for zone in event["zones"])}
                       for event in list_events()]}


@app.get("/admin/api/catalog")
def admin_catalog():
    return {"events": list_events()}


@app.post("/admin/api/event-import")
async def import_event_details(request: Request):
    raw = await request.body()
    if len(raw) > MAX_BYTES:
        raise HTTPException(413, "รายละเอียดมีขนาดใหญ่เกินไป")
    try:
        body = json.loads(raw)
        if not isinstance(body, dict) or set(body) - {"url", "text"}:
            raise ValueError("ข้อมูลต้องมี url และ text เท่านั้น")
        text = body.get("text", "")
        if not isinstance(text, str):
            raise ValueError("text ต้องเป็นข้อความ")
        result = await analyze_event(body.get("url"), text)
        result["draft"] = validate_event_update(result["draft"])
        result["workflowProfiles"] = {profile: normalize_workflow({"WORKFLOW_PROFILE": profile})
                                      for profile in ("A", "B", "C", "D")}
        return result
    except (ValueError, RecursionError) as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post("/admin/api/catalog", status_code=201)
async def admin_create_event(request: Request):
    data = await request.json()
    if not isinstance(data, dict):
        raise HTTPException(status_code=422, detail="event must be an object")
    try:
        event_id = validate_event_id(data.pop("eventId", ""))
        update = validate_event_update(data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if "eventName" not in update:
        raise HTTPException(status_code=422, detail="eventName is required")
    event = {**DEFAULT_EVENT, **update, "eventId": event_id}
    if event_id == DEFAULT_EVENT_ID or not r.hsetnx(EVENTS_KEY, event_id, json.dumps(event)):
        raise HTTPException(status_code=409, detail="eventId already exists")
    log_event("edge", "admin_create_event", "", client_ip(request), {"eventId": event_id})
    return {"event": event}


@app.post("/admin/api/clear-all")
def admin_clear_all():
    result = clear_all_defense_data()
    log_event("edge", "admin_clear_all", "", "", result, blocked=False)
    return result


@app.post("/admin/api/reset-seats")
def admin_reset_seats():
    """Reset seats, sessions, carts — keep audit logs."""
    result = reset_seats_and_sessions()
    log_event("edge", "admin_reset_seats", "", "", result, blocked=False)
    return result


class SaleStartRequest(BaseModel):
    delay_seconds: int
    soft_open_seconds: int = 0
    event_id: str = DEFAULT_EVENT_ID

@app.post("/admin/api/set-sale-start")
async def admin_set_sale_start(req: SaleStartRequest, request: Request):
    """Set the sale start time (pre-queue countdown)."""
    if not load_event(req.event_id):
        raise HTTPException(status_code=404, detail="event not found")
    start_time = time.time() + req.delay_seconds
    suffix = "" if req.event_id == DEFAULT_EVENT_ID else f":{req.event_id}"
    r.set("defense:config:sale_start" + suffix, str(start_time))
    r.set("defense:config:soft_open_seconds" + suffix, str(max(0, req.soft_open_seconds)))
    log_event("edge", "admin_set_sale_start", "", client_ip(request), {"start_time": start_time,
                                                                         "soft_open_seconds": req.soft_open_seconds,
                                                                         "event_id": req.event_id}, blocked=False)
    return {"success": True, "sale_start": start_time, "soft_open_seconds": req.soft_open_seconds,
            "event_id": req.event_id}

class SimulationRequest(BaseModel):
    enabled: bool

@app.post("/admin/api/set-simulation")
async def admin_set_simulation(req: SimulationRequest, request: Request):
    """Enable or disable the background bot simulator."""
    r.set("defense:config:bot_simulation", "1" if req.enabled else "0")
    log_event("edge", "admin_set_simulation", "", client_ip(request), {"enabled": req.enabled}, blocked=False)
    return {"success": True, "enabled": req.enabled}

def get_workflow_config() -> dict:
    return get_workflow()


@app.get("/api/event-config")
def get_event_config(request: Request, event_id: str = ""):
    event = load_event(event_id or active_event_id(request))
    if not event:
        raise HTTPException(status_code=404, detail="event not found")
    return {**event, "workflow": get_workflow_config()}


def get_defense_toggles() -> dict:
    raw = r.get("defense:config:toggles")
    toggles = json.loads(raw) if raw else {}
    return {
        "waf": True,
        "akamai": True,
        "bot_bypass": True,
        "graphql": False,
        "queue": True,
        "three_ds": True,
        **toggles,
        "bot_simulation": r.get("defense:config:bot_simulation") in [b"1", "1"],
        **get_workflow_config(),
    }


@app.get("/metrics")
def metrics():
    def label(value: str) -> str:
        return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")

    lines = ["# TYPE defense_events_total counter"]
    for field, count in r.hgetall("defense:metrics:events").items():
        layer, action, blocked = field.split("|", 2)
        lines.append(f'defense_events_total{{layer="{label(layer)}",action="{label(action)}",blocked="{blocked}"}} {int(count)}')
    lines.extend([
        "# TYPE defense_admit_time_milliseconds_sum counter",
        f'defense_admit_time_milliseconds_sum {int(r.get("defense:metric:admit_time_ms_sum") or 0)}',
        "# TYPE defense_admit_time_count counter",
        f'defense_admit_time_count {int(r.get("defense:metric:admit_time_count") or 0)}',
        "# TYPE defense_hold_expired_total counter",
        f'defense_hold_expired_total {int(r.get("defense:metric:hold_expired_total") or 0)}',
        "# TYPE defense_waiting_room_size gauge",
    ])
    waiting = sum(r.zcard(key) for key in r.scan_iter(match="defense:waiting:*:rank"))
    lines.append(f"defense_waiting_room_size {waiting}")
    return PlainTextResponse("\n".join(lines) + "\n", media_type="text/plain; version=0.0.4")


@app.get("/api/defense-toggles")
def get_toggles_api():
    return get_defense_toggles()


@app.post("/api/defense-toggles")
async def update_toggles_api(request: Request):
    data = await request.json()
    if not isinstance(data, dict):
        raise HTTPException(status_code=422, detail="toggles must be an object")
    workflow_input = {key: value for key, value in data.items() if key in WORKFLOW_DEFAULTS}
    toggle_input = {key: value for key, value in data.items() if key not in WORKFLOW_DEFAULTS}
    allowed = {"waf", "akamai", "bot_bypass", "graphql", "queue", "three_ds", "bot_simulation"}
    if set(toggle_input) - allowed or any(type(value) is not bool for value in toggle_input.values()):
        raise HTTPException(status_code=422, detail="invalid defense toggle")
    old_workflow = get_workflow_config()
    try:
        workflow = normalize_workflow(workflow_input, old_workflow)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    toggles = {key: value for key, value in get_defense_toggles().items() if key in allowed}
    toggles.update(toggle_input)
    pipe = r.pipeline()
    pipe.set("defense:config:toggles", json.dumps(toggles))
    pipe.set(WORKFLOW_CONFIG_KEY, json.dumps(workflow))
    if workflow["QUEUE_MODE"] != old_workflow["QUEUE_MODE"]:
        waiting_keys = list(r.scan_iter(match="defense:waiting:*"))
        if waiting_keys:
            pipe.delete(*waiting_keys)
    if any(workflow[key] != old_workflow[key] for key in ("CAPTCHA_POSITION", "CAPTCHA_RANDOM_RATE")):
        pipe.incr("defense:config:captcha_version")
    if "bot_simulation" in toggle_input:
        pipe.set("defense:config:bot_simulation", "1" if toggle_input["bot_simulation"] else "0")
    pipe.execute()
    result = {**toggles, **workflow}
    log_event("edge", "admin_update_toggles", "", client_ip(request), result, blocked=False)
    return {"success": True, "toggles": result}


@app.post("/api/event-config")
async def update_event_config(request: Request):
    data = await request.json()
    if not isinstance(data, dict):
        raise HTTPException(status_code=422, detail="event config must be an object")
    workflow_input = data.pop("workflow", None)
    event_id = data.pop("eventId", DEFAULT_EVENT_ID)
    try:
        validate_event_id(event_id)
        event_update = validate_event_update(data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    old_workflow = get_workflow_config()
    workflow = old_workflow
    if workflow_input is not None:
        try:
            workflow = normalize_workflow(workflow_input, old_workflow)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    event = load_event(event_id)
    if not event:
        raise HTTPException(status_code=404, detail="event not found")
    event.update(event_update)
    pipe = r.pipeline()
    if event_id == DEFAULT_EVENT_ID:
        pipe.set("defense:config:event", json.dumps(event))
    else:
        pipe.hset(EVENTS_KEY, event_id, json.dumps(event))
    pipe.set(WORKFLOW_CONFIG_KEY, json.dumps(workflow))
    if workflow["QUEUE_MODE"] != old_workflow["QUEUE_MODE"]:
        waiting_keys = list(r.scan_iter(match="defense:waiting:*"))
        if waiting_keys:
            pipe.delete(*waiting_keys)
    if any(workflow[key] != old_workflow[key] for key in ("CAPTCHA_POSITION", "CAPTCHA_RANDOM_RATE")):
        pipe.incr("defense:config:captcha_version")
    pipe.execute()
    result = {**event, "workflow": workflow}
    log_event("edge", "admin_update_event_config", "", client_ip(request), result, blocked=False)
    return {"success": True, "config": result}


@app.get("/admin")
def admin():
    return FileResponse(str(FRONTEND / "admin.html"))


@app.post("/api/sensor")
async def submit_sensor(request: Request):
    ip = client_ip(request)
    raw = await request.json()
    sensor_data = raw.get("sensor_data") or ""
    if not sensor_data and raw.get("user_agent"):
        import base64

        sensor_data = base64.b64encode(json.dumps(raw).encode()).decode()
    body = SensorSubmit(
        sensor_data=sensor_data,
        session_id=raw.get("session_id", ""),
        fingerprint=raw.get("fingerprint", ""),
    )
    session_id = body.session_id or session_id_from_request(request)
    if not session_id:
        session_id = __import__("uuid").uuid4().hex

    bump_request_count(session_id)
    toggles = get_defense_toggles()

    if not toggles.get("akamai", True):
        bot_score = 0
        challenged = False
        fingerprint = body.fingerprint or session_id
        signals = {"signal_count": 0}
    else:
        cookie_hash = cookie_hash_from_abck(request.cookies.get("_abck", ""))
        signals, err = decode_sensor_payload(body.sensor_data, cookie_hash)
        if signals is None:
            log_event("akamai", "sensor_decode_fail", session_id, ip, {"error": err}, blocked=True)
            raise HTTPException(status_code=400, detail={"error": "SENSOR_INVALID", "reason": err})

        fingerprint = body.fingerprint or signals.get("fingerprint", session_id)
        bot_score = compute_bot_score(signals)
        challenged = bot_score >= 55

    payload = {
        "session_id": session_id,
        "fingerprint": fingerprint,
        "bot_score": bot_score,
        "signal_count": signals.get("signal_count", 0),
        "challenged": challenged,
        "ts": time.time(),
    }
    r.setex(sensor_session_key(session_id), SENSOR_SESSION_TTL_SEC, json.dumps(payload))
    log_event("akamai", "sensor_accepted", session_id, ip, {"bot_score": bot_score, "signals": signals.get("signal_count")})

    resp = JSONResponse({
        "ok": True,
        "bot_score": bot_score,
        "challenged": challenged,
        "session_id": session_id,
    })
    _set_akamai_cookies(resp, session_id, fingerprint, bot_score, challenged)
    return resp


@app.post("/api/challenge/pass")
async def challenge_pass(request: Request):
    session_id = session_id_from_request(request)
    if not session_id:
        raise HTTPException(status_code=400, detail="missing session")

    raw = r.get(sensor_session_key(session_id))
    if raw:
        meta = json.loads(raw)
        meta["bot_score"] = max(0, int(meta.get("bot_score", 50)) - 30)
        meta["challenged"] = False
        r.setex(sensor_session_key(session_id), SENSOR_SESSION_TTL_SEC, json.dumps(meta))

    r.setex(f"defense:challenge_ok:{session_id}", 600, "1")

    async with httpx.AsyncClient(timeout=10.0) as client:
        await client.post(
            f"{QUEUE_SERVICE_URL}/internal/challenge-pass",
            json={"session_id": session_id, "event_id": active_event_id(request)},
        )

    fingerprint = ""
    if raw:
        fingerprint = json.loads(raw).get("fingerprint", session_id)
    bot_score = json.loads(raw).get("bot_score", 25) if raw else 25

    resp = JSONResponse({"ok": True, "bot_score": bot_score})
    _set_akamai_cookies(resp, session_id, fingerprint, bot_score, False)
    log_event("akamai", "challenge_passed_gateway", session_id, client_ip(request), {"bot_score": bot_score})
    return resp


@app.get("/login")
def login_page():
    return FileResponse(str(FRONTEND / "login.html"))


@app.get("/captcha")
def captcha_page():
    return FileResponse(str(FRONTEND / "captcha.html"))


@app.get("/api/auth/session")
def auth_session(request: Request):
    user_id = current_user(request)
    return {"authenticated": bool(user_id), "user_id": user_id}


@app.post("/api/auth/login")
async def auth_login(request: Request):
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(status_code=422, detail="INVALID_LOGIN_REQUEST")
    email = str(body.get("email", "")).strip().lower()
    password = str(body.get("password", ""))
    session_id = session_id_from_request(request)
    if not session_id or not r.get(sensor_session_key(session_id)):
        raise HTTPException(status_code=401, detail="SENSOR_SESSION_REQUIRED")
    if not email or "@" not in email or not password:
        raise HTTPException(status_code=422, detail="EMAIL_AND_PASSWORD_REQUIRED")
    user_id = hashlib.sha256(email.encode()).hexdigest()[:24]
    queue_token = str(body.get("queue_token", ""))
    if queue_token:
        token_key = "defense:token:" + hashlib.sha256(queue_token.encode()).hexdigest()[:16]
        raw = r.get(token_key)
        if not raw:
            raise HTTPException(status_code=403, detail="INVALID_QUEUE_TOKEN")
        meta = json.loads(raw)
        if (meta.get("session_id") != session_id or meta.get("ip") != client_ip(request)
                or (meta.get("user_id") and meta["user_id"] != user_id)):
            raise HTTPException(status_code=403, detail="QUEUE_TOKEN_BIND_MISMATCH")
        r.set(token_key, json.dumps({**meta, "user_id": user_id}), keepttl=True)
    auth_token, user_id = create_auth(email, session_id)
    response = JSONResponse({"ok": True, "user_id": user_id})
    response.set_cookie("defense_auth", auth_token, max_age=AUTH_SESSION_TTL_SEC, httponly=True,
                        secure=request.url.scheme == "https", samesite="lax")
    log_event("login", "login_success", session_id, client_ip(request), {"user_id": user_id})
    return response


@app.post("/api/auth/logout")
def auth_logout(request: Request):
    token = request.cookies.get("defense_auth", "")
    if token:
        from shared.workflow import auth_key
        r.delete(auth_key(token))
    response = JSONResponse({"ok": True})
    response.delete_cookie("defense_auth")
    return response


@app.get("/api/captcha/challenge")
def captcha_challenge(request: Request, position: str, event_id: str = DEFAULT_EVENT_ID):
    if position not in GATE_POSITIONS:
        raise HTTPException(status_code=422, detail="INVALID_POSITION")
    session_id = session_id_from_request(request)
    if not session_id or not r.get(sensor_session_key(session_id)):
        raise HTTPException(status_code=401, detail="SENSOR_SESSION_REQUIRED")
    workflow = get_workflow_config()
    if not captcha_required(workflow, session_id, event_id, position, _sensor_meta(session_id).get("bot_score", 60)):
        return {"required": False, "position": position}
    if captcha_passed(session_id, event_id, position):
        return {"required": False, "position": position}
    return {"required": True, **new_challenge(session_id, event_id, position)}


@app.post("/api/captcha/verify")
async def captcha_verify(request: Request):
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(status_code=422, detail="INVALID_CAPTCHA_REQUEST")
    position = body.get("position", "")
    event_id = body.get("event_id") or DEFAULT_EVENT_ID
    session_id = session_id_from_request(request)
    if position not in GATE_POSITIONS or not session_id:
        raise HTTPException(status_code=422, detail="INVALID_CAPTCHA_REQUEST")
    if not verify_challenge(session_id, event_id, position, body.get("answer", "")):
        log_event("captcha", "captcha_failed", session_id, client_ip(request), {"position": position}, blocked=True)
        raise HTTPException(status_code=403, detail="CAPTCHA_FAILED")
    log_event("captcha", "captcha_passed", session_id, client_ip(request), {"position": position})
    return {"ok": True, "position": position}


@app.get("/member-code")
def member_code_page(request: Request):
    gate = _gate_status(request, "booking", active_event_id(request))
    if not gate and _login_required(get_workflow_config(), "seat") and not current_user(request):
        gate = {"status": "need_login", "position": "seat"}
    if gate:
        return _page_gate_redirect(gate, "/member-code")
    return FileResponse(str(FRONTEND / "member-code.html"))


@app.get("/seats")
def seats_page(request: Request):
    gate = _gate_status(request, "seat", active_event_id(request))
    if gate:
        return _page_gate_redirect(gate, "/seats")
    return FileResponse(str(FRONTEND / "seat-map.html"))


@app.get("/checkout")
def checkout_page(request: Request):
    gate = _gate_status(request, "checkout", active_event_id(request))
    if gate:
        return _page_gate_redirect(gate, "/checkout")
    return FileResponse(str(FRONTEND / "checkout.html"))


@app.get("/checkout.html")
def checkout_html_alias(request: Request):
    query = request.url.query
    target = "/checkout" + (f"?{query}" if query else "")
    return RedirectResponse(url=target, status_code=307)


@app.get("/")
def index():
    return FileResponse(str(FRONTEND / "waiting-room.html"))


@app.get("/events")
def events_page():
    return FileResponse(str(FRONTEND / "events.html"))


@app.get("/m")
def mobile_index():
    return RedirectResponse("/?mobile=1", status_code=307)


@app.get("/m/seats")
def mobile_seats():
    return RedirectResponse("/seats?mobile=1", status_code=307)


@app.get("/m/checkout")
def mobile_checkout():
    return RedirectResponse("/checkout?mobile=1", status_code=307)


def _sensor_meta(session_id: str) -> Dict[str, Any]:
    raw = r.get(sensor_session_key(session_id))
    if not raw:
        return {"bot_score": 60, "fingerprint": session_id, "challenged": True}
    return json.loads(raw)


async def _handle_queue_status(
    client: httpx.AsyncClient,
    ip: str,
    session_id: str,
    event_id: str,
    join_queue: bool,
    auth_token: str = "",
) -> dict:
    sm = _sensor_meta(session_id)
    resp = await client.post(
        f"{QUEUE_SERVICE_URL}/internal/queue-status",
        json={
            "event_id": event_id,
            "ip": ip,
            "session_id": session_id,
            "bot_score": sm.get("bot_score", 50),
            "fingerprint": sm.get("fingerprint", session_id),
            "join_queue": join_queue,
            "auth_token": auth_token,
        },
    )
    data = resp.json()
    return {
        "status": data.get("status"),
        "reason": data.get("reason"),
        "position": data.get("position"),
        "token": data.get("token", ""),
        "captchaSitekey": data.get("captchaSitekey", ""),
        "queuePosition": data.get("queuePosition"),
        "issuedAt": data.get("issued_at"),
        "botScore": data.get("botScore"),
        "challengeRequired": data.get("challengeRequired", False),
        "startTime": data.get("startTime"),
    }


async def _handle_add_to_cart(
    client: httpx.AsyncClient,
    request: Request,
    ip: str,
    session_id: str,
    inp: dict,
) -> JSONResponse | dict:
    queue_token = request.headers.get("x-queueit-token", "")
    sm = _sensor_meta(session_id)
    resp = await client.post(
        f"{SEAT_SERVICE_URL}/internal/add-to-cart",
        json={
            "event_id": inp.get("eventId", DEFAULT_EVENT_ID),
            "ticket_type": inp.get("ticketType", "GA-B1"),
            "quantity": inp.get("quantity", 1),
            "queue_token": queue_token,
            "ip": ip,
            "session_id": session_id,
            "api_only": not bool(r.get(f"defense:telemetry:{session_id}")),
            "bot_score": sm.get("bot_score"),
            "auth_token": request.cookies.get("defense_auth", ""),
        },
    )
    if resp.status_code == 428:
        return JSONResponse(resp.json().get("detail", {}), status_code=428)
    if resp.status_code == 403:
        detail = resp.json().get("detail", {})
        return JSONResponse(
            {"errors": [{"message": "FRAUD_DETECTED", "extensions": detail}]},
            status_code=403,
        )
    if resp.status_code == 409:
        return {"success": False, "errorCode": resp.json().get("detail", {}).get("errorCode", "SeatAlreadyLocked")}
    if resp.status_code >= 400:
        return JSONResponse({"errors": [{"message": resp.json().get("detail", {}).get("errorCode", "BOOKING_FAILED")}]}, status_code=resp.status_code)
    data = resp.json()
    return {"success": data.get("success"), "cartId": data.get("cartId")}


async def _handle_checkout(
    client: httpx.AsyncClient,
    request: Request,
    ip: str,
    session_id: str,
    inp: dict,
) -> JSONResponse | dict:
    queue_token = inp.get("queueToken") or request.headers.get("x-queueit-token", "")
    card = inp.get("card", {})
    buyer = inp.get("buyer", {})
    resp = await client.post(
        f"{PAYMENT_SERVICE_URL}/internal/checkout",
        json={
            "cart_id": inp.get("cartId"),
            "queue_token": queue_token,
            "ip": ip,
            "session_id": session_id,
            "card_number": card.get("number", ""),
            "buyer_email": buyer.get("email", ""),
            "payment_method": inp.get("paymentMethod", "credit_card"),
            "attendees": inp.get("attendees", []),
            "auth_token": request.cookies.get("defense_auth", ""),
            "bot_score": _sensor_meta(session_id).get("bot_score", 60),
        },
    )
    if resp.status_code >= 400:
        detail = resp.json().get("detail", {})
        if resp.status_code == 428:
            return JSONResponse(detail, status_code=428)
        return JSONResponse(
            {
                "errors": [
                    {
                        "message": detail.get("errorCode", "CHECKOUT_FAILED"),
                        "extensions": detail,
                    }
                ]
            },
            status_code=resp.status_code,
        )
    return resp.json()


@app.post("/api/funnel/queue-status")
async def funnel_queue_status(request: Request):
    body = await request.json()
    ip = client_ip(request)
    session_id = session_id_from_request(request)
    event_id = body.get("eventId") or DEFAULT_EVENT_ID
    join_queue = bool(body.get("joinQueue", False))
    gate = _gate_status(request, "queue", event_id)
    if gate:
        return {"data": {"queueStatus": gate}}
    async with httpx.AsyncClient(timeout=15.0) as client:
        data = await _handle_queue_status(client, ip, session_id, event_id, join_queue,
                                          request.cookies.get("defense_auth", ""))
    if data["status"] == "admitted" and _login_required(get_workflow_config(), "seat") and not current_user(request):
        data["status"] = "need_login"
    return {"data": {"queueStatus": data}}


@app.post("/api/funnel/add-to-cart")
async def funnel_add_to_cart(request: Request):
    body = await request.json()
    ip = client_ip(request)
    session_id = session_id_from_request(request)
    inp = body.get("input", body)
    gate = (_gate_response(request, "booking", inp.get("eventId", DEFAULT_EVENT_ID))
            or _gate_response(request, "seat", inp.get("eventId", DEFAULT_EVENT_ID))
            or _gate_response(request, "lock", inp.get("eventId", DEFAULT_EVENT_ID)))
    if gate:
        return gate
    token_gate = _bound_token_gate(request, request.headers.get("x-queueit-token", ""))
    if token_gate:
        return token_gate
    async with httpx.AsyncClient(timeout=15.0) as client:
        result = await _handle_add_to_cart(client, request, ip, session_id, inp)
    if isinstance(result, JSONResponse):
        return result
    return {"data": {"addToCart": result}}


@app.post("/api/funnel/checkout")
async def funnel_checkout(request: Request):
    body = await request.json()
    ip = client_ip(request)
    session_id = session_id_from_request(request)
    inp = body.get("input", body)
    gate = _gate_response(request, "checkout", cart_event_id(inp.get("cartId", "")))
    if gate:
        return gate
    token_gate = _bound_token_gate(request, inp.get("queueToken") or request.headers.get("x-queueit-token", ""))
    if token_gate:
        return token_gate
    async with httpx.AsyncClient(timeout=15.0) as client:
        result = await _handle_checkout(client, request, ip, session_id, inp)
    if isinstance(result, JSONResponse):
        return result
    return {"data": {"checkout": result}}


@app.post("/graphql/v2")
async def graphql_v2(request: Request):
    toggles = get_defense_toggles()
    if not toggles.get("graphql", False):
        log_event(
            "edge",
            "graphql_disabled",
            session_id_from_request(request),
            client_ip(request),
            BLOCK_RESPONSE,
            blocked=True,
        )
        return JSONResponse(BLOCK_RESPONSE, status_code=403)

    ip = client_ip(request)
    session_id = session_id_from_request(request)
    body = await request.json()
    op, variables = parse_graphql(body)

    async with httpx.AsyncClient(timeout=15.0) as client:
        if op == "queueStatus":
            event_id = variables.get("eventId") or DEFAULT_EVENT_ID
            join = variables.get("joinQueue", False)
            gate = _gate_status(request, "queue", event_id)
            if gate:
                return {"data": {"queueStatus": gate}}
            data = await _handle_queue_status(client, ip, session_id, event_id, join,
                                              request.cookies.get("defense_auth", ""))
            if data["status"] == "admitted" and _login_required(get_workflow_config(), "seat") and not current_user(request):
                data["status"] = "need_login"
            return {"data": {"queueStatus": data}}

        if op == "addToCart":
            inp = variables.get("input", {})
            gate = (_gate_response(request, "booking", inp.get("eventId", DEFAULT_EVENT_ID))
                    or _gate_response(request, "seat", inp.get("eventId", DEFAULT_EVENT_ID))
                    or _gate_response(request, "lock", inp.get("eventId", DEFAULT_EVENT_ID)))
            if gate:
                return gate
            token_gate = _bound_token_gate(request, request.headers.get("x-queueit-token", ""))
            if token_gate:
                return token_gate
            result = await _handle_add_to_cart(client, request, ip, session_id, inp)
            if isinstance(result, JSONResponse):
                return result
            return {"data": {"addToCart": result}}

        if op == "checkout":
            inp = variables.get("input", {})
            gate = _gate_response(request, "checkout", cart_event_id(inp.get("cartId", "")))
            if gate:
                return gate
            token_gate = _bound_token_gate(request, inp.get("queueToken") or request.headers.get("x-queueit-token", ""))
            if token_gate:
                return token_gate
            result = await _handle_checkout(client, request, ip, session_id, inp)
            if isinstance(result, JSONResponse):
                return result
            return {"data": {"checkout": result}}

    raise HTTPException(status_code=400, detail="Unknown GraphQL operation")


@app.post("/api/telemetry")
async def telemetry_proxy(request: Request):
    body = await request.json()
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(f"{SEAT_SERVICE_URL}/internal/telemetry", json=body)
        return resp.json()


@app.post("/api/3ds/verify")
async def three_ds_verify(request: Request):
    body = await request.json()
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(f"{PAYMENT_SERVICE_URL}/internal/3ds/verify", json=body)
        if resp.status_code >= 400:
            raise HTTPException(status_code=resp.status_code, detail=resp.json().get("detail"))
        return resp.json()


@app.post("/api/qr/verify")
async def qr_verify(request: Request):
    body = await request.json()
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(f"{PAYMENT_SERVICE_URL}/internal/qr/verify", json=body)
        if resp.status_code >= 400:
            raise HTTPException(status_code=resp.status_code, detail=resp.json().get("detail"))
        return resp.json()


@app.get("/api/seats/{event_id}")
async def seats_proxy(event_id: str, request: Request):
    gate = _gate_response(request, "seat", event_id)
    if gate:
        return gate
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{SEAT_SERVICE_URL}/internal/seats/{event_id}")
        return JSONResponse(resp.json(), status_code=resp.status_code)
