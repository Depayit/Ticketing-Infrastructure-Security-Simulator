import json
import hashlib
import time
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.events import log_event
from shared.redis_client import r
from shared.config import EDGE_DDOS_GLOBAL_RPS


class EdgeCDNMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "unknown").split(",")[0].strip()
        key = f"defense:edge:rps:{int(time.time())}"
        count = r.incr(key)
        if count == 1:
            r.expire(key, 2)
        if count > EDGE_DDOS_GLOBAL_RPS:
            log_event("edge", "global_rps_blocked", "", ip, {"rps": count}, blocked=True)
            return JSONResponse({"error": "EDGE_RATE_LIMITED"}, status_code=429)
        response = await call_next(request)
        zone = int(hashlib.sha256(ip.encode()).hexdigest()[:4], 16) % 3 + 1
        response.headers["X-CDN-Edge"] = "defense-lab-bkk"
        response.headers["X-Cache-Status"] = "BYPASS"
        response.headers["X-AZ-Zone"] = f"az-bkk-{zone}"
        response.headers["X-Defense-Lab"] = "simulated"
        return response

DATACENTER_KEYWORDS = [
    "amazon", "aws", "google", "cloudflare", "microsoft", "azure",
    "digitalocean", "linode", "vultr", "ovh", "hetzner", "oracle cloud",
]

RATE_LIMITS = {
    "graphql": (60, 60),
    "checkout": (10, 60),
}


def is_datacenter(isp: str) -> bool:
    low = (isp or "").lower()
    return any(k in low for k in DATACENTER_KEYWORDS)


class WAFMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        toggles_raw = r.get("defense:config:toggles")
        toggles = json.loads(toggles_raw) if toggles_raw else {"waf": True}
        
        if not toggles.get("waf", True):
            return await call_next(request)

        ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "unknown")
        if "," in ip:
            ip = ip.split(",")[0].strip()

        if r.get(f"defense:ban:{ip}"):
            log_event("ip", "ip_banned", "", ip, blocked=True)
            return JSONResponse({"error": "IP_BANNED"}, status_code=403)

        isp = request.headers.get("x-isp", "")
        if is_datacenter(isp):
            log_event("ip", "datacenter_blocked", "", ip, {"isp": isp}, blocked=True)
            return JSONResponse({"error": "DATACENTER_BLOCKED"}, status_code=403)

        burst_key = f"defense:burst:{ip}"
        burst = r.incr(burst_key)
        if burst == 1:
            r.expire(burst_key, 5)
        if burst > 15:
            r.setex(f"defense:ban:{ip}", 60, "1")
            log_event("ip", "burst_blocked", "", ip, {"burst": burst}, blocked=True)
            return JSONResponse({"error": "RATE_LIMIT_BURST"}, status_code=429)

        path = request.url.path
        bucket = "graphql" if "/graphql" in path else "checkout" if "checkout" in path else None
        if bucket:
            limit, window = RATE_LIMITS[bucket]
            rk = f"defense:ratelimit:{ip}:{bucket}"
            count = r.incr(rk)
            if count == 1:
                r.expire(rk, window)
            if count > limit:
                log_event("ip", "rate_limited", "", ip, {"bucket": bucket}, blocked=True)
                return JSONResponse({"error": "RATE_LIMITED"}, status_code=429)

        token = request.headers.get("x-queueit-token")
        if token and request.method == "POST":
            import hashlib
            h = hashlib.sha256(token.encode()).hexdigest()[:16]
            meta_raw = r.get(f"defense:token:{h}")
            if meta_raw:
                meta = json.loads(meta_raw)
                if meta.get("ip") and meta["ip"] != ip:
                    log_event("ip", "token_ip_mismatch", "", ip, blocked=True)
                    return JSONResponse({"error": "TOKEN_IP_MISMATCH"}, status_code=403)

        return await call_next(request)
