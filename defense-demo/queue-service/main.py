import hashlib
import json
import secrets
import sys
import time
from pathlib import Path

from fastapi import FastAPI, Request
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from admission import try_admit
from shared.config import MOCK_CAPTCHA_SITEKEY, TOKEN_TTL_SEC
from shared.events import log_event
from shared.redis_client import r

app = FastAPI(title="Queue Service")


class QueueStatusRequest(BaseModel):
    event_id: str
    ip: str = ""
    session_id: str = ""


def token_key(token: str) -> str:
    h = hashlib.sha256(token.encode()).hexdigest()[:16]
    return f"defense:token:{h}"


@app.get("/health")
def health():
    return {"status": "ok", "service": "queue-service"}


@app.post("/internal/queue-status")
def queue_status(req: QueueStatusRequest, request: Request):
    ip = req.ip or (request.client.host if request.client else "unknown")

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

    toggles_raw = r.get("defense:config:toggles")
    toggles = json.loads(toggles_raw) if toggles_raw else {"queue": True}

    if toggles.get("queue", True):
        if not try_admit():
            log_event("ip", "admission_denied", req.session_id, ip, blocked=True)
            return {
                "status": "waiting",
                "token": "",
                "captchaSitekey": "",
                "queuePosition": r.incr("defense:queue:waiting") % 1000 + 1,
            }

    token = secrets.token_urlsafe(32)
    issued_at = time.time()
    meta = {
        "event_id": req.event_id,
        "ip": ip,
        "session_id": req.session_id,
        "issued_at": issued_at,
    }
    r.setex(token_key(token), TOKEN_TTL_SEC, json.dumps(meta))

    log_event("queue", "token_issued", req.session_id, ip, {"event_id": req.event_id})
    return {
        "status": "admitted",
        "token": token,
        "captchaSitekey": MOCK_CAPTCHA_SITEKEY,
        "issued_at": issued_at,
    }


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
