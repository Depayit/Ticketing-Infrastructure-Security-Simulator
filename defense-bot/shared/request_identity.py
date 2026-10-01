"""Stable visitor identity for queue tokens and simulated WAF decisions."""

import os


def client_identity(request) -> str:
    if os.getenv("LAB_ACCESS") == "public":
        visitor_id = getattr(request.state, "visitor_id", "")
        return f"visitor:{visitor_id}" if visitor_id else "visitor:unassigned"
    if os.getenv("LAB_MODE") == "production":
        # Tailscale Serve removes supplied identity headers and adds the
        # authenticated user's login. The gateway listens on localhost only.
        login = request.headers.get("tailscale-user-login")
        if login:
            return f"tailscale:{login}"
        return request.client.host if request.client else "unknown"

    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    return request.client.host if request.client else "unknown"
