import os
import json
import redis
import telegram
from typing import Dict, List, Optional

REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")

# Akamai / human-verification gate (ticket login, edge WAF, defense-demo challenge)
DEFAULT_HV_MARKERS = (
    "confirm you're a human",
    "please confirm you're a human",
    "i'm not a robot",
    "im not a robot",
    "not a robot",
    "powered and protected by akamai",
    "akamai bot manager",
)
DEFAULT_HV_ROBOT_TEXTS = (
    "I'm not a robot",
    "I am not a robot",
    "not a robot",
    "ฉันไม่ใช่หุ่นยนต์",
    "ไม่ใช่หุ่นยนต์",
)
DEFAULT_HV_PROCEED_TEXTS = (
    "Proceed",
    "Continue",
    "Submit",
    "Confirm",
    "Complete Challenge",
    "ดำเนินการต่อ",
    "ยืนยัน",
    "ตกลง",
)

QUEUE_CAPTCHA_URL_TPL = "https://www.example-ticket.com/concert/{event_id}"

_tg_bots_cache = {}  # token -> telegram.Bot

def _load_config_from_file() -> dict:
    try:
        with open("config.json") as f:
            return json.load(f)
    except Exception:
        return {}

def _load_config_from_redis(r: redis.Redis) -> Optional[dict]:
    try:
        raw = r.get("ticket:config")
        if raw:
            return json.loads(raw)
    except Exception:
        pass
    return None

def load_config(r: redis.Redis) -> dict:
    cfg = _load_config_from_redis(r)
    if cfg:
        return cfg
    return _load_config_from_file()

def get_tg_bot_instances(config: dict) -> List[tuple[telegram.Bot, str]]:
    global _tg_bots_cache
    bots_list = config.get("telegram_bots", [])
    if not bots_list:
        token = config.get("telegram_token", "")
        chat_id = config.get("telegram_chat_id", "")
        if token and token != "YOUR_TELEGRAM_BOT_TOKEN_HERE" and not token.startswith("YOUR_") and chat_id:
            bots_list = [{
                "token": token,
                "chat_id": chat_id,
                "enabled": True
            }]
            
    results = []
    for b in bots_list:
        if not b.get("enabled", True):
            continue
        t = b.get("token", "").strip()
        c = b.get("chat_id", "").strip()
        if t and c and not t.startswith("YOUR_"):
            if t not in _tg_bots_cache:
                try:
                    _tg_bots_cache[t] = telegram.Bot(token=t)
                except Exception:
                    continue
            results.append((_tg_bots_cache[t], c))
    return results

def get_tg_bot(config: dict) -> Optional[telegram.Bot]:
    instances = get_tg_bot_instances(config)
    if instances:
        return instances[0][0]
    return None
