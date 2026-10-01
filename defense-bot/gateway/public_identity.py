"""Issue a stable, signed visitor ID for the public simulator."""

import hashlib
import hmac
import os
import re
import secrets


COOKIE_NAME = "__Host-defense_vid"
COOKIE_AGE_SECONDS = 30 * 24 * 60 * 60
_TOKEN_RE = re.compile(r"^[0-9a-f]{32}$")


def _key() -> bytes:
    password = os.environ.get("LAB_ADMIN_PASSWORD", "")
    if not password:
        raise RuntimeError("LAB_ADMIN_PASSWORD is required for public visitor IDs")
    return hmac.new(password.encode(), b"defense-public-visitor-v1", hashlib.sha256).digest()


def _sign(token: str) -> str:
    return hmac.new(_key(), token.encode(), hashlib.sha256).hexdigest()


def valid_visitor(cookie: str) -> str:
    if len(cookie) != 97:
        return ""
    token, separator, signature = cookie.partition(".")
    if not separator or not _TOKEN_RE.fullmatch(token) or not re.fullmatch(r"[0-9a-f]{64}", signature):
        return ""
    return token if hmac.compare_digest(_sign(token), signature) else ""


async def public_visitor(request, call_next):
    if os.getenv("LAB_ACCESS") != "public":
        return await call_next(request)

    token = valid_visitor(request.cookies.get(COOKIE_NAME, ""))
    issued = not token
    if issued:
        token = secrets.token_hex(16)
    request.state.visitor_id = token
    response = await call_next(request)
    if issued:
        response.set_cookie(COOKIE_NAME, f"{token}.{_sign(token)}", max_age=COOKIE_AGE_SECONDS,
                            secure=True, httponly=True, samesite="lax", path="/")
    return response
