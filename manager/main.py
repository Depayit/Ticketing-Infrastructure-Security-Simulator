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

app = FastAPI(title="Ticket Bot 2026 Dashboard")
REDIS_URL = "redis://redis:6379/0"
BASE_DIR = Path(__file__).resolve().parent


class LocalRedis:
    def __init__(self):
        self.data = {}
        self.logs = deque(maxlen=100)
        self.config = {
            "bot_mode": "queueit",
            "event_id": "",
            "target_url": "",
            "click_selector": "button:has-text('Add to Cart'), button:has-text('ซื้อเลย'), button:has-text('ใส่ตะกร้า')",
            "refresh_mode": "auto_refresh",
            "refresh_interval": 1.0,
            "action_after_click": "notify",
            "telegram_token": "",
            "telegram_chat_id": "",
            "telegram_bots": [],
            "captcha_key": "",
            "redis_url": "redis://redis:6379/0",
            "proxies": [],
            "profiles": [],
            "ticket_priorities": ["VIP", "GA", "Standing"],
            "membership_code": "",
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
        if key != "ticket:logs":
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
            existing = self.client.lrange("ticket:logs", 0, 99)
            logs = list(existing)
            logs.append(message)
            self.client.delete("ticket:logs")
            if logs:
                for log in reversed(logs[-100:]):
                    self.client.lpush("ticket:logs", log)
        except Exception:
            self.use_local = True
            self.local.append_log(message)

    def get_config(self):
        if self.use_local:
            return self.local.get_config()
        try:
            config_str = self.client.get("ticket:config")
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
            self.client.set("ticket:config", json.dumps(config))
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
    worker_keys = redis_store.keys("worker:*")
    workers_list = []
    for k in worker_keys:
        try:
            val = redis_store.get(k)
            if val:
                workers_list.append(json.loads(val))
        except Exception:
            workers_list.append({
                "instance_id": k.split(":")[-1],
                "status": "RUNNING",
                "current_url": "N/A",
                "last_log": "Active",
                "proxy": "unknown",
                "updated_at": val or ""
            })
            
    active_workers = len(workers_list)
    success_count = int(redis_store.get("ticket:success_count") or 0)
    global_stop = redis_store.get("ticket:global_stop") == "1"
    is_running = redis_store.get("ticket:running") == "1"
    live_logs = redis_store.lrange("ticket:logs", 0, 80)
    
    try:
        active_proxies = int(redis_store._call("scard", "ticket:proxies:active") or 0)
        dead_proxies = int(redis_store._call("scard", "ticket:proxies:dead") or 0)
        total_proxies = int(redis_store._call("scard", "ticket:proxies:raw") or 0)
    except Exception:
        active_proxies = 0
        dead_proxies = 0
        total_proxies = 0

    bot_mode = "queueit"
    event_id = ""
    target_url = ""
    try:
        cfg = redis_store.get_config()
        browser_profiles_count = len(cfg.get("browser_profiles", []))
        buyer_profiles_count = len(cfg.get("profiles", []))
        bot_mode = cfg.get("bot_mode", "queueit")
        event_id = cfg.get("event_id", "")
        target_url = cfg.get("target_url", "")
    except Exception:
        browser_profiles_count = 0
        buyer_profiles_count = 0

    return {
        "active_workers": active_workers,
        "workers": workers_list,
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


@app.post("/api/ai/chat")
async def ai_chat(request: Request):
    import httpx
    data = await request.json()
    message = data.get("message", "")
    history = data.get("history", [])
    
    cfg = redis_store.get_config()
    api_key = cfg.get("gemini_api_key") or cfg.get("captcha_key")
    if not api_key or api_key.startswith("YOUR_"):
        return {
            "status": "error",
            "message": "กรุณาตั้งค่า Gemini API Key ในหน้าตั้งค่าบอทก่อนใช้งาน AI Chat Controller"
        }
        
    config_summary = {
        "bot_mode": cfg.get("bot_mode"),
        "target_url": cfg.get("target_url"),
        "refresh_mode": cfg.get("refresh_mode"),
        "refresh_interval": cfg.get("refresh_interval"),
        "ticket_count": cfg.get("ticket_count"),
        "ticket_priorities": cfg.get("ticket_priorities"),
        "buyer_profiles_count": len(cfg.get("profiles", [])),
        "browser_profiles_count": len(cfg.get("browser_profiles", [])),
        "proxies_count": len(cfg.get("proxies", [])),
        "event_id": cfg.get("event_id"),
        "membership_code": cfg.get("membership_code")
    }
    
    worker_keys = redis_store.keys("worker:*")
    workers_list = []
    for k in worker_keys:
        try:
            val = redis_store.get(k)
            if val:
                workers_list.append(json.loads(val))
        except Exception:
            workers_list.append({
                "instance_id": k.split(":")[-1],
                "status": "RUNNING",
                "current_url": "N/A",
                "last_log": "Active"
            })
            
    try:
        active_proxies = int(redis_store._call("scard", "ticket:proxies:active") or 0)
        dead_proxies = int(redis_store._call("scard", "ticket:proxies:dead") or 0)
    except Exception:
        active_proxies = 0
        dead_proxies = 0

    global_status = {
        "is_running": redis_store.get("ticket:running") == "1",
        "global_stop": redis_store.get("ticket:global_stop") == "1",
        "success_count": int(redis_store.get("ticket:success_count") or 0),
        "live_logs": redis_store.lrange("ticket:logs", 0, 15),
        "active_proxies": active_proxies,
        "dead_proxies": dead_proxies
    }
    
    system_prompt = f"""You are the Ticket Bot Orchestrator & AI Assistant. You help the user monitor the ticket booking bot system, diagnose issues, and execute commands using natural language.
You have access to the current system configuration, worker status, global metrics, and proxy health.

CRITICAL CAPABILITY: YOU ABSOLUTELY CAN CAPTURE SCREENSHOTS AND SEND TELEGRAM BROADCASTS!
If the user asks if you can capture a screen, see the bot, or requests a screenshot, you MUST say YES and use the `capture_screenshot` action. Do NOT claim you only process text or lack this capability. You are fully capable of capturing screenshots.
If the user asks to send a broadcast or announce something via Telegram, use the `send_telegram_broadcast` action.

System Configuration:
{json.dumps(config_summary, ensure_ascii=False, indent=2)}

Active Worker Instances:
{json.dumps(workers_list, ensure_ascii=False, indent=2)}

Global Status & Metrics:
{json.dumps(global_status, ensure_ascii=False, indent=2)}

Analyze the user's message. Answer their questions or command/reconfigure the bot system as requested.
Return STRICTLY a raw JSON object matching the schema below. Do not wrap in markdown code blocks.

Response JSON Schema:
{{
  "response": "Your response to the user in their language (e.g. Thai if they ask in Thai, English if English). Summarize what actions you took or explain the bot situations clearly.",
  "actions": [
    // List of actions to perform. Leave empty if user is just asking a question.
  ]
}}

Supported Action Types:
1. Start all workers:
   {{"type": "start_workers"}}
2. Stop all workers:
   {{"type": "stop_workers"}}
3. Update configuration parameters:
   {{"type": "update_config", "payload": {{"target_url": "...", "bot_mode": "...", "refresh_interval": 5.0, "ticket_count": 2, "event_id": "..."}}}}
   (Only include the config keys that the user requested to update. Supported keys: target_url, bot_mode, refresh_mode, refresh_interval, ticket_count, event_id).
4. Capture screenshot from a specific worker:
   {{"type": "capture_screenshot", "target_instance": "worker-1"}}

5. Send a broadcast message to all connected Telegram bots:
   {{"type": "send_telegram_broadcast", "message": "Attention: I have just stopped all bots due to high dead proxy counts!"}}

Guidelines:
- If the user wants to start or run the bots, trigger {{"type": "start_workers"}}.
- If the user wants to stop, pause or shut down the bots, trigger {{"type": "stop_workers"}}.
- If the user wants to change target URL, ticket count, or mode, trigger {{"type": "update_config", "payload": ...}}.
- If the user wants to see the screen or capture a screenshot of a specific bot (e.g., "แคปหน้าจอ", "ดูหน้าจอบอท 1"), trigger {{"type": "capture_screenshot", "target_instance": "<instance_id>"}}. 
- If the user asks to broadcast or send a message to Telegram, trigger {{"type": "send_telegram_broadcast", "message": "..."}}.
- If the user refers to a bot by index like "bot 1" or "บอท 1", match it with the first worker in the Active Worker Instances list.
- IMPORTANT: Screenshots can only be successfully captured if the target worker is running (not in STANDBY). If the target worker is in STANDBY, you should still trigger the action, but explain in your response that the bot is currently in STANDBY so the screen might not be available or they should start the bot first.
- Respond politely and professionally in the same language the user queried in (primarily Thai).
"""

    gemini_contents = []
    for turn in history:
        gemini_contents.append({
            "role": "user" if turn.get("role") == "user" else "model",
            "parts": [{"text": turn.get("text", "")}]
        })
    gemini_contents.append({
        "role": "user",
        "parts": [{"text": message}]
    })
    
    payload = {
        "systemInstruction": {
            "parts": [{"text": system_prompt}]
        },
        "contents": gemini_contents,
        "generationConfig": {
            "responseMimeType": "application/json"
        }
    }
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-pro:generateContent?key={api_key}"
    
    executed_actions = []
    response_text = ""
    image_url_out = None
    
    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code == 200:
                raw_text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
                result = json.loads(raw_text)
                response_text = result.get("response", "")
                actions = result.get("actions", [])
                
                for action in actions:
                    act_type = action.get("type")
                    if act_type == "start_workers":
                        await start_all()
                        executed_actions.append("Started all workers")
                    elif act_type == "stop_workers":
                        await stop_all()
                        executed_actions.append("Stopped all workers")
                    elif act_type == "update_config":
                        payload_data = action.get("payload", {})
                        if payload_data:
                            # Merge
                            for k, v in payload_data.items():
                                if k in ["refresh_interval", "ticket_count"]:
                                    try:
                                        v = float(v) if k == "refresh_interval" else int(v)
                                    except Exception:
                                        pass
                                cfg[k] = v
                            cfg["_saved_at"] = datetime.now().isoformat()
                            redis_store.set_config(cfg)
                            executed_actions.append(f"Updated config: {payload_data}")
                    elif act_type == "send_telegram_broadcast":
                        msg = action.get("message")
                        if msg:
                            try:
                                import telegram
                                bots_list = cfg.get("telegram_bots", [])
                                if not bots_list and cfg.get("telegram_token"):
                                    bots_list = [{"token": cfg.get("telegram_token"), "chat_id": cfg.get("telegram_chat_id")}]
                                for b in bots_list:
                                    if b.get("token") and b.get("chat_id") and not b.get("token").startswith("YOUR_"):
                                        t_bot = telegram.Bot(token=b["token"])
                                        await t_bot.send_message(chat_id=b["chat_id"], text=f"🤖 <b>AI Orchestrator:</b>\n{msg}", parse_mode="HTML")
                                executed_actions.append(f"Sent Telegram broadcast: {msg}")
                            except Exception as e:
                                executed_actions.append(f"Failed to send Telegram broadcast: {e}")
                    elif act_type == "capture_screenshot":
                        target = action.get("target_instance")
                        if target:
                            import time as time_mod
                            req_id = f"snap_{int(time_mod.time())}"
                            redis_store.set(f"ticket:cmd:screenshot:{target}", req_id, ex=30)
                            executed_actions.append(f"Requested screenshot from {target}")
                            
                            for _ in range(30):
                                await asyncio.sleep(0.5)
                                if redis_store.get(f"ticket:screenshot:{req_id}"):
                                    response_text += f"\n\n📸 (ระบบได้แนบรูปภาพหน้าจอล่าสุดของ {target} มาให้แล้วด้านล่างนี้ครับ)"
                                    image_url_out = f"/api/screenshot/{req_id}"
                                    break
                            else:
                                response_text += f"\n\n⚠️ ร้องขอ Screenshot จาก {target} แล้ว แต่บอทไม่ตอบสนองในเวลาที่กำหนด (อาจจะกำลังโหลดหน้าเว็บอยู่ หรือไม่ได้รัน)"
            else:
                response_text = f"ขออภัยครับ เกิดข้อผิดพลาดในการเชื่อมต่อกับ Gemini API (Status Code: {resp.status_code}): {resp.text}"
    except Exception as e:
        response_text = f"ขออภัยครับ เกิดข้อผิดพลาดในการประมวลผลคำสั่ง: {str(e)}"
        
    return {
        "status": "success",
        "response": response_text,
        "actions": executed_actions,
        "image_url": image_url_out
    }



@app.post("/api/start")
async def start_all():
    redis_store.delete("ticket:global_stop")
    redis_store.set("ticket:command", "start")
    redis_store.set("ticket:running", "1")
    redis_store.append_log(f"[{datetime.now().strftime('%H:%M:%S')}] Dashboard: ▶ START — workers กำลังทำงาน")
    return {"status": "success", "message": "All workers started"}


@app.post("/api/stop")
async def stop_all():
    redis_store.set("ticket:global_stop", "1", ex=7200)
    redis_store.set("ticket:command", "stop")
    redis_store.delete("ticket:running")
    redis_store.append_log(f"[{datetime.now().strftime('%H:%M:%S')}] Dashboard: ⏹ STOP — workers หยุดทำงานแล้ว")
    return {"status": "success", "message": "All workers stopped"}


@app.post("/api/worker/{instance_id}/start")
async def start_worker(instance_id: str):
    redis_store.delete(f"ticket:stop:{instance_id}")
    redis_store.append_log(f"[{datetime.now().strftime('%H:%M:%S')}] Dashboard: ▶ START WORKER {instance_id}")
    return {"status": "success", "message": f"Worker {instance_id} started"}


@app.post("/api/worker/{instance_id}/stop")
async def stop_worker(instance_id: str):
    redis_store.set(f"ticket:stop:{instance_id}", "1")
    redis_store.append_log(f"[{datetime.now().strftime('%H:%M:%S')}] Dashboard: ⏹ STOP WORKER {instance_id}")
    return {"status": "success", "message": f"Worker {instance_id} stopped"}


@app.get("/api/config")
async def get_config():
    return redis_store.get_config()


@app.post("/api/config")
async def set_config(request: Request):
    config = await request.json()
    # Replicate first active bot to root variables for backward compatibility
    bots = config.get("telegram_bots", [])
    if bots:
        first_bot = next((b for b in bots if b.get("enabled", True)), bots[0])
        config["telegram_token"] = first_bot.get("token", "")
        config["telegram_chat_id"] = first_bot.get("chat_id", "")

    # stamp the save time so workers and UI can detect freshness
    config["_saved_at"] = datetime.now().isoformat()
    redis_store.set_config(config)
    redis_store.append_log(
        f"[{datetime.now().strftime('%H:%M:%S')}] Dashboard: config updated "
        f"(profiles={len(config.get('profiles', []))}, proxies={len(config.get('proxies', []))}, telegram_bots={len(bots)})"
    )
    return {"status": "success", "message": "Configuration saved", "saved_at": config["_saved_at"]}


@app.get("/api/telegram/status")
async def get_telegram_status():
    try:
        raw = redis_store.get("ticket:telegram_bot_statuses")
        if raw:
            return json.loads(raw)
    except Exception:
        pass
    return {}


@app.post("/api/telegram/test")
async def test_telegram_bot(request: Request):
    try:
        data = await request.json()
        token = data.get("token")
        chat_id = data.get("chat_id")
        if not token or not chat_id:
            return {"status": "error", "message": "Missing token or chat_id"}
        import telegram
        bot = telegram.Bot(token=token)
        await bot.send_message(
            chat_id=chat_id,
            text=f"🔔 <b>Test Notification</b>\nThis bot connection is working correctly!\nSent from Ticket Bot Dashboard at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            parse_mode="HTML"
        )
        return {"status": "success", "message": "Test message sent successfully"}
    except Exception as e:
        return {"status": "error", "message": f"Failed to send test message: {str(e)}"}


@app.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            logs = redis_store.lrange("ticket:logs", 0, 50)
            try:
                await websocket.send_json({"logs": logs, "timestamp": datetime.now().isoformat()})
            except Exception:
                break
            await asyncio.sleep(1.2)
    except Exception:
        pass


@app.get("/api/screenshot/{req_id}")
async def get_screenshot(req_id: str):
    import base64
    from fastapi.responses import Response
    b64_data = redis_store.get(f"ticket:screenshot:{req_id}")
    if b64_data:
        try:
            image_bytes = base64.b64decode(b64_data)
            return Response(content=image_bytes, media_type="image/jpeg")
        except Exception:
            pass
    return Response(status_code=404, content="Screenshot not found or expired")


@app.post("/api/live/{instance_id}/start")
async def start_live_stream(instance_id: str):
    redis_store.set(f"ticket:live_stream:{instance_id}", "1", ex=30)
    return {"status": "success"}

@app.post("/api/live/{instance_id}/stop")
async def stop_live_stream(instance_id: str):
    redis_store.delete(f"ticket:live_stream:{instance_id}")
    return {"status": "success"}

@app.post("/api/live/{instance_id}/control")
async def live_control(instance_id: str, request: Request):
    try:
        data = await request.json()
        redis_store._call("publish", f"ticket:control:{instance_id}", json.dumps(data))
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/live/{instance_id}/stream")
async def get_live_stream(instance_id: str):
    import base64
    from fastapi.responses import StreamingResponse
    import asyncio
    
    async def generate():
        while True:
            b64_data = redis_store.get(f"ticket:live_frame:{instance_id}")
            if b64_data:
                try:
                    image_bytes = base64.b64decode(b64_data)
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + image_bytes + b'\r\n')
                except Exception:
                    pass
            await asyncio.sleep(0.5)

    return StreamingResponse(generate(), media_type="multipart/x-mixed-replace; boundary=frame")


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8080)
