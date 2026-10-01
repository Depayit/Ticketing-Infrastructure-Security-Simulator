import asyncio
import json
import hashlib
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.config import FRAUD_ENGINE_URL, SEAT_LOCK_TTL_SEC, THREE_DS_OTP
from shared.events import log_event
from shared.redis_client import r
from shared.workflow import auth_user, captcha_passed, captcha_required, get_workflow, sensor_score
from shared.seat_state import commit_hold, release_hold
from telegram_notify import delivery_loop, queue_payment_alert

app = FastAPI(title="Payment Service")


@app.on_event("startup")
async def start_telegram_delivery():
    if os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID"):
        asyncio.create_task(delivery_loop())


class CheckoutRequest(BaseModel):
    cart_id: str
    queue_token: str = ""
    ip: str = ""
    session_id: str = ""
    card_number: str = ""
    buyer_email: str = ""
    payment_method: str = "credit_card"
    attendees: list[str] = []
    auth_token: str = ""
    bot_score: int = 60


class ThreeDSVerifyRequest(BaseModel):
    challenge_id: str
    otp: str


class QRVerifyRequest(BaseModel):
    challenge_id: str


def seat_state_key(event_id: str, seat_id: str) -> str:
    return f"defense:seat:{event_id}:{seat_id}"


def _commit_order(cart: Dict[str, Any], cart_id: str, session_id: str, ip: str,
                  attendees: list[str], payment_method: str) -> str:
    order_id = f"ORD-{uuid.uuid4().hex[:10].upper()}"
    order = {
        "order_id": order_id,
        "event_id": cart["event_id"],
        "seat_id": cart["seat_id"],
        "quantity": cart.get("quantity", 1),
        "total_price": cart.get("total_price", 0),
        "email": cart.get("buyer_email", ""),
        "session_id": session_id,
        "committed_at": time.time(),
        "payment_method": payment_method,
        "attendees": attendees,
    }
    if not commit_hold(cart["event_id"], cart["seat_id"], cart_id, order):
        log_event("payment", "hold_expired_before_commit", session_id, ip, {"cart_id": cart_id}, blocked=True)
        raise HTTPException(status_code=409, detail={"errorCode": "HOLD_EXPIRED"})
    queue_payment_alert(order)
    return order_id


@app.get("/health")
def health():
    return {"status": "ok", "service": "payment-service"}


@app.post("/internal/checkout")
async def checkout(req: CheckoutRequest):
    cart_raw = r.get(f"defense:cart:{req.cart_id}")
    if not cart_raw:
        raise HTTPException(status_code=404, detail={"errorCode": "CART_NOT_FOUND"})

    cart = json.loads(cart_raw)
    cart["buyer_email"] = req.buyer_email
    session_id = req.session_id or cart.get("session_id", "")
    workflow = get_workflow()
    if (any(workflow[key] for key in ("REQUIRE_LOGIN_BEFORE_QUEUE", "REQUIRE_LOGIN_BEFORE_SEAT", "REQUIRE_LOGIN_BEFORE_LOCK"))
            or workflow["CAPTCHA_POSITION"] in ("checkout", "random")) and not r.get(f"defense:sensor:{session_id}"):
        raise HTTPException(status_code=428, detail={"status": "need_sensor", "position": "checkout"})
    if any(workflow[key] for key in ("REQUIRE_LOGIN_BEFORE_QUEUE", "REQUIRE_LOGIN_BEFORE_SEAT", "REQUIRE_LOGIN_BEFORE_LOCK")):
        user_id = auth_user(req.auth_token, session_id)
        raw = r.get("defense:token:" + hashlib.sha256(req.queue_token.encode()).hexdigest()[:16]) if req.queue_token else None
        meta = json.loads(raw) if raw else {}
        if (not user_id or meta.get("user_id") != user_id or meta.get("session_id") != session_id
                or meta.get("ip") != req.ip or meta.get("event_id") != cart.get("event_id")
                or req.queue_token != cart.get("queue_token")):
            raise HTTPException(status_code=403, detail={"errorCode": "QUEUE_TOKEN_BIND_MISMATCH"})
    if captcha_required(workflow, session_id, cart.get("event_id", ""), "checkout", sensor_score(session_id)) and not captcha_passed(session_id, cart.get("event_id", ""), "checkout"):
        raise HTTPException(status_code=428, detail={"status": "need_captcha", "position": "checkout"})

    telemetry_raw = r.get(f"defense:telemetry:{session_id}")
    telemetry = json.loads(telemetry_raw) if telemetry_raw else None
    events = telemetry.get("events", []) if telemetry else []
    token_issued_at = 0.0
    if req.queue_token:
        token_raw = r.get("defense:token:" + hashlib.sha256(req.queue_token.encode()).hexdigest()[:16])
        if token_raw:
            token_issued_at = json.loads(token_raw).get("issued_at", 0.0)
    features = {
        "session_id": session_id,
        "token_issued_at": token_issued_at,
        "lock_at": time.time(),
        "api_only": telemetry is None,
        "telemetry_event_count": len(events),
        "scroll_count": sum(1 for event in events if event.get("type") == "scroll"),
        "seat_hover_count": sum(1 for event in events if event.get("type") == "seat_hover"),
        "mousemove_count": sum(1 for event in events if event.get("type") == "mousemove"),
        "checkout_attempts_per_min": r.incr(f"defense:checkout:rate:{req.ip or session_id}") or 1,
    }
    r.expire(f"defense:checkout:rate:{req.ip or session_id}", 60)

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            score_resp = await client.post(f"{FRAUD_ENGINE_URL}/score", json=features)
            score_data = score_resp.json()
    except Exception:
        score_data = {"risk_score": 0.0, "decision": "allow"}

    if score_data.get("decision") == "block":
        _release_cart(cart, req.cart_id)
        log_event("payment", "fraud_blocked", session_id, req.ip, score_data, blocked=True)
        raise HTTPException(status_code=403, detail={"errorCode": "FRAUD_DETECTED"})

    if req.payment_method == "qr":
        challenge_id = str(uuid.uuid4())
        r.setex(f"defense:qr:{challenge_id}", 300, json.dumps({
            "cart_id": req.cart_id,
            "cart": cart,
            "session_id": session_id,
            "ip": req.ip,
            "attendees": req.attendees,
        }))
        log_event("payment", "qr_generated", session_id, req.ip, {"challenge_id": challenge_id})
        return {
            "success": False,
            "status": "qr_required",
            "orderId": None,
            "challengeId": challenge_id,
        }

    card_hash = req.card_number[-4:] if req.card_number else "unknown"
    card_use_key = f"defense:card:{card_hash}"
    card_sessions = r.incr(card_use_key)
    r.expire(card_use_key, 3600)
    if card_sessions > 3:
        log_event("3ds", "carding_detected", session_id, req.ip, {"card_last4": card_hash}, blocked=True)
        _release_cart(cart, req.cart_id)
        raise HTTPException(status_code=403, detail={"errorCode": "CARDING_DETECTED"})

    toggles_raw = r.get("defense:config:toggles")
    toggles = json.loads(toggles_raw) if toggles_raw else {"three_ds": True}

    if not toggles.get("three_ds", True):
        order_id = _commit_order(cart, req.cart_id, session_id, req.ip, req.attendees, req.payment_method)
        log_event("3ds", "payment_committed_bypass", session_id, req.ip, {"order_id": order_id})
        return {"success": True, "orderId": order_id, "status": "success"}

    challenge_id = str(uuid.uuid4())
    r.setex(f"defense:3ds:{challenge_id}", 300, json.dumps({
        "cart_id": req.cart_id,
        "cart": cart,
        "session_id": session_id,
        "ip": req.ip,
        "attendees": req.attendees,
    }))

    log_event("3ds", "challenge_issued", session_id, req.ip, {"challenge_id": challenge_id})
    return {
        "success": False,
        "status": "3ds_required",
        "orderId": None,
        "paymentUrl": f"/checkout.html?challenge={challenge_id}",
        "challengeId": challenge_id,
        "risk_score": score_data.get("risk_score", 0),
    }


@app.post("/internal/3ds/verify")
def verify_3ds(req: ThreeDSVerifyRequest):
    raw = r.get(f"defense:3ds:{req.challenge_id}")
    if not raw:
        raise HTTPException(status_code=404, detail={"errorCode": "CHALLENGE_EXPIRED"})

    payload = json.loads(raw)
    cart = payload["cart"]
    session_id = payload.get("session_id", "")

    if req.otp != THREE_DS_OTP:
        log_event("3ds", "otp_failed", session_id, payload.get("ip", ""), blocked=True)
        _release_cart(cart, payload["cart_id"])
        r.delete(f"defense:3ds:{req.challenge_id}")
        raise HTTPException(status_code=402, detail={"errorCode": "3DS_FAILED"})

    order_id = _commit_order(cart, payload["cart_id"], session_id, payload.get("ip", ""),
                             payload.get("attendees", []), "credit_card")
    r.delete(f"defense:3ds:{req.challenge_id}")

    log_event("3ds", "payment_committed", session_id, payload.get("ip", ""), {"order_id": order_id})
    return {"success": True, "orderId": order_id, "status": "success"}


@app.post("/internal/qr/verify")
def verify_qr(req: QRVerifyRequest):
    raw = r.get(f"defense:qr:{req.challenge_id}")
    if not raw:
        raise HTTPException(status_code=404, detail={"errorCode": "CHALLENGE_EXPIRED"})

    payload = json.loads(raw)
    cart = payload["cart"]
    session_id = payload.get("session_id", "")

    order_id = _commit_order(cart, payload["cart_id"], session_id, payload.get("ip", ""),
                             payload.get("attendees", []), "qr")
    r.delete(f"defense:qr:{req.challenge_id}")

    log_event("payment", "qr_payment_committed", session_id, payload.get("ip", ""), {"order_id": order_id})
    return {"success": True, "orderId": order_id, "status": "success"}


def _release_cart(cart: Dict[str, Any], cart_id: str) -> None:
    release_hold(cart["event_id"], cart["seat_id"], cart_id, count_abuse=True)
