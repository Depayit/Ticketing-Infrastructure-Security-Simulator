"""Shared, operator-controlled state for the single active lab event."""

import json
import re
from datetime import date
from urllib.parse import urlparse

from shared.config import DEFAULT_EVENT_ID, DEFAULT_EVENT_NAME
from shared.redis_client import r

SALE_STATUSES = {"open", "paused", "sold_out"}
ZONE_IDS = {"VIP", "RED", "RED_RESTRICTED", "BLUE", "YELLOW", "GREEN", "TEAL"}
EVENTS_KEY = "defense:config:events"
DEFAULT_EVENT = {
    "eventId": DEFAULT_EVENT_ID,
    "eventName": DEFAULT_EVENT_NAME,
    "saleStatus": "open",
    "maxTicketsPerAccount": 4,
    "zones": [
        {"id": "VIP", "name": "VIP (V1-V16)", "price": 7800, "color": "#c084fc", "isRestricted": False},
        {"id": "RED", "name": "Red Zone (A1-A24)", "price": 6800, "color": "#ef4444", "isRestricted": False},
        {"id": "RED_RESTRICTED", "name": "Red (Restricted View)", "price": 6800, "color": "#991b1b", "isRestricted": True},
        {"id": "BLUE", "name": "Blue Zone", "price": 6300, "color": "#3b82f6", "isRestricted": False},
        {"id": "YELLOW", "name": "Yellow/Orange Zone", "price": 5300, "color": "#eab308", "isRestricted": False},
        {"id": "GREEN", "name": "Green Zone", "price": 4300, "color": "#22c55e", "isRestricted": False},
        {"id": "TEAL", "name": "Teal/Light Blue Zone", "price": 3300, "color": "#14b8a6", "isRestricted": False},
    ],
}


def load_event(event_id: str) -> dict | None:
    if event_id == DEFAULT_EVENT_ID:
        raw = r.get("defense:config:event")
        event = json.loads(raw) if raw else DEFAULT_EVENT.copy()
        event.setdefault("saleStatus", "open")
        return event
    raw = r.hget(EVENTS_KEY, event_id)
    return json.loads(raw) if raw else None


def list_events() -> list[dict]:
    events = [load_event(DEFAULT_EVENT_ID)]
    events.extend(json.loads(raw) for raw in r.hvals(EVENTS_KEY))
    return sorted(events, key=lambda event: event["eventName"].casefold())


def save_event(event: dict) -> None:
    if event["eventId"] == DEFAULT_EVENT_ID:
        r.set("defense:config:event", json.dumps(event))
    else:
        r.hset(EVENTS_KEY, event["eventId"], json.dumps(event))


def validate_event_id(event_id: str) -> str:
    if not isinstance(event_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,47}", event_id):
        raise ValueError("eventId must be 3–48 lowercase letters, digits or hyphens")
    return event_id


def sale_status(event_id: str = DEFAULT_EVENT_ID) -> str:
    event = load_event(event_id)
    return event.get("saleStatus", "open") if event else "missing"


def validate_event_update(data: dict) -> dict:
    allowed = {"eventName", "maxTicketsPerAccount", "zones", "saleStatus",
               "venue", "showDate", "officialEventUrl"}
    unknown = set(data) - allowed
    if unknown:
        raise ValueError(f"unknown event fields: {', '.join(sorted(unknown))}")
    result = {}
    for field in ("venue", "showDate", "officialEventUrl"):
        if field not in data:
            continue
        value = data[field]
        if not isinstance(value, str) or len(value) > 500:
            raise ValueError(f"{field} must be a string of at most 500 characters")
        value = value.strip()
        if value:
            if field == "showDate":
                try:
                    date.fromisoformat(value)
                except ValueError as exc:
                    raise ValueError("showDate must be an ISO date") from exc
            elif field == "officialEventUrl":
                try:
                    parsed = urlparse(value)
                    valid = (parsed.scheme == "https" and parsed.hostname in
                             {"www.thaiticketmajor.com", "thaiticketmajor.com", "event.thaiticketmajor.com"}
                             and not parsed.username and not parsed.password and parsed.port in {None, 443})
                except ValueError:
                    valid = False
                if not valid:
                    raise ValueError("officialEventUrl must be an HTTPS ThaiTicketMajor URL")
        result[field] = value
    if "eventName" in data:
        name = data["eventName"]
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 120:
            raise ValueError("eventName must be 1–120 characters")
        result["eventName"] = name.strip()
    if "maxTicketsPerAccount" in data:
        count = data["maxTicketsPerAccount"]
        if type(count) is not int or not 1 <= count <= 10:
            raise ValueError("maxTicketsPerAccount must be between 1 and 10")
        result["maxTicketsPerAccount"] = count
    if "saleStatus" in data:
        if not isinstance(data["saleStatus"], str) or data["saleStatus"] not in SALE_STATUSES:
            raise ValueError("saleStatus must be open, paused, or sold_out")
        result["saleStatus"] = data["saleStatus"]
    if "zones" in data:
        zones = data["zones"]
        if not isinstance(zones, list) or not zones or len(zones) > len(ZONE_IDS):
            raise ValueError("zones must be a nonempty list of supported zones")
        seen = set()
        clean = []
        for zone in zones:
            if not isinstance(zone, dict) or set(zone) != {"id", "name", "price", "color", "isRestricted"}:
                raise ValueError("invalid zone fields")
            zone_id = zone["id"]
            name = zone["name"]
            price = zone["price"]
            color = zone["color"]
            restricted = zone["isRestricted"]
            if not isinstance(zone_id, str) or zone_id not in ZONE_IDS or zone_id in seen:
                raise ValueError("unknown or duplicate zone id")
            if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80:
                raise ValueError("zone name must be 1–80 characters")
            if type(price) is not int or not 0 <= price <= 1000000:
                raise ValueError("zone price must be between 0 and 1000000")
            if not isinstance(color, str) or len(color) != 7 or color[0] != "#" or any(c not in "0123456789abcdefABCDEF" for c in color[1:]):
                raise ValueError("zone color must be a hex color")
            if type(restricted) is not bool:
                raise ValueError("isRestricted must be a boolean")
            seen.add(zone_id)
            clean.append({"id": zone_id, "name": name.strip(), "price": price, "color": color, "isRestricted": restricted})
        result["zones"] = clean
    return result
