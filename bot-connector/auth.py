import hashlib
import json
import secrets
import time
from typing import Optional

import redis

BOT_PREFIX = "connector:bot:"
APIKEY_PREFIX = "connector:apikey:"
BOT_TTL_SEC = 3600


def _hash_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode()).hexdigest()


class BotRegistry:
    def __init__(self, client: redis.Redis):
        self.client = client

    def register(self, name: str, description: str = "") -> dict:
        bot_id = f"ext-{secrets.token_hex(6)}"
        api_key = f"ttm_{secrets.token_urlsafe(24)}"
        now = time.time()
        record = {
            "bot_id": bot_id,
            "name": name,
            "description": description,
            "created_at": now,
            "last_seen": now,
            "status": "registered",
            "sessions_total": 0,
        }
        pipe = self.client.pipeline()
        pipe.set(f"{BOT_PREFIX}{bot_id}", json.dumps(record))
        pipe.set(f"{APIKEY_PREFIX}{_hash_key(api_key)}", bot_id)
        pipe.execute()
        return {"bot_id": bot_id, "api_key": api_key, **record}

    def resolve_bot_id(self, api_key: str) -> Optional[str]:
        return self.client.get(f"{APIKEY_PREFIX}{_hash_key(api_key)}")

    def get_bot(self, bot_id: str) -> Optional[dict]:
        raw = self.client.get(f"{BOT_PREFIX}{bot_id}")
        if not raw:
            return None
        return json.loads(raw)

    def heartbeat(self, bot_id: str, status: str = "online", meta: Optional[dict] = None) -> Optional[dict]:
        bot = self.get_bot(bot_id)
        if not bot:
            return None
        bot["last_seen"] = time.time()
        bot["status"] = status
        if meta:
            bot["meta"] = meta
        self.client.set(f"{BOT_PREFIX}{bot_id}", json.dumps(bot), ex=BOT_TTL_SEC)
        return bot

    def increment_sessions(self, bot_id: str) -> None:
        bot = self.get_bot(bot_id)
        if not bot:
            return
        bot["sessions_total"] = int(bot.get("sessions_total", 0)) + 1
        self.client.set(f"{BOT_PREFIX}{bot_id}", json.dumps(bot), ex=BOT_TTL_SEC)

    def list_bots(self) -> list[dict]:
        keys = self.client.keys(f"{BOT_PREFIX}*")
        bots = []
        for key in keys:
            raw = self.client.get(key)
            if raw:
                bots.append(json.loads(raw))
        bots.sort(key=lambda b: b.get("last_seen", 0), reverse=True)
        return bots
