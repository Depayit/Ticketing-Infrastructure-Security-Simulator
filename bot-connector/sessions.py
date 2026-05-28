import json
import secrets
import time
from typing import Optional

import redis

SESSION_PREFIX = "connector:session:"
SESSION_LOG_PREFIX = "connector:session_logs:"
SESSION_TTL_SEC = 7200
LOG_MAX = 200


class SessionStore:
    def __init__(self, client: redis.Redis):
        self.client = client

    def create(
        self,
        bot_id: str,
        event_id: str,
        mode: str = "sandbox",
        metadata: Optional[dict] = None,
    ) -> dict:
        session_id = f"sess-{secrets.token_hex(8)}"
        now = time.time()
        record = {
            "session_id": session_id,
            "bot_id": bot_id,
            "event_id": event_id,
            "mode": mode,
            "status": "active",
            "created_at": now,
            "updated_at": now,
            "queue_token": "",
            "cart_id": "",
            "order_id": "",
            "last_error": "",
            "request_count": 0,
            "metadata": metadata or {},
        }
        self.client.set(f"{SESSION_PREFIX}{session_id}", json.dumps(record), ex=SESSION_TTL_SEC)
        return record

    def get(self, session_id: str) -> Optional[dict]:
        raw = self.client.get(f"{SESSION_PREFIX}{session_id}")
        if not raw:
            return None
        return json.loads(raw)

    def update(self, session_id: str, **fields) -> Optional[dict]:
        session = self.get(session_id)
        if not session:
            return None
        session.update(fields)
        session["updated_at"] = time.time()
        self.client.set(f"{SESSION_PREFIX}{session_id}", json.dumps(session), ex=SESSION_TTL_SEC)
        return session

    def close(self, session_id: str) -> Optional[dict]:
        return self.update(session_id, status="closed")

    def increment_requests(self, session_id: str) -> None:
        session = self.get(session_id)
        if not session:
            return
        session["request_count"] = int(session.get("request_count", 0)) + 1
        session["updated_at"] = time.time()
        self.client.set(f"{SESSION_PREFIX}{session_id}", json.dumps(session), ex=SESSION_TTL_SEC)

    def append_log(self, session_id: str, level: str, message: str, detail: Optional[dict] = None) -> None:
        entry = {
            "ts": time.time(),
            "level": level,
            "message": message,
            "detail": detail or {},
        }
        key = f"{SESSION_LOG_PREFIX}{session_id}"
        self.client.lpush(key, json.dumps(entry))
        self.client.ltrim(key, 0, LOG_MAX - 1)
        self.client.expire(key, SESSION_TTL_SEC)

    def get_logs(self, session_id: str, limit: int = 50) -> list[dict]:
        key = f"{SESSION_LOG_PREFIX}{session_id}"
        items = self.client.lrange(key, 0, limit - 1)
        logs = [json.loads(item) for item in items]
        logs.reverse()
        return logs

    def list_for_bot(self, bot_id: str) -> list[dict]:
        keys = self.client.keys(f"{SESSION_PREFIX}*")
        sessions = []
        for key in keys:
            raw = self.client.get(key)
            if not raw:
                continue
            session = json.loads(raw)
            if session.get("bot_id") == bot_id and session.get("status") == "active":
                sessions.append(session)
        sessions.sort(key=lambda s: s.get("updated_at", 0), reverse=True)
        return sessions
