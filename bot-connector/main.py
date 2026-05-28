import asyncio
import json
import os
import random
import time
from datetime import datetime
from typing import Any, Optional

import redis
from fastapi import Depends, FastAPI, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from auth import BotRegistry
from sandbox import (
    DEFAULT_EVENT_ID,
    check_sandbox_health,
    proxy_3ds,
    proxy_graphql,
    proxy_seats,
    proxy_telemetry,
    sandbox_info,
)
from sessions import SessionStore

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
CONNECTOR_PORT = int(os.environ.get("CONNECTOR_PORT", "8100"))

app = FastAPI(
    title="TTM Bot Connector",
    description="API สำหรับ Bot ภายนอกเชื่อมต่อและทดสอบใน Defense Demo Sandbox",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

redis_client = redis.from_url(REDIS_URL, decode_responses=True)
bots = BotRegistry(redis_client)
sessions = SessionStore(redis_client)


class RegisterRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: str = ""


class HeartbeatRequest(BaseModel):
    status: str = "online"
    meta: dict = Field(default_factory=dict)


class CreateSessionRequest(BaseModel):
    event_id: str = DEFAULT_EVENT_ID
    mode: str = "sandbox"
    metadata: dict = Field(default_factory=dict)


class GraphQLRequest(BaseModel):
    query: str
    variables: dict = Field(default_factory=dict)
    operationName: Optional[str] = None
    queue_token: str = ""


class TelemetryRequest(BaseModel):
    events: list[dict] = Field(default_factory=list)
    mousemove_count: int = 0
    scroll_count: int = 0
    click_count: int = 0
    seat_hover_count: int = 0


class SimulateHumanRequest(BaseModel):
    duration_sec: float = Field(default=2.0, ge=0.5, le=30.0)
    seat_hover_count: int = Field(default=5, ge=1, le=50)


class ThreeDSRequest(BaseModel):
    transaction_id: str
    otp: str


class LogRequest(BaseModel):
    level: str = "info"
    message: str
    detail: dict = Field(default_factory=dict)


def get_api_key(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    authorization: Optional[str] = Header(None),
) -> str:
    if x_api_key:
        return x_api_key
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    raise HTTPException(status_code=401, detail="Missing API key (X-API-Key or Authorization: Bearer)")


def get_bot(api_key: str = Depends(get_api_key)) -> dict:
    bot_id = bots.resolve_bot_id(api_key)
    if not bot_id:
        raise HTTPException(status_code=401, detail="Invalid API key")
    bot = bots.get_bot(bot_id)
    if not bot:
        raise HTTPException(status_code=401, detail="Bot not found")
    return bot


def get_session_for_bot(session_id: str, bot: dict = Depends(get_bot)) -> dict:
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.get("bot_id") != bot["bot_id"]:
        raise HTTPException(status_code=403, detail="Session belongs to another bot")
    if session.get("status") != "active":
        raise HTTPException(status_code=410, detail="Session is closed")
    return session


@app.get("/health")
async def health():
    sandbox = await check_sandbox_health()
    return {
        "status": "ok",
        "service": "bot-connector",
        "timestamp": datetime.now().isoformat(),
        "sandbox": sandbox,
    }


@app.get("/api/v1/sandbox/info")
async def get_sandbox_info():
    info = sandbox_info()
    info["health"] = await check_sandbox_health()
    return info


@app.post("/api/v1/register")
async def register_bot(body: RegisterRequest):
    result = bots.register(body.name, body.description)
    return {
        "status": "success",
        "message": "เก็บ api_key ไว้ใช้ในทุก request ถัดไป",
        "bot": {
            "bot_id": result["bot_id"],
            "api_key": result["api_key"],
            "name": result["name"],
        },
    }


@app.get("/api/v1/me")
async def get_me(bot: dict = Depends(get_bot)):
    active = sessions.list_for_bot(bot["bot_id"])
    return {"bot": bot, "active_sessions": len(active)}


@app.post("/api/v1/heartbeat")
async def heartbeat(body: HeartbeatRequest, bot: dict = Depends(get_bot)):
    updated = bots.heartbeat(bot["bot_id"], body.status, body.meta)
    return {"status": "ok", "bot": updated}


@app.post("/api/v1/sessions")
async def create_session(body: CreateSessionRequest, bot: dict = Depends(get_bot)):
    sandbox = await check_sandbox_health()
    if not sandbox.get("reachable"):
        raise HTTPException(
            status_code=503,
            detail={
                "error": "SANDBOX_UNAVAILABLE",
                "message": "Defense Demo sandbox ไม่พร้อม — รัน defense-demo ก่อน",
                "sandbox": sandbox,
            },
        )

    session = sessions.create(
        bot_id=bot["bot_id"],
        event_id=body.event_id,
        mode=body.mode,
        metadata=body.metadata,
    )
    bots.increment_sessions(bot["bot_id"])
    sessions.append_log(session["session_id"], "info", "Session created", {"event_id": body.event_id})
    return {"status": "success", "session": session}


@app.get("/api/v1/sessions")
async def list_sessions(bot: dict = Depends(get_bot)):
    return {"sessions": sessions.list_for_bot(bot["bot_id"])}


@app.get("/api/v1/sessions/{session_id}")
async def get_session(session: dict = Depends(get_session_for_bot)):
    logs = sessions.get_logs(session["session_id"], limit=30)
    return {"session": session, "logs": logs}


@app.delete("/api/v1/sessions/{session_id}")
async def close_session(session: dict = Depends(get_session_for_bot)):
    closed = sessions.close(session["session_id"])
    sessions.append_log(session["session_id"], "info", "Session closed")
    return {"status": "success", "session": closed}


@app.post("/api/v1/sessions/{session_id}/graphql")
async def session_graphql(
    body: GraphQLRequest,
    request: Request,
    session: dict = Depends(get_session_for_bot),
):
    sessions.increment_requests(session["session_id"])
    client_ip = request.client.host if request.client else None

    payload = {"query": body.query, "variables": body.variables}
    if body.operationName:
        payload["operationName"] = body.operationName

    queue_token = body.queue_token or session.get("queue_token", "")
    status_code, data = await proxy_graphql(
        session_id=session["session_id"],
        body=payload,
        queue_token=queue_token,
        client_ip=client_ip,
    )

    update_fields: dict[str, Any] = {}
    if status_code == 200 and isinstance(data, dict):
        gql_data = data.get("data", {})
        if "queueStatus" in gql_data:
            token = gql_data["queueStatus"].get("token", "")
            if token:
                update_fields["queue_token"] = token
        if "addToCart" in gql_data and gql_data["addToCart"].get("success"):
            cart_id = gql_data["addToCart"].get("cartId", "")
            if cart_id:
                update_fields["cart_id"] = cart_id
        if "checkout" in gql_data and gql_data["checkout"].get("success"):
            update_fields["order_id"] = gql_data["checkout"].get("orderId", "")

    if status_code >= 400:
        err_msg = ""
        if isinstance(data, dict):
            errors = data.get("errors", [])
            if errors:
                err_msg = errors[0].get("message", "")
            elif "detail" in data:
                err_msg = str(data["detail"])
        update_fields["last_error"] = err_msg or f"HTTP {status_code}"
        sessions.append_log(session["session_id"], "error", f"GraphQL failed: {update_fields['last_error']}", data)
    else:
        op = "unknown"
        if "queueStatus" in body.query:
            op = "queueStatus"
        elif "addToCart" in body.query:
            op = "addToCart"
        elif "checkout" in body.query:
            op = "checkout"
        sessions.append_log(session["session_id"], "info", f"GraphQL {op} OK", {"status_code": status_code})

    if update_fields:
        sessions.update(session["session_id"], **update_fields)

    return {"status_code": status_code, "data": data, "session_id": session["session_id"]}


@app.post("/api/v1/sessions/{session_id}/telemetry")
async def session_telemetry(body: TelemetryRequest, session: dict = Depends(get_session_for_bot)):
    payload = body.model_dump()
    payload["sessionId"] = session["session_id"]
    status_code, data = await proxy_telemetry(session["session_id"], payload)
    sessions.append_log(
        session["session_id"],
        "info",
        "Telemetry submitted",
        {"status_code": status_code, "events": len(body.events)},
    )
    return {"status_code": status_code, "data": data}


@app.post("/api/v1/sessions/{session_id}/telemetry/simulate-human")
async def simulate_human_telemetry(body: SimulateHumanRequest, session: dict = Depends(get_session_for_bot)):
    events = []
    steps = max(int(body.duration_sec * 10), 5)
    for i in range(steps):
        events.append({
            "type": "mousemove",
            "x": random.randint(0, 1200),
            "y": random.randint(0, 800),
            "ts": time.time() + i * 0.1,
        })
    for _ in range(random.randint(2, 8)):
        events.append({"type": "scroll", "deltaY": random.randint(-200, 200), "ts": time.time()})
    for _ in range(body.seat_hover_count):
        events.append({
            "type": "seat_hover",
            "seatId": f"GA-B{random.randint(1, 5)}-{random.randint(1, 20)}",
            "ts": time.time(),
        })

    payload = {
        "sessionId": session["session_id"],
        "events": events,
        "mousemove_count": sum(1 for e in events if e["type"] == "mousemove"),
        "scroll_count": sum(1 for e in events if e["type"] == "scroll"),
        "click_count": random.randint(1, 5),
        "seat_hover_count": body.seat_hover_count,
    }
    status_code, data = await proxy_telemetry(session["session_id"], payload)
    sessions.append_log(session["session_id"], "info", "Simulated human telemetry", payload)
    return {"status_code": status_code, "data": data, "telemetry": payload}


@app.get("/api/v1/sessions/{session_id}/seats/{event_id}")
async def session_seats(event_id: str, session: dict = Depends(get_session_for_bot)):
    status_code, data = await proxy_seats(event_id)
    return {"status_code": status_code, "data": data}


@app.post("/api/v1/sessions/{session_id}/3ds/verify")
async def session_3ds(body: ThreeDSRequest, session: dict = Depends(get_session_for_bot)):
    status_code, data = await proxy_3ds(body.model_dump())
    level = "info" if status_code < 400 else "error"
    sessions.append_log(session["session_id"], level, "3DS verify", {"status_code": status_code})
    return {"status_code": status_code, "data": data}


@app.post("/api/v1/sessions/{session_id}/logs")
async def append_log(body: LogRequest, session: dict = Depends(get_session_for_bot)):
    sessions.append_log(session["session_id"], body.level, body.message, body.detail)
    return {"status": "ok"}


@app.get("/api/v1/sessions/{session_id}/logs")
async def get_logs(session: dict = Depends(get_session_for_bot), limit: int = 50):
    return {"logs": sessions.get_logs(session["session_id"], limit=limit)}


@app.get("/api/v1/admin/bots")
async def admin_list_bots():
    bot_list = bots.list_bots()
    return {"bots": bot_list, "count": len(bot_list)}


@app.websocket("/api/v1/ws/sessions/{session_id}")
async def ws_session(session_id: str, websocket: WebSocket):
    await websocket.accept()
    api_key = websocket.query_params.get("api_key", "")
    bot_id = bots.resolve_bot_id(api_key) if api_key else None
    session = sessions.get(session_id)

    if not bot_id or not session or session.get("bot_id") != bot_id:
        await websocket.send_json({"error": "Unauthorized or session not found"})
        await websocket.close(code=4401)
        return

    try:
        while True:
            current = sessions.get(session_id) or session
            logs = sessions.get_logs(session_id, limit=20)
            await websocket.send_json({
                "session": current,
                "logs": logs,
                "timestamp": datetime.now().isoformat(),
            })
            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=CONNECTOR_PORT)
