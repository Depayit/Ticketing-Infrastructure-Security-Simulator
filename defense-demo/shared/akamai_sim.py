"""
Minimal Akamai simulation for the defense-demo stack.

This is a stub implementation to make the gateway runnable.
It is intentionally permissive for local testing of the Ticket bot.

The real production Akamai is opaque and cryptographic.
Here we just parse the synthetic payloads the bot sends in defense_funnel mode.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
from typing import Any, Dict, Optional, Tuple

log = logging.getLogger("akamai_sim")


def cookie_hash_from_abck(abck: Optional[str]) -> str:
    """Return a stable hash used as key for sensor binding in the demo."""
    if not abck:
        return "no-abck"
    return hashlib.sha256(abck.encode()).hexdigest()[:16]


def decode_sensor_payload(sensor_data: str, cookie_hash: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Decode the sensor payload sent by the bot.

    In defense_funnel + defense_demo mode, the bot sends base64(JSON) containing
    at minimum "signal_count" and some fingerprint fields.

    Returns (signals_dict, error) where signals_dict has at least "signal_count".
    """
    if not sensor_data:
        return None, "empty sensor_data"

    raw = sensor_data.strip()

    # Try direct base64 decode first (the main path used by our bot)
    try:
        decoded = base64.b64decode(raw, validate=False)
        payload = json.loads(decoded)
        if isinstance(payload, dict) and ("signal_count" in payload or "fingerprint" in payload):
            # Normalize
            payload.setdefault("signal_count", 120)
            return payload, None
    except Exception:
        pass

    # Fallback: the gateway itself sometimes does base64(raw json) when sensor_data missing
    try:
        payload = json.loads(raw)
        if isinstance(payload, dict):
            payload.setdefault("signal_count", 80)
            return payload, None
    except Exception:
        pass

    # Last resort: treat as opaque, assign a medium score
    return {"signal_count": 60, "raw": raw[:200]}, None


def compute_bot_score(signals: Dict[str, Any]) -> int:
    """
    Very simple scoring for the demo.

    Higher signal_count → lower (better) bot score.
    The fraud engine and gateway use thresholds:
      - >= 55  → challenged
      - >= 75  → blocked in some paths
    """
    if not signals:
        return 85

    count = int(signals.get("signal_count", 40))

    # Tuned so that the bot's default 140 signals gives ~18-25 score
    score = max(5, 95 - int(count * 0.55))

    # Add a little noise based on other signals if present
    if signals.get("canvas_hash"):
        score -= 3
    if signals.get("audio_hash"):
        score -= 2

    return max(0, min(100, score))

def format_abck(status: int, session_id: str, fingerprint: str, sensor_ok: bool = True) -> str:
    """Create a fake _abck cookie value for the demo."""
    # The real format is much more complex. This is good enough for the demo gateway.
    h = hashlib.md5(f"{session_id}:{fingerprint}".encode()).hexdigest()[:16]
    return f"{h}~{status}~0~0~1~||-1"


def format_ak_bmsc(session_id: str) -> str:
    return hashlib.sha256(session_id.encode()).hexdigest()[:24]


# Optional helpers the gateway might call
def get_sensor_meta(session_id: str) -> Dict[str, Any]:
    # Placeholder; real impl would read from Redis in some setups
    return {}

