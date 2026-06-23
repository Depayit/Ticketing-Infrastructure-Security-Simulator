"""
Bot Bypass / Block middleware for the defense-demo gateway.

This is a minimal implementation to make the gateway start and be useful
for testing the TTM bot's defense_funnel + sensor + telemetry flow.

When BOT_BYPASS_BLOCK=true (default in config), the middleware is lenient
on the /api/funnel/* and /api/sensor paths so the bot can exercise the
full purchase funnel without being instantly 403'd.

For GraphQL, the main.py already gates it with GRAPHQL_ENABLED.
"""

from __future__ import annotations

import json
import logging
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from shared.redis_client import r

log = logging.getLogger("bypass_block")

# The response the gateway returns when it decides to block a bot
BLOCK_RESPONSE = {
    "error": "Access Denied",
    "message": "Bot activity detected. Please use the official website.",
    "code": "BOT_BLOCKED",
    "layers": ["edge", "akamai", "fraud"],
}


class BotBypassBlockMiddleware(BaseHTTPMiddleware):
    """
    Lightweight middleware that can short-circuit obviously automated traffic.

    In the current demo setup it mostly passes through (especially when
    BOT_BYPASS_BLOCK is true) so we can actually test the bot code.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path or ""
        method = request.method

        # Always allow health and static-like paths
        if path in ("/health", "/docs", "/openapi.json", "/admin/api/events"):
            return await call_next(request)

        # For the public funnel and sensor endpoints we are intentionally permissive
        # during bot development. Real blocking happens deeper (fraud-engine rules).
        if path.startswith(("/api/funnel", "/api/sensor", "/api/telemetry", "/api/challenge")):
            toggles_raw = r.get("defense:config:toggles")
            toggles = json.loads(toggles_raw) if toggles_raw else {"bot_bypass": True}
            
            if toggles.get("bot_bypass", True):
                # Let it through; the seat-service + fraud-engine will still score it.
                return await call_next(request)
            else:
                return JSONResponse(BLOCK_RESPONSE, status_code=403)

        # GraphQL is handled explicitly in main.py (returns 403 when disabled).
        if path == "/graphql/v2":
            return await call_next(request)

        # Default: proceed normally
        return await call_next(request)
