"""HTTP smoke test for the isolated Docker Defense Lab."""

import base64
import json
import os
import re
import time
import uuid

import httpx


BASE = os.getenv("GATEWAY_URL", "http://gateway:8090")
EVENT = "demo-concert-2026"


def require(response, status=200):
    assert response.status_code == status, (response.request.url, response.status_code, response.text)
    return response.json()


def solve_captcha(client, position):
    challenge = require(client.get("/api/captcha/challenge", params={"position": position, "event_id": EVENT}))
    if challenge.get("required"):
        numbers = [int(n) for n in re.findall(r"\d+", challenge["question"])]
        assert numbers, challenge
        require(client.post("/api/captcha/verify", json={
            "position": position, "event_id": EVENT, "answer": sum(numbers),
        }))


def run_profile(profile, index):
    require(httpx.post(BASE + "/admin/api/reset-seats", timeout=15))
    require(httpx.post(BASE + "/admin/api/set-sale-start", json={"delay_seconds": 0}, timeout=15))
    updated = require(httpx.post(BASE + "/api/event-config", json={
        "workflow": {"WORKFLOW_PROFILE": profile},
    }, timeout=15))
    assert updated["config"]["workflow"]["WORKFLOW_PROFILE"] == profile

    sid = uuid.uuid4().hex
    ip = f"198.51.100.{index}"
    with httpx.Client(base_url=BASE, timeout=15, headers={
        "x-session-id": sid, "x-forwarded-for": ip, "User-Agent": "DefenseLabSmoke/1",
    }) as client:
        payload = base64.b64encode(json.dumps({"signal_count": 150, "fingerprint": sid}).encode()).decode()
        sensor = require(client.post("/api/sensor", json={"sensor_data": payload, "session_id": sid}))
        assert sensor["bot_score"] < 55
        token = ""
        admitted = False
        for _ in range(45):
            state = require(client.post("/api/funnel/queue-status", json={
                "eventId": EVENT, "joinQueue": True,
            }))["data"]["queueStatus"]
            status = state["status"]
            if state.get("token"):
                token = state["token"]
            if status == "admitted":
                admitted = True
                break
            if status == "need_login":
                require(client.post("/api/auth/login", json={
                    "email": f"smoke-{profile}@example.invalid", "password": "lab", "queue_token": token,
                }))
            elif status == "need_captcha":
                solve_captcha(client, state.get("position", "queue"))
            elif status == "waiting":
                time.sleep(0.25)
            else:
                raise AssertionError((profile, state))
        assert admitted and token, (profile, state)

        for position in ("booking", "seat", "lock", "checkout"):
            solve_captcha(client, position)
        now = int(time.time() * 1000)
        events = ([{"type": "mousemove", "t": now + i * 30, "x": i * 9, "y": 200} for i in range(35)]
                  + [{"type": "scroll", "t": now + 1100}, {"type": "seat_hover", "t": now + 1200}])
        require(client.post("/api/telemetry", json={
            "session_id": sid, "token_issued_at": time.time() - 3, "events": events,
        }))
        time.sleep(1.1)
        seats = require(client.get(f"/api/seats/{EVENT}"))
        available = next(s["seatId"] for s in seats["seats"] if s["status"] == "available")
        headers = {"x-queueit-token": token}
        cart = require(client.post("/api/funnel/add-to-cart", headers=headers, json={"input": {
            "eventId": EVENT, "ticketType": available, "quantity": 1,
        }}))["data"]["addToCart"]
        assert cart["success"], (profile, cart)
        payment = require(client.post("/api/funnel/checkout", headers=headers, json={"input": {
            "cartId": cart["cartId"], "queueToken": token, "paymentMethod": "credit_card",
            "buyer": {"email": "smoke@example.invalid"},
            "card": {"number": f"411111111111{index:04d}"}, "attendees": ["Smoke Test"],
        }}))["data"]["checkout"]
        if payment["status"] == "3ds_required":
            payment = require(client.post("/api/3ds/verify", json={
                "challenge_id": payment["challengeId"], "otp": "123456",
            }))
        assert payment["status"] == "success", (profile, payment)
        print(f"profile {profile}: admitted, locked {available}, paid {payment['orderId']}", flush=True)


if __name__ == "__main__":
    for number, name in enumerate("ABCD", start=1):
        run_profile(name, number)
    metrics = httpx.get(BASE + "/metrics", timeout=15)
    assert metrics.status_code == 200 and "defense_events_total" in metrics.text
    print("metrics: available", flush=True)
