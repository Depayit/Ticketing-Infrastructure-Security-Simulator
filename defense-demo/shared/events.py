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


def clear_all_defense_data() -> Dict[str, Any]:
    keys = r.keys("defense:*")
    if keys:
        r.delete(*keys)
    # Re-initialize seats to available after clearing
    _reinit_all_seats()
    return {"status": "ok", "deleted_keys": len(keys), "seats_reset": True}


def reset_seats_and_sessions() -> Dict[str, Any]:
    """Reset only seats, carts, sessions, telemetry, and bans — keep audit logs."""
    patterns = [
        "defense:seat:*",
        "defense:cart:*",
        "defense:sensor:*",
        "defense:telemetry:*",
        "defense:bm_sv:*",
        "defense:token:*",
        "defense:challenge_ok:*",
        "defense:ban:*",
        "defense:queue:*",
    ]
    deleted = 0
    for pattern in patterns:
        keys = r.keys(pattern)
        if keys:
            r.delete(*keys)
            deleted += len(keys)
    # Re-initialize seats to available
    _reinit_all_seats()
    return {"status": "ok", "deleted_keys": deleted, "seats_reset": True}


def _reinit_all_seats() -> None:
    """Force all seats back to 'available' in Redis."""
    import json as _json
    default_event_id = "demo-concert-2026"
    default_seats = ["VIP-A1", "VIP-A2", "GA-B1", "GA-B2", "STAND-C1", "STAND-C2"]
    for seat in default_seats:
        key = f"defense:seat:{default_event_id}:{seat}"
        r.set(key, _json.dumps({"status": "available", "session_id": "", "cart_id": ""}))


def summarize_audit_events(events: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    if not events:
        events = get_audit_events(500)
    total = len(events)
    by_layer = {}
    blocked_count = 0
    for ev in events:
        layer = ev.get("layer", "unknown")
        by_layer[layer] = by_layer.get(layer, 0) + 1
        if ev.get("blocked"):
            blocked_count += 1
    return {
        "total": total,
        "by_layer": by_layer,
        "blocked": blocked_count,
        "passed": total - blocked_count,
    }
