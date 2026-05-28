from pathlib import Path
from collections import deque
from fastapi import FastAPI, WebSocket, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import redis
import asyncio
import uvicorn
import json
from datetime import datetime

app = FastAPI(title="TTM 2026 Bot Dashboard")
REDIS_URL = "redis://redis:6379/0"
BASE_DIR = Path(__file__).resolve().parent


class LocalRedis:
    def __init__(self):
        self.data = {}
        self.logs = deque(maxlen=100)
        self.config = {
            "bot_mode": "ttm",
            "event_id": "",
            "target_url": "",
            "click_selector": "button:has-text('Add to Cart'), button:has-text('ซื้อเลย'), button:has-text('ใส่ตะกร้า')",
            "refresh_mode": "auto_refresh",
            "refresh_interval": 1.0,
            "action_after_click": "notify",
            "telegram_token": "",
            "telegram_chat_id": "",
            "captcha_key": "",
            "redis_url": "redis://redis:6379/0",
            "proxies": [],
            "profiles": [],
            "ticket_priorities": ["VIP", "GA", "Standing"],
            # snapshot flag — frontend uses this to detect a freshly-saved config
            "_saved_at": "",
        }

    def keys(self, pattern: str):
        if pattern == "worker:*":
            return [key for key in self.data if key.startswith("worker:")]
        return [key for key in self.data if key == pattern]

    def get(self, key: str):
        return self.data.get(key)

    def set(self, key: str, value: str, ex=None):
        self.data[key] = value

    def delete(self, *keys):
        for key in keys:
            self.data.pop(key, None)

    def lrange(self, key: str, start: int, end: int):
        if key != "ttm:logs":
            return []
        items = list(self.logs)
        return items[start:end + 1]

    def append_log(self, message: str):
        self.logs.append(message)

    def get_config(self):
      return self.config

    def set_config(self, config: dict):
      self.config = config

    def scard(self, key: str) -> int:
        val = self.data.get(key)
        if isinstance(val, set):
            return len(val)
        return 0

    def sadd(self, key: str, *values) -> int:
        if key not in self.data or not isinstance(self.data[key], set):
            self.data[key] = set()
        added = 0
        for val in values:
            if val not in self.data[key]:
                self.data[key].add(val)
                added += 1
        return added

    def srem(self, key: str, *values) -> int:
        val = self.data.get(key)
        if not isinstance(val, set):
            return 0
        removed = 0
        for v in values:
            if v in val:
                val.remove(v)
                removed += 1
        return removed

    def smembers(self, key: str) -> set:
        val = self.data.get(key)
        if isinstance(val, set):
            return val
        return set()



class RedisGateway:
    def __init__(self):
        self.client = redis.from_url(REDIS_URL, decode_responses=True)
        self.local = LocalRedis()
        self.use_local = False

    def _call(self, method_name, *args, **kwargs):
        if self.use_local:
            return getattr(self.local, method_name)(*args, **kwargs)

        try:
            return getattr(self.client, method_name)(*args, **kwargs)
        except Exception:
            self.use_local = True
            return getattr(self.local, method_name)(*args, **kwargs)

    def keys(self, pattern: str):
        return self._call("keys", pattern)

    def get(self, key: str):
        return self._call("get", key)

    def set(self, key: str, value: str, ex=None):
        return self._call("set", key, value, ex=ex)

    def delete(self, *keys):
        return self._call("delete", *keys)

    def lrange(self, key: str, start: int, end: int):
        return self._call("lrange", key, start, end)

    def append_log(self, message: str):
        if self.use_local:
            self.local.append_log(message)
            return

        try:
            existing = self.client.lrange("ttm:logs", 0, 99)
            logs = list(existing)
            logs.append(message)
            self.client.delete("ttm:logs")
            if logs:
                for log in reversed(logs[-100:]):
                    self.client.lpush("ttm:logs", log)
        except Exception:
            self.use_local = True
            self.local.append_log(message)

    def get_config(self):
        if self.use_local:
            return self.local.get_config()
        try:
            config_str = self.client.get("ttm:config")
            if config_str:
                return json.loads(config_str)
            return self.local.get_config()
        except Exception:
            self.use_local = True
            return self.local.get_config()

    def set_config(self, config: dict):
        if self.use_local:
            self.local.set_config(config)
            return

        try:
            self.client.set("ttm:config", json.dumps(config))
            self.local.set_config(config)
        except Exception:
            self.use_local = True
            self.local.set_config(config)


redis_store = RedisGateway()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

static_dir = BASE_DIR / "static"
if static_dir.exists():
    app.mount("/assets", StaticFiles(directory=str(static_dir / "assets")), name="assets")


@app.get("/")
async def serve_dashboard():
    if static_dir.exists() and (static_dir / "index.html").exists():
        return FileResponse(static_dir / "index.html")
    return {"error": "dashboard assets not found"}


@app.get("/api/status")
async def get_status():
    active_workers = len(redis_store.keys("worker:*"))
    success_count = int(redis_store.get("ttm:success_count") or 0)
    global_stop = redis_store.get("ttm:global_stop") == "1"
    is_running = redis_store.get("ttm:running") == "1"
    live_logs = redis_store.lrange("ttm:logs", 0, 80)
    
    try:
        active_proxies = int(redis_store._call("scard", "ttm:proxies:active") or 0)
        dead_proxies = int(redis_store._call("scard", "ttm:proxies:dead") or 0)
        total_proxies = int(redis_store._call("scard", "ttm:proxies:raw") or 0)
    except Exception:
        active_proxies = 0
        dead_proxies = 0
        total_proxies = 0

    bot_mode = "ttm"
    event_id = ""
    target_url = ""
    try:
        cfg = redis_store.get_config()
        browser_profiles_count = len(cfg.get("browser_profiles", []))
        buyer_profiles_count = len(cfg.get("profiles", []))
        bot_mode = cfg.get("bot_mode", "ttm")
        event_id = cfg.get("event_id", "")
        target_url = cfg.get("target_url", "")
    except Exception:
        browser_profiles_count = 0
        buyer_profiles_count = 0

    return {
        "active_workers": active_workers,
        "success_count": success_count,
        "global_stop": global_stop,
        "is_running": is_running,
        "live_logs": live_logs,
        "active_proxies": active_proxies,
        "dead_proxies": dead_proxies,
        "total_proxies": total_proxies,
        "browser_profiles_count": browser_profiles_count,
        "buyer_profiles_count": buyer_profiles_count,
        "bot_mode": bot_mode,
        "event_id": event_id,
        "target_url": target_url,
        "timestamp": datetime.now().isoformat(),
    }


@app.post("/api/start")
async def start_all():
    redis_store.delete("ttm:global_stop")
    redis_store.set("ttm:command", "start")
    redis_store.set("ttm:running", "1")
    redis_store.append_log(f"[{datetime.now().strftime('%H:%M:%S')}] Dashboard: ▶ START — workers กำลังทำงาน")
    return {"status": "success", "message": "All workers started"}


@app.post("/api/stop")
async def stop_all():
    redis_store.set("ttm:global_stop", "1", ex=7200)
    redis_store.set("ttm:command", "stop")
    redis_store.delete("ttm:running")
    redis_store.append_log(f"[{datetime.now().strftime('%H:%M:%S')}] Dashboard: ⏹ STOP — workers หยุดทำงานแล้ว")
    return {"status": "success", "message": "All workers stopped"}


@app.get("/api/config")
async def get_config():
    return redis_store.get_config()


@app.post("/api/config")
async def set_config(request: Request):
    config = await request.json()
    # stamp the save time so workers and UI can detect freshness
    config["_saved_at"] = datetime.now().isoformat()
    redis_store.set_config(config)
    redis_store.append_log(
        f"[{datetime.now().strftime('%H:%M:%S')}] Dashboard: config updated "
        f"(profiles={len(config.get('profiles', []))}, proxies={len(config.get('proxies', []))})"
    )
    return {"status": "success", "message": "Configuration saved", "saved_at": config["_saved_at"]}


@app.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            logs = redis_store.lrange("ttm:logs", 0, 50)
            try:
                await websocket.send_json({"logs": logs, "timestamp": datetime.now().isoformat()})
            except Exception:
                break
            await asyncio.sleep(1.2)
    except Exception:
        pass


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8080)
