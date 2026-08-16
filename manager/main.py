from pathlib import Path
from collections import deque
from fastapi import FastAPI, WebSocket, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import redis
import asyncio
import uvicorn
import json
from datetime import datetime
import os
import hmac
import uuid

app = FastAPI(title="Adversary Emulation Lab Dashboard")
REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")
BASE_DIR = Path(__file__).resolve().parent

# Admin / operator configuration
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN")  # Must be set by operator for production
DEV_MODE = os.environ.get("DEV_MODE", "false").lower() == "true"
ALLOWED_ORIGINS = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "").split(",") if o.strip()]


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
            "ticket_pr...
