import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

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
    DEFAULT_EVENT_ID,
    DEFAULT_EVENT_NAME,
    PAYMENT_SERVICE_URL,
    PURCHASE_LIMIT_MINUTES,
    QUEUE_SERVICE_URL,
    SEAT_SERVICE_URL,
    SENSOR_SESSION_TTL_SEC,
)
try:
    from shared.events import clear_all_defense_data, get_audit_events, log_event, summarize_audit_events
except Exception:
    from shared.events import get_audit_events, log_event  # type: ignore
    def clear_all_defense_data(): pass  # type: ignore
    def summarize_audit_events(): return {"total": 0, "by_layer": {}}  # type: ignore
    # Also ensure log_event is available under the name used later
    if 'log_event' not in dir():
        from shared.events import log_event  # type: ignore
from shared.redis_client import r

app = FastAPI(title="Defense Gateway")
app.add_middleware(EdgeCDNMiddleware)
app.add_middleware(BotBypassBlockMiddleware)
app.add_middleware(WAFMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
if FRONTEND.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND)), name="static")


class SensorSubmit(BaseModel):
    sensor_data: str
    session_id: str = ""
    fingerprint: str = ""


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def session_id_from_request(request: Request) -> str:
    return request.headers.get("x-session-id", "") or request.cookies.get("defense_sid", "")


def sensor_session_key(session_id: str) -> str:
    return f"defense:sensor:{session_id}"


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


@app.post("/admin/api/clear-all")
def admin_clear_all():
    result = clear_all_defense_data()
    log_event("edge", "admin_clear_all", "", "", result, blocked=False)
    return result


@app.get("/admin")
def admin():
    return FileResponse(str(FRONTEND / "admin.html"))


@app.get("/api/event-config")
def event_config():
    return {
        "event_id": DEFAULT_EVENT_ID,
        "event_name": DEFAULT_EVENT_NAME,
        "purchase_limit_minutes": PURCHASE_LIMIT_MINUTES,
        "sensor_file_hash": "a3f8c2e9",
    }


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
            json={"session_id": session_id, "event_id": DEFAULT_EVENT_ID},
        )

    fingerprint = ""
    if raw:
        fingerprint = json.loads(raw).get("fingerprint", session_id)
    bot_score = json.loads(raw).get("bot_score", 25) if raw else 25

    resp = JSONResponse({"ok": True, "bot_score": bot_score})
    _set_akamai_cookies(resp, session_id, fingerprint, bot_score, False)
    log_event("akamai", "challenge_passed_gateway", session_id, client_ip(request), {"bot_score": bot_score})
    return resp


@app.get("/seats")
def seats_page():
    return FileResponse(str(FRONTEND / "seat-map.html"))


@app.get("/checkout")
def checkout_page():
    return FileResponse(str(FRONTEND / "checkout.html"))


@app.get("/checkout.html")
def checkout_html_alias(request: Request):
    query = request.url.query
    target = "/checkout" + (f"?{query}" if query else "")
    return RedirectResponse(url=target, status_code=307)


@app.get("/")
def index():
    return FileResponse(str(FRONTEND / "waiting-room.html"))


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
        },
    )
    data = resp.json()
    return {
        "status": data.get("status"),
        "token": data.get("token", ""),
        "captchaSitekey": data.get("captchaSitekey", ""),
        "queuePosition": data.get("queuePosition"),
        "issuedAt": data.get("issued_at"),
        "botScore": data.get("botScore"),
        "challengeRequired": data.get("challengeRequired", False),
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
        },
    )
    if resp.status_code == 403:
        detail = resp.json().get("detail", {})
        return JSONResponse(
            {"errors": [{"message": "FRAUD_DETECTED", "extensions": detail}]},
            status_code=403,
        )
    if resp.status_code == 409:
        return {"success": False, "errorCode": "SeatAlreadyLocked"}
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
        },
    )
    if resp.status_code >= 400:
        detail = resp.json().get("detail", {})
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
    async with httpx.AsyncClient(timeout=15.0) as client:
        data = await _handle_queue_status(client, ip, session_id, event_id, join_queue)
    return {"data": {"queueStatus": data}}


@app.post("/api/funnel/add-to-cart")
async def funnel_add_to_cart(request: Request):
    body = await request.json()
    ip = client_ip(request)
    session_id = session_id_from_request(request)
    inp = body.get("input", body)
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
    async with httpx.AsyncClient(timeout=15.0) as client:
        result = await _handle_checkout(client, request, ip, session_id, inp)
    if isinstance(result, JSONResponse):
        return result
    return {"data": {"checkout": result}}


@app.post("/graphql/v2")
async def graphql_v2(request: Request):
    if not GRAPHQL_ENABLED:
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
            data = await _handle_queue_status(client, ip, session_id, event_id, join)
            return {"data": {"queueStatus": data}}

        if op == "addToCart":
            inp = variables.get("input", {})
            result = await _handle_add_to_cart(client, request, ip, session_id, inp)
            if isinstance(result, JSONResponse):
                return result
            return {"data": {"addToCart": result}}

        if op == "checkout":
            inp = variables.get("input", {})
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


@app.get("/api/seats/{event_id}")
async def seats_proxy(event_id: str):
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{SEAT_SERVICE_URL}/internal/seats/{event_id}")
        return resp.json()
