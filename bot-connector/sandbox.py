import os
from typing import Any, Optional

import httpx

SANDBOX_GATEWAY_URL = os.environ.get("SANDBOX_GATEWAY_URL", "http://localhost:8090")
DEFAULT_EVENT_ID = os.environ.get("SANDBOX_EVENT_ID", "demo-concert-2026")
DEFAULT_3DS_OTP = os.environ.get("SANDBOX_3DS_OTP", "123456")


def sandbox_info() -> dict:
    return {
        "gateway_url": SANDBOX_GATEWAY_URL,
        "graphql_url": f"{SANDBOX_GATEWAY_URL}/graphql/v2",
        "telemetry_url": f"{SANDBOX_GATEWAY_URL}/api/telemetry",
        "seats_url_template": f"{SANDBOX_GATEWAY_URL}/api/seats/{{event_id}}",
        "three_ds_verify_url": f"{SANDBOX_GATEWAY_URL}/api/3ds/verify",
        "waiting_room_url": f"{SANDBOX_GATEWAY_URL}/",
        "admin_url": f"{SANDBOX_GATEWAY_URL}/admin",
        "default_event_id": DEFAULT_EVENT_ID,
        "default_3ds_otp": DEFAULT_3DS_OTP,
        "operations": ["queueStatus", "addToCart", "checkout"],
        "required_headers": {
            "x-session-id": "Unique session ID (auto-set by connector)",
            "x-queueit-token": "Queue token from queueStatus (for addToCart/checkout)",
        },
        "test_scenarios": [
            {
                "id": "A",
                "name": "IP Layer — burst detection",
                "description": "ยิง request เกิน 15 ครั้ง/5 วิ → 429 RATE_LIMIT_BURST",
            },
            {
                "id": "B",
                "name": "AI Layer — API-only bot",
                "description": "GraphQL ตรงไม่ส่ง telemetry → 403 FRAUD_DETECTED",
            },
            {
                "id": "C",
                "name": "Human flow — ผ่านทุก layer",
                "description": "ส่ง telemetry + checkout + OTP 123456",
            },
            {
                "id": "D",
                "name": "3DS Layer — หลุด AI แต่ติด OTP",
                "description": "ปิด AI_LAYER_ENABLED แล้วทดสอบ checkout",
            },
        ],
    }


async def check_sandbox_health() -> dict:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{SANDBOX_GATEWAY_URL}/health")
            if resp.status_code == 200:
                return {"reachable": True, "status": resp.json()}
    except Exception as exc:
        return {"reachable": False, "error": str(exc)}
    return {"reachable": False, "error": "unexpected response"}


async def proxy_graphql(
    session_id: str,
    body: dict,
    queue_token: str = "",
    client_ip: Optional[str] = None,
) -> tuple[int, Any]:
    headers = {
        "Content-Type": "application/json",
        "x-session-id": session_id,
    }
    if queue_token:
        headers["x-queueit-token"] = queue_token
    if client_ip:
        headers["x-forwarded-for"] = client_ip

    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(
            f"{SANDBOX_GATEWAY_URL}/graphql/v2",
            json=body,
            headers=headers,
        )
        try:
            data = resp.json()
        except Exception:
            data = {"raw": resp.text}
        return resp.status_code, data


async def proxy_telemetry(session_id: str, body: dict) -> tuple[int, Any]:
    payload = dict(body)
    payload.setdefault("sessionId", session_id)
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"{SANDBOX_GATEWAY_URL}/api/telemetry",
            json=payload,
            headers={"x-session-id": session_id},
        )
        try:
            data = resp.json()
        except Exception:
            data = {"raw": resp.text}
        return resp.status_code, data


async def proxy_3ds(body: dict) -> tuple[int, Any]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(f"{SANDBOX_GATEWAY_URL}/api/3ds/verify", json=body)
        try:
            data = resp.json()
        except Exception:
            data = {"raw": resp.text}
        return resp.status_code, data


async def proxy_seats(event_id: str) -> tuple[int, Any]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{SANDBOX_GATEWAY_URL}/api/seats/{event_id}")
        try:
            data = resp.json()
        except Exception:
            data = {"raw": resp.text}
        return resp.status_code, data
