"""Operator API for the local ticketing research lab."""

import asyncio
import base64
import binascii
import hmac
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import redis
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles


app = FastAPI(title="Ticketing Security Simulator Manager")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")
DEV_MODE = os.getenv("DEV_MODE", "false").lower() == "true"
STATIC_DIR = Path(__file__).resolve().parent / "static"
r = redis.from_url(REDIS_URL, decode_responses=True)

DEFAULT_CONFIG = {
    "bot_mode": "defense_demo",
    "event_id": "demo-concert-2026",
    "target_url": "http://defense-gateway:8090/?demo=1",
    "official_event_url": "https://www.thaiticketmajor.com/",
    "defense_demo": {"default_url": "http://defense-gateway:8090/?demo=1"},
    "proxies": [],
    "profiles": [],
    "browser_profiles": [],
    "queueit": {"headless": True, "manual_takeover": False, "max_minutes": 10},
    "telegram_bots": [],
    "membership_code": "LAB-DEMO",
}


def redis_ready():
    try:
        r.ping()
    except redis.RedisError as exc:
        raise HTTPException(503, "Redis unavailable") from exc


def require_operator(request: Request):
    if DEV_MODE:
        return
    supplied = request.headers.get("x-admin-token", "")
    if not ADMIN_TOKEN or not hmac.compare_digest(supplied, ADMIN_TOKEN):
        raise HTTPException(403, "Operator token required")


def require_worker_id(instance_id: str):
    if not re.fullmatch(r"worker-[a-f0-9]{8}", instance_id):
        raise HTTPException(404, "Unknown worker")


def validate_lab_url(value: str):
    try:
        parsed = urlparse(value)
        valid = (
            parsed.scheme == "http"
            and parsed.hostname in {"defense-gateway", "localhost", "127.0.0.1"}
            and parsed.port in {8090, None}
            and not parsed.username
            and not parsed.password
        )
    except (TypeError, ValueError):
        valid = False
    if not valid:
        raise HTTPException(422, "Target URL must point to the local defense gateway")


def validate_official_event_url(value: str):
    if not isinstance(value, str):
        raise HTTPException(422, "Official event URL must be a string")
    value = value.strip() or DEFAULT_CONFIG["official_event_url"]
    try:
        parsed = urlparse(value)
        valid = (
            parsed.scheme == "https"
            and parsed.hostname in {
                "thaiticketmajor.com",
                "www.thaiticketmajor.com",
                "booking.thaiticketmajor.com",
            }
            and parsed.port is None
            and not parsed.username
            and not parsed.password
        )
    except ValueError:
        valid = False
    if not valid:
        raise HTTPException(422, "Official event URL must be an HTTPS ThaiTicketMajor page")
    return value


def get_config():
    redis_ready()
    raw = r.get("ticket:config")
    if not raw:
        return dict(DEFAULT_CONFIG)
    try:
        return {**DEFAULT_CONFIG, **json.loads(raw)}
    except (ValueError, TypeError):
        raise HTTPException(500, "Stored configuration is invalid")


@app.get("/health")
def health():
    redis_ready()
    return {"status": "ok"}


@app.get("/api/config")
def read_config(request: Request):
    require_operator(request)
    return get_config()


@app.post("/api/config")
async def save_config(request: Request):
    require_operator(request)
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(422, "Expected a configuration object")
    defense = body.get("defense_demo") or {}
    if not isinstance(defense, dict):
        raise HTTPException(422, "Invalid defense settings")
    target = body.get("target_url") or defense.get("default_url")
    validate_lab_url(target or "")
    if body.get("bot_mode") not in {"defense_demo", "queueit"}:
        raise HTTPException(422, "Unknown bot mode")
    body["target_url"] = target
    body["official_event_url"] = validate_official_event_url(
        body.get("official_event_url", DEFAULT_CONFIG["official_event_url"])
    )
    redis_ready()
    r.set("ticket:config", json.dumps(body, ensure_ascii=False))
    r.publish("ticket:config_updates", "updated")
    return {"status": "saved"}


@app.get("/api/status")
def status():
    cfg = get_config()
    workers = []
    for key in r.scan_iter("worker:*"):
        try:
            workers.append(json.loads(r.get(key) or "{}"))
        except (ValueError, TypeError):
            continue
    return {
        "active_workers": sum(w.get("status") not in {"STANDBY", "STOPPED"} for w in workers),
        "success_count": int(r.get("ticket:success_count") or 0),
        "global_stop": r.get("ticket:global_stop") == "1",
        "is_running": r.get("ticket:running") == "1",
        "live_logs": r.lrange("ticket:logs", 0, 100),
        "active_proxies": r.scard("ticket:proxies:active"),
        "dead_proxies": r.scard("ticket:proxies:dead"),
        "total_proxies": r.scard("ticket:proxies:raw"),
        "browser_profiles_count": len(cfg.get("browser_profiles") or []),
        "buyer_profiles_count": len(cfg.get("profiles") or []),
        "bot_mode": cfg.get("bot_mode"),
        "event_id": cfg.get("event_id"),
        "target_url": cfg.get("target_url"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "workers": workers,
    }


@app.post("/api/start")
def start(request: Request):
    require_operator(request)
    validate_lab_url(get_config().get("target_url", ""))
    r.delete("ticket:global_stop")
    r.set("ticket:running", "1")
    return {"status": "running"}


@app.post("/api/stop")
def stop(request: Request):
    require_operator(request)
    redis_ready()
    r.set("ticket:running", "0")
    return {"status": "stopped"}


@app.post("/api/worker/{instance_id}/{action}")
def control_worker(instance_id: str, action: str, request: Request):
    require_operator(request)
    require_worker_id(instance_id)
    if action not in {"start", "stop"}:
        raise HTTPException(404, "Unknown worker action")
    redis_ready()
    key = f"ticket:stop:{instance_id}"
    if action == "stop":
        r.set(key, "1")
    else:
        r.delete(key)
    return {"status": action}


@app.post("/api/live/{instance_id}/start")
@app.post("/api/live/{instance_id}/stop")
def live_toggle(instance_id: str, request: Request):
    require_operator(request)
    require_worker_id(instance_id)
    action = request.url.path.rsplit("/", 1)[-1]
    redis_ready()
    key = f"ticket:live_stream:{instance_id}"
    if action == "start":
        r.setex(key, 30, "1")
    else:
        r.delete(key)
    return {"status": action}


@app.post("/api/live/{instance_id}/control")
async def live_control(instance_id: str, request: Request):
    require_operator(request)
    require_worker_id(instance_id)
    command = await request.json()
    if not isinstance(command, dict) or command.get("type") not in {"click", "type", "keypress"}:
        raise HTTPException(422, "Unknown control command")
    redis_ready()
    r.publish(f"ticket:control:{instance_id}", json.dumps(command))
    return {"status": "sent"}


@app.get("/api/live/{instance_id}/stream")
async def live_stream(instance_id: str, request: Request):
    require_operator(request)
    require_worker_id(instance_id)
    redis_ready()

    async def frames():
        while True:
            if await request.is_disconnected():
                break
            encoded = r.get(f"ticket:live_frame:{instance_id}")
            if encoded:
                try:
                    frame = base64.b64decode(encoded, validate=True)
                    yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
                except (ValueError, binascii.Error):
                    pass
            await asyncio.sleep(0.5)

    return StreamingResponse(frames(), media_type="multipart/x-mixed-replace; boundary=frame")


@app.get("/api/telegram/status")
def telegram_status(request: Request):
    require_operator(request)
    cfg = get_config()
    return {
        str(bot.get("id", index)): {
            "name": bot.get("name", "Telegram Bot"),
            "status": "disabled" if not bot.get("enabled", True) else "running",
            "message": "Configured in lab" if bot.get("enabled", True) else "Disabled",
        }
        for index, bot in enumerate(cfg.get("telegram_bots") or [])
    }


@app.websocket("/ws/logs")
async def logs_socket(ws: WebSocket):
    if not DEV_MODE and (not ADMIN_TOKEN or not hmac.compare_digest(
        ws.headers.get("x-admin-token", ""), ADMIN_TOKEN
    )):
        await ws.close(code=1008)
        return
    await ws.accept()
    try:
        while True:
            await ws.send_json({"logs": r.lrange("ticket:logs", 0, 100)})
            await asyncio.sleep(2)
    except (WebSocketDisconnect, redis.RedisError):
        pass


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


if (STATIC_DIR / "assets").exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)
