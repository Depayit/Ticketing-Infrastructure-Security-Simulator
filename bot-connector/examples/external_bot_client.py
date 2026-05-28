#!/usr/bin/env python3
"""ตัวอย่าง Bot ภายนอก — เชื่อมต่อผ่าน Bot Connector"""

from __future__ import annotations

import argparse
import json
import sys
import time

try:
    import httpx
except ImportError:
    print("ติดตั้ง: pip install httpx")
    sys.exit(1)


class TTMConnectorClient:
    def __init__(self, base_url: str, api_key: str = ""):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.bot_id = ""

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["X-API-Key"] = self.api_key
        return h

    def register(self, name: str, description: str = "") -> dict:
        resp = httpx.post(
            f"{self.base_url}/api/v1/register",
            json={"name": name, "description": description},
            timeout=15.0,
        )
        resp.raise_for_status()
        data = resp.json()
        self.api_key = data["bot"]["api_key"]
        self.bot_id = data["bot"]["bot_id"]
        return data

    def sandbox_info(self) -> dict:
        return httpx.get(f"{self.base_url}/api/v1/sandbox/info", timeout=10.0).json()

    def create_session(self, event_id: str = "demo-concert-2026") -> dict:
        resp = httpx.post(
            f"{self.base_url}/api/v1/sessions",
            headers=self._headers(),
            json={"event_id": event_id, "mode": "sandbox"},
            timeout=15.0,
        )
        resp.raise_for_status()
        return resp.json()["session"]

    def graphql(self, session_id: str, query: str, variables: dict | None = None, queue_token: str = "") -> dict:
        resp = httpx.post(
            f"{self.base_url}/api/v1/sessions/{session_id}/graphql",
            headers=self._headers(),
            json={"query": query, "variables": variables or {}, "queue_token": queue_token},
            timeout=30.0,
        )
        return resp.json()

    def simulate_human(self, session_id: str) -> dict:
        resp = httpx.post(
            f"{self.base_url}/api/v1/sessions/{session_id}/telemetry/simulate-human",
            headers=self._headers(),
            json={"duration_sec": 2.5, "seat_hover_count": 8},
            timeout=15.0,
        )
        resp.raise_for_status()
        return resp.json()


QUEUE_QUERY = """
query QueueStatus($eventId: String!) {
  queueStatus(eventId: $eventId) { status token captchaSitekey }
}
"""

ADD_TO_CART = """
mutation AddToCart($input: AddToCartInput!) {
  addToCart(input: $input) { success cartId errorCode }
}
"""


def run_scenario_b(client: TTMConnectorClient, event_id: str) -> None:
    print("\n=== Scenario B: API-only bot ===")
    session = client.create_session(event_id)
    sid = session["session_id"]
    q = client.graphql(sid, QUEUE_QUERY, {"eventId": event_id})
    print("queueStatus:", json.dumps(q, indent=2, ensure_ascii=False))
    token = q.get("data", {}).get("data", {}).get("queueStatus", {}).get("token", "")
    time.sleep(0.3)
    cart = client.graphql(
        sid, ADD_TO_CART,
        {"input": {"eventId": event_id, "ticketType": "GA-B1", "quantity": 1}},
        queue_token=token,
    )
    print("addToCart:", json.dumps(cart, indent=2, ensure_ascii=False))


def run_scenario_c(client: TTMConnectorClient, event_id: str) -> None:
    print("\n=== Scenario C: Human-like bot ===")
    session = client.create_session(event_id)
    sid = session["session_id"]
    client.simulate_human(sid)
    q = client.graphql(sid, QUEUE_QUERY, {"eventId": event_id})
    token = q.get("data", {}).get("data", {}).get("queueStatus", {}).get("token", "")
    time.sleep(1.5)
    cart = client.graphql(
        sid, ADD_TO_CART,
        {"input": {"eventId": event_id, "ticketType": "GA-B1", "quantity": 1}},
        queue_token=token,
    )
    print("addToCart:", json.dumps(cart, indent=2, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--connector", default="http://localhost:8100")
    parser.add_argument("--api-key", default="")
    parser.add_argument("--scenario", choices=["B", "C", "info"], default="info")
    parser.add_argument("--event-id", default="demo-concert-2026")
    args = parser.parse_args()

    client = TTMConnectorClient(args.connector, api_key=args.api_key)
    if not args.api_key:
        reg = client.register(name="External Test Bot", description="CLI example")
        print("Registered:", json.dumps(reg, indent=2, ensure_ascii=False))
        print(f"\nAPI Key: {client.api_key}\n")

    info = client.sandbox_info()
    print("Sandbox:", json.dumps(info.get("health", {}), indent=2))
    if not info.get("health", {}).get("reachable"):
        print("Sandbox ไม่พร้อม — รัน defense-demo ก่อน")
        sys.exit(1)

    if args.scenario == "B":
        run_scenario_b(client, args.event_id)
    elif args.scenario == "C":
        run_scenario_c(client, args.event_id)


if __name__ == "__main__":
    main()
