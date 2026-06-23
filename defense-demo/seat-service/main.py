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

TICKET_MAP = {"VIP": "VIP", "GA": "RED", "Standing": "BLUE"}
DEFAULT_SEATS = ["VIP", "RED", "RED_RESTRICTED", "BLUE", "YELLOW", "GREEN", "TEAL"]

import asyncio
import random

async def simulate_concurrent_booking():
    while True:
        await asyncio.sleep(random.uniform(2.0, 5.0))
        
        sim_enabled = r.get("defense:config:bot_simulation")
        if sim_enabled != b"1" and sim_enabled != "1":
            continue
            
        event_id = DEFAULT_EVENT_ID
        init_seats(event_id)
        
        # Find available seats
        available_seats = []
        locked_seats = []
        for seat in DEFAULT_SEATS:
            key = seat_state_key(event_id, seat)
            raw = r.get(key)
            if raw:
                state = json.loads(raw)
                if state.get("status") == "available":
                    available_seats.append(seat)
                elif state.get("status") == "locked":
                    locked_seats.append(seat)
                    
        # Randomly release a locked seat to simulate payment failure/timeout (20% chance)
        if locked_seats and random.random() < 0.2:
            seat_to_release = random.choice(locked_seats)
            key = seat_state_key(event_id, seat_to_release)
            r.set(key, json.dumps({"status": "available", "session_id": "", "cart_id": ""}))
            continue
            
        # Randomly lock an available seat
        if available_seats:
            seat_to_lock = random.choice(available_seats)
            key = seat_state_key(event_id, seat_to_lock)
            r.set(key, json.dumps({"status": "locked", "session_id": "sim_bot", "cart_id": "sim_cart"}))
            log_event("seat", "seat_locked_by_sim", "sim_bot", "127.0.0.1", {"seat_id": seat_to_lock})

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(simulate_concurrent_booking())


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
    # Fetch event config
    config_raw = r.get("defense:config:event")
    if config_raw:
        event_config = json.loads(config_raw)
    else:
        event_config = {
            "maxTicketsPerAccount": 4,
            "zones": [{"id": req.ticket_type, "price": 1000}]
        }
    
    max_tickets = event_config.get("maxTicketsPerAccount", 4)
    if req.quantity > max_tickets:
        raise HTTPException(status_code=400, detail={"errorCode": "QUANTITY_EXCEEDED", "message": f"Cannot purchase more than {max_tickets} tickets."})
        
    zone = next((z for z in event_config.get("zones", []) if z["id"] == req.ticket_type), None)
    if not zone:
        zone = {"id": req.ticket_type, "price": 1000}
    
    total_price = zone["price"] * req.quantity

    seat_id = req.ticket_type
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
        
    seat_key = seat_state_key(req.event_id, seat_id)
    seat_state = get_seat(req.event_id, seat_id)
    if seat_state.get("status") != "available":
        raise HTTPException(status_code=409, detail={"errorCode": "SeatAlreadyLocked", "message": "ที่นั่งถูกล็อกโดยผู้อื่นแล้ว"})

    cart_id = str(uuid.uuid4())
    
    # Mark as locked in Redis
    r.set(seat_key, json.dumps({"status": "locked", "session_id": session_id, "cart_id": cart_id}))
    
    r.setex(f"defense:cart:{cart_id}", SEAT_LOCK_TTL_SEC, json.dumps({
        "event_id": req.event_id,
        "seat_id": seat_id,
        "quantity": req.quantity,
        "total_price": total_price,
        "session_id": session_id,
        "queue_token": req.queue_token,
    }))

    log_event("seat", "seat_locked", session_id, req.ip, {"seat_id": seat_id, "cart_id": cart_id})
    return {"success": True, "cartId": cart_id, "seatId": seat_id, "risk_score": score_data.get("risk_score", 0)}


