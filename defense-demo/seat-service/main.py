import json
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.config import DEFAULT_EVENT_ID, FRAUD_ENGINE_URL, SEAT_LOCK_TTL_SEC
from shared.events import log_event
from shared.redis_client import r

app = FastAPI(title="Seat Service")

TICKET_MAP = {"VIP": "VIP-A1", "GA": "GA-B1", "Standing": "STAND-C1"}
DEFAULT_SEATS = ["VIP-A1", "VIP-A2", "GA-B1", "GA-B2", "STAND-C1", "STAND-C2"]


def seat_state_key(event_id: str, seat_id: str) -> str:
    return f"defense:seat:{event_id}:{seat_id}"


def init_seats(event_id: str) -> None:
    for seat in DEFAULT_SEATS:
        key = seat_state_key(event_id, seat)
        if not r.exists(key):
            r.set(key, json.dumps({"status": "available", "session_id": "", "cart_id": ""}))


def get_seat(event_id: str, seat_id: str) -> Dict[str, Any]:
    init_seats(event_id)
    raw = r.get(seat_state_key(event_id, seat_id))
    return json.loads(raw) if raw else {"status": "available", "session_id": "", "cart_id": ""}


class TelemetryEvent(BaseModel):
    type: str
    t: float
    x: Optional[float] = None
    y: Optional[float] = None
    seatId: Optional[str] = None
    dwellMs: Optional[float] = None
    step: Optional[str] = None


class TelemetryBatch(BaseModel):
    session_id: str
    token_issued_at: float
    events: List[TelemetryEvent]


class AddToCartRequest(BaseModel):
    event_id: str
    ticket_type: str
    quantity: int = 1
    queue_token: str = ""
    ip: str = ""
    session_id: str = ""
    api_only: bool = False


@app.get("/health")
def health():
    return {"status": "ok", "service": "seat-service"}


@app.get("/internal/seats/{event_id}")
def list_seats(event_id: str):
    init_seats(event_id)
    out = []
    for seat in DEFAULT_SEATS:
        st = get_seat(event_id, seat)
        out.append({"seatId": seat, **st})
    return {"seats": out}


@app.post("/internal/telemetry")
def ingest_telemetry(batch: TelemetryBatch):
    key = f"defense:telemetry:{batch.session_id}"
    r.setex(key, 3600, batch.model_dump_json())
    return {"ok": True, "count": len(batch.events)}


@app.post("/internal/add-to-cart")
async def add_to_cart(req: AddToCartRequest):
    init_seats(req.event_id)
    seat_id = TICKET_MAP.get(req.ticket_type, req.ticket_type if req.ticket_type in DEFAULT_SEATS else DEFAULT_SEATS[0])
    session_id = req.session_id or str(uuid.uuid4())

    telemetry_raw = r.get(f"defense:telemetry:{session_id}")
    telemetry = json.loads(telemetry_raw) if telemetry_raw else None

    token_meta_raw = None
    if req.queue_token:
        import hashlib
        h = hashlib.sha256(req.queue_token.encode()).hexdigest()[:16]
        token_meta_raw = r.get(f"defense:token:{h}")

    token_issued_at = 0.0
    if token_meta_raw:
        token_issued_at = json.loads(token_meta_raw).get("issued_at", 0.0)
    elif telemetry:
        token_issued_at = telemetry.get("token_issued_at", 0.0)

    features = {
        "session_id": session_id,
        "token_issued_at": token_issued_at,
        "lock_at": __import__("time").time(),
        "api_only": req.api_only or telemetry is None,
        "telemetry_event_count": len(telemetry.get("events", [])) if telemetry else 0,
        "checkout_attempts_per_min": 1,
    }

    if telemetry:
        events = telemetry.get("events", [])
        features["scroll_count"] = sum(1 for e in events if e.get("type") == "scroll")
        features["seat_hover_count"] = sum(1 for e in events if e.get("type") == "seat_hover")
        features["mousemove_count"] = sum(1 for e in events if e.get("type") == "mousemove")
    else:
        features["scroll_count"] = 0
        features["seat_hover_count"] = 0
        features["mousemove_count"] = 0

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            score_resp = await client.post(f"{FRAUD_ENGINE_URL}/score", json=features)
            score_data = score_resp.json()
    except Exception:
        score_data = {"risk_score": 0.0, "decision": "allow", "layer": "ai"}

    if score_data.get("decision") == "block":
        log_event("ai", "add_to_cart_blocked", session_id, req.ip, score_data, blocked=True)
        raise HTTPException(status_code=403, detail={"errorCode": "FRAUD_DETECTED", **score_data})

    lock_key = seat_state_key(req.event_id, seat_id)
    acquired = r.set(lock_key, json.dumps({
        "status": "held",
        "session_id": session_id,
        "cart_id": "",
        "held_at": __import__("time").time(),
    }), nx=True, ex=SEAT_LOCK_TTL_SEC)

    if not acquired:
        st = get_seat(req.event_id, seat_id)
        if st.get("session_id") == session_id:
            acquired = True
        else:
            raise HTTPException(status_code=409, detail={"errorCode": "SeatAlreadyLocked"})

    cart_id = str(uuid.uuid4())
    r.setex(lock_key, SEAT_LOCK_TTL_SEC, json.dumps({
        "status": "held",
        "session_id": session_id,
        "cart_id": cart_id,
        "held_at": __import__("time").time(),
    }))
    r.setex(f"defense:cart:{cart_id}", SEAT_LOCK_TTL_SEC, json.dumps({
        "event_id": req.event_id,
        "seat_id": seat_id,
        "session_id": session_id,
        "queue_token": req.queue_token,
    }))

    log_event("seat", "seat_locked", session_id, req.ip, {"seat_id": seat_id, "cart_id": cart_id})
    return {"success": True, "cartId": cart_id, "seatId": seat_id, "risk_score": score_data.get("risk_score", 0)}


