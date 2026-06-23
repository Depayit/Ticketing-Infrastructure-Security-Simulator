import json
from datetime import datetime
from typing import Optional, List
import redis
import telegram
from core.config import get_tg_bot_instances

def send_log_sync(
    r: redis.Redis,
    instance_id: str,
    worker_key: str,
    message: str,
    level: str,
    config: dict,
    update_status_func
) -> str:
    log_line = f"[{datetime.now().strftime('%H:%M:%S')}] [{level}] [{instance_id}] {message}"
    print(log_line)
    try:
        r.lpush("ttm:logs", log_line)
        r.ltrim("ttm:logs", 0, 100)
    except Exception:
        pass
    return log_line

async def send_log_async(
    r: redis.Redis,
    instance_id: str,
    message: str,
    level: str,
    config: dict
):
    if level in ["SUCCESS", "ERROR", "WARN", "ALERT"]:
        try:
            bot_instances = get_tg_bot_instances(config)
            for bot, chat_id in bot_instances:
                try:
                    emoji_prefix = ""
                    if not any(e in message for e in ["✅", "❌", "⚠️", "🚨", "🎯", "🤖"]):
                        if level == "SUCCESS": emoji_prefix = "✅ "
                        elif level == "ERROR": emoji_prefix = "❌ "
                        elif level == "WARN": emoji_prefix = "⚠️ "
                        elif level == "ALERT": emoji_prefix = "🔔 "
                        
                    await bot.send_message(
                        chat_id=chat_id,
                        text=f"{emoji_prefix}<b>[{instance_id}]</b> {message}",
                        parse_mode="HTML",
                    )
                except Exception:
                    pass
        except Exception:
            pass

def update_status_in_redis(
    r: redis.Redis,
    worker_key: str,
    heartbeat_ttl: int,
    instance_id: str,
    status: str,
    current_url: str,
    last_log: str,
    proxy: str,
    viewport_width: int = 1920,
    viewport_height: int = 1080
):
    status_data = {
        "instance_id": instance_id,
        "status": status,
        "current_url": current_url,
        "last_log": last_log,
        "proxy": proxy,
        "viewport_width": viewport_width,
        "viewport_height": viewport_height,
        "updated_at": datetime.now().isoformat()
    }
    try:
        r.setex(worker_key, heartbeat_ttl, json.dumps(status_data))
    except Exception:
        pass
