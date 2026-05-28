import json
import time
from typing import Any, Dict, List, Optional

from shared.redis_client import r

AUDIT_KEY = "defense:audit:events"
AUDIT_MAX = 500


def log_event(
    layer: str,
    action: str,
    session_id: str = "",
    ip: str = "",
    detail: Optional[Dict[str, Any]] = None,
    blocked: bool = False,
) -> None:
    entry = {
        "ts": time.time(),
        "layer": layer,
        "action": action,
        "session_id": session_id,
        "ip": ip,
        "blocked": blocked,
        "detail": detail or {},
    }
    r.lpush(AUDIT_KEY, json.dumps(entry))
    r.ltrim(AUDIT_KEY, 0, AUDIT_MAX - 1)


def get_audit_events(limit: int = 100) -> List[Dict[str, Any]]:
    raw = r.lrange(AUDIT_KEY, 0, limit - 1)
    return [json.loads(x) for x in raw]
