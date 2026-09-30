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
from shared.event_state import list_events, load_event, sale_status
from shared.redis_client import r
from shared.workflow import auth_user, captcha_passed, captcha_required, get_workflow, sensor_score
from shared.seat_state import lock_hold, read_seat, release_hold

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
        
        available_seats = [seat for seat in DEFAULT_SEATS if get_seat(event_id, seat)["status"] == "available"]
        if available_seats:
            seat_to_lock = random.choice(available_seats)
            cart_id = f"sim-{uuid.uuid4().hex}"
            cart = {"event_id": event_id, "seat_id": seat_to_lock, "session_id": "sim_bot"}
            if lock_hold(event_id, seat_to_lock, cart_id, "sim_bot", "127.0.0.1", cart, 20) == "locked":
                log_event("seat", "seat_locked_by_sim", "sim_bot", "127.0.0.1", {"seat_id": seat_to_lock})
                await asyncio.sleep(random.uniform(3.0, 8.0))
                release_hold(event_id, seat_to_lock, cart_id)


async def sweep_expired_holds():
    while True:
        await asyncio.sleep(5)
        for event in list_events():
            for seat in DEFAULT_SEATS:
                get_seat(event["eventId"], seat)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(simulate_concurrent_booking())
    asyncio.create_task(sweep_expired_holds())


def seat_state_key(event_id: str, seat_id: str) -> str:
    return f"defense:seat:{event_id}:{seat_id}"


def init_seats(event_id: str) -> None:
    for seat in DEFAULT_SEATS:
        key = seat_state_key(event_id, seat)
        if not r.exists(key):
            r.set(key, json.dumps({"status": "available", "session_id": "", "cart_id": ""}))


def get_seat(event_id: str, seat_id: str) -> Dict[str, Any]:
    init_seats(event_id)
    return read_seat(event_id, seat_id)


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
    auth_token: str = ""
    bot_score: int = 60


@app.get("/health")
def health():
    return {"status": "ok", "service": "seat-service"}


@app.get("/internal/seats/{event_id}")
def list_seats(event_id: str):
    if not load_event(event_id):
        raise HTTPException(status_code=404, detail="EVENT_NOT_FOUND")
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
    status = sale_status(req.event_id)
    if status != "open":
        error = {"paused": "EVENT_PAUSED", "sold_out": "EVENT_SOLD_OUT", "missing": "EVENT_NOT_FOUND"}.get(status, "EVENT_PAUSED")
        raise HTTPException(status_code=409, detail={"errorCode": error})
    workflow = get_workflow()
    if (any(workflow[key] for key in ("REQUIRE_LOGIN_BEFORE_QUEUE", "REQUIRE_LOGIN_BEFORE_SEAT", "REQUIRE_LOGIN_BEFORE_LOCK"))
            or workflow["CAPTCHA_POSITION"] in ("booking", "seat", "lock", "random")) and not r.get(f"defense:sensor:{req.session_id}"):
        raise HTTPException(status_code=428, detail={"status": "need_sensor", "position": "lock"})
    if any(workflow[key] for key in ("REQUIRE_LOGIN_BEFORE_QUEUE", "REQUIRE_LOGIN_BEFORE_SEAT", "REQUIRE_LOGIN_BEFORE_LOCK")):
        user_id = auth_user(req.auth_token, req.session_id)
        if not user_id:
            raise HTTPException(status_code=428, detail={"status": "need_login", "position": "lock"})
        if not req.queue_token:
            raise HTTPException(status_code=403, detail={"errorCode": "QUEUE_TOKEN_REQUIRED"})
        import hashlib
        token_hash = hashlib.sha256(req.queue_token.encode()).hexdigest()[:16]
        raw = r.get(f"defense:token:{token_hash}")
        meta = json.loads(raw) if raw else {}
        if (meta.get("user_id") != user_id or meta.get("session_id") != req.session_id
                or meta.get("ip") != req.ip or meta.get("event_id") != req.event_id):
            raise HTTPException(status_code=403, detail={"errorCode": "QUEUE_TOKEN_BIND_MISMATCH"})
    for position in ("booking", "seat", "lock"):
        if captcha_required(workflow, req.session_id, req.event_id, position, sensor_score(req.session_id)) and not captcha_passed(req.session_id, req.event_id, position):
            raise HTTPException(status_code=428, detail={"status": "need_captcha", "position": position})
    # Fetch event config
    event_config = load_event(req.event_id)
    
    max_tickets = event_config.get("maxTicketsPerAccount", 4)
    if req.quantity < 1 or req.quantity > max_tickets:
        raise HTTPException(status_code=400, detail={"errorCode": "QUANTITY_EXCEEDED", "message": f"Cannot purchase more than {max_tickets} tickets."})
    if req.ticket_type not in DEFAULT_SEATS:
        raise HTTPException(status_code=400, detail={"errorCode": "INVALID_SEAT"})
        
    zone = next((z for z in event_config.get("zones", []) if z["id"] == req.ticket_type), None)
    if not zone:
        raise HTTPException(status_code=400, detail={"errorCode": "INVALID_SEAT"})
    
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
        
    cart_id = str(uuid.uuid4())
    cart = {
        "event_id": req.event_id,
        "seat_id": seat_id,
        "quantity": req.quantity,
        "total_price": total_price,
        "session_id": session_id,
        "queue_token": req.queue_token,
    }
    result = lock_hold(req.event_id, seat_id, cart_id, session_id, req.ip, cart, SEAT_LOCK_TTL_SEC)
    if result == "abuse_blocked":
        log_event("seat", "reserve_abuse_blocked", session_id, req.ip, blocked=True)
        raise HTTPException(status_code=403, detail={"errorCode": "RESERVE_ABUSE_BLOCKED"})
    if result != "locked":
        raise HTTPException(status_code=409, detail={"errorCode": "SeatAlreadyLocked", "message": "ที่นั่งถูกล็อกโดยผู้อื่นแล้ว"})

    log_event("seat", "seat_locked", session_id, req.ip, {"seat_id": seat_id, "cart_id": cart_id})
    return {"success": True, "cartId": cart_id, "seatId": seat_id, "risk_score": score_data.get("risk_score", 0)}


