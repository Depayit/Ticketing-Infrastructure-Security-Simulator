"""HTTP Basic protection for the lab control room and its write APIs."""

import binascii
import hmac
import os
from base64 import b64decode
from urllib.parse import urlsplit

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

ADMIN_USER = os.getenv("LAB_ADMIN_USER", "admin")
ADMIN_PASSWORD = os.getenv("LAB_ADMIN_PASSWORD", "")
if os.getenv("LAB_MODE") == "production" and not ADMIN_PASSWORD:
    raise RuntimeError("LAB_ADMIN_PASSWORD is required in production")


def admin_path(request: Request) -> bool:
    path = request.url.path
    return (path in ("/admin", "/static/admin.html") or path.startswith("/admin/api/")
            or (request.method != "GET" and path in ("/api/event-config", "/api/defense-toggles")))


async def admin_auth(request: Request, call_next):
    if ADMIN_PASSWORD and admin_path(request):
        auth = request.headers.get("authorization", "")
        try:
            scheme, encoded = auth.split(" ", 1)
            user, password = b64decode(encoded, validate=True).decode("utf-8").split(":", 1)
        except (ValueError, UnicodeError, binascii.Error):
            scheme, user, password = "", "", ""
        if (scheme.lower() != "basic" or not hmac.compare_digest(user.encode(), ADMIN_USER.encode())
                or not hmac.compare_digest(password.encode(), ADMIN_PASSWORD.encode())):
            return Response(status_code=401, headers={"WWW-Authenticate": 'Basic realm="Defense Lab Admin"', "Cache-Control": "no-store"})
        if request.method not in ("GET", "HEAD"):
            origin = request.headers.get("origin")
            host = request.headers.get("host", "")
            if origin and urlsplit(origin).netloc != host:
                return JSONResponse({"detail": "cross-origin admin write denied"}, status_code=403)
            if request.headers.get("sec-fetch-site") == "cross-site":
                return JSONResponse({"detail": "cross-site admin write denied"}, status_code=403)
    response = await call_next(request)
    if admin_path(request):
        response.headers["Cache-Control"] = "no-store"
    return response
