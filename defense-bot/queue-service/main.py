import hashlib
import json
import secrets
import sys
import time
from pathlib import Path

from fastapi import FastAPI, Request
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from admission import admission, issue_once, member_id
from shared.config import ADMISSION_RATE, BOT_SCORE_ADMIT_MAX, MOCK_CAPTCHA_SITEKEY
from shared.events import log_event
from shared.redis_client import r
from shared.workflow import auth_user, captcha_passed, captcha_required, get_workflow, sensor_score

app = FastAPI(title="Queue Service")


class QueueStatusRequest(BaseModel):
    event_id: str
    ip: str = ""
    session_id: str = ""
    auth_token: str = ""
    bot_score: int = 60
    join_queue: bool = False


def token_key(token: str) -> str:
    h = hashlib.sha256(token.encode()).hexdigest()[:16]
    return f"defense:token:{h}"


@app.get("/health")
def health():
    return {"status": "ok", "service": "queue-service"}


@app.post("/internal/queue-status")
def queue_status(req: QueueStatusRequest, request: Request):
    ip = req.ip or (request.client.host if request.client else "unknown")
    workflow = get_workflow()
    if not r.get(f"defense:sensor:{req.session_id}"):
        return {"status": "need_sensor", "position": "queue", "token": ""}
    bot_score = sensor_score(req.session_id)
    user_id = auth_user(req.auth_token, req.session_id)
    if workflow["REQUIRE_LOGIN_BEFORE_QUEUE"] and not user_id:
        return {"status": "need_login", "position": "queue", "token": ""}
    if captcha_required(workflow, req.session_id, req.event_id, "queue", bot_score) and not captcha_passed(req.session_id, req.event_id, "queue"):
        return {"status": "need_captcha", "position": "queue", "token": ""}

    sale_start_raw = r.get("defense:config:sale_start")
    sale_start = float(sale_start_raw) if sale_start_raw else 0.0
    
    if sale_start > time.time():
        return {
            "status": "pre_queue",
            "startTime": sale_start,
            "token": "",
            "captchaSitekey": "",
            "queuePosition": 0,
        }

    if not req.join_queue:
        return {"status": "waiting", "token": "", "queuePosition": 0, "startTime": 0}

    if not req.session_id:
        log_event("queue", "session_denied", "", ip, blocked=True)
        return {"status": "denied", "token": "", "reason": "SENSOR_SESSION_REQUIRED"}

    toggles_raw = r.get("defense:config:toggles")
    toggles = json.loads(toggles_raw) if toggles_raw else {"queue": True}

    mode = workflow["QUEUE_MODE"] if toggles.get("queue", True) else "off"
    if mode != "off" and bot_score > BOT_SCORE_ADMIT_MAX:
        log_event("queue", "score_denied", req.session_id, ip, {"bot_score": bot_score}, blocked=True)
        return {"status": "denied", "token": "", "reason": "BOT_SCORE_TOO_HIGH", "botScore": bot_score}
    member = member_id(req.event_id, req.session_id)
    if mode != "off":
        soft_seconds = int(r.get("defense:config:soft_open_seconds") or 0)
        effective_rate = max(1, ADMISSION_RATE // 4) if soft_seconds and sale_start <= time.time() < sale_start + soft_seconds else ADMISSION_RATE
        admitted, position, member = admission(req.event_id, req.session_id, bot_score, mode, effective_rate)
        if not admitted:
            log_event("queue", "waiting", req.session_id, ip, {"mode": mode, "position": position, "bot_score": bot_score})
            return {"status": "waiting", "token": "", "queuePosition": position, "botScore": bot_score}

    token = secrets.token_urlsafe(32)
    issued_at = time.time()
    meta = {
        "event_id": req.event_id,
        "ip": ip,
        "session_id": req.session_id,
        "user_id": user_id or "",
        "bot_score": bot_score,
        "captcha_passed": captcha_passed(req.session_id, req.event_id, "queue"),
        "profile": workflow["WORKFLOW_PROFILE"],
        "mode": mode,
        "issued_at": issued_at,
    }
    response = {
        "status": "need_login" if workflow["REQUIRE_LOGIN_BEFORE_SEAT"] and not user_id else "admitted",
        "position": "seat" if workflow["REQUIRE_LOGIN_BEFORE_SEAT"] and not user_id else None,
        "token": token,
        "captchaSitekey": MOCK_CAPTCHA_SITEKEY,
        "issued_at": issued_at,
        "botScore": bot_score,
    }
    issued = json.loads(issue_once(req.event_id, member, json.dumps(response), token_key(token), json.dumps(meta)))
    existing_raw = r.get(token_key(issued["token"]))
    existing_meta = json.loads(existing_raw) if existing_raw else {}
    if existing_meta.get("ip") != ip or existing_meta.get("session_id") != req.session_id:
        return {"status": "denied", "token": "", "reason": "QUEUE_TOKEN_BIND_MISMATCH"}
    if user_id and existing_meta.get("user_id") == user_id:
        issued["status"] = "admitted"
        issued["position"] = None
    if issued["token"] == token:
        admit_ms = int((issued_at - float(r.get(f"defense:waiting:joined:{member}") or issued_at)) * 1000)
        r.incrby("defense:metric:admit_time_ms_sum", admit_ms)
        r.incr("defense:metric:admit_time_count")
        log_event("queue", "token_issued", req.session_id, ip, {"event_id": req.event_id, "mode": mode,
                                                               "bot_score": bot_score,
                                                               "time_to_admit_ms": admit_ms})
    return issued


def validate_token(token: str, ip: str, session_id: str = ""):
    if not token:
        return None
    raw = r.get(token_key(token))
    if not raw:
        return None
    meta = json.loads(raw)
    if meta.get("ip") and ip and meta["ip"] != ip:
        return None
    if meta.get("session_id") and session_id and meta["session_id"] != session_id:
        return None
    return meta
