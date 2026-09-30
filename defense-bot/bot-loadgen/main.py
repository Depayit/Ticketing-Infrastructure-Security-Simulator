"""Bounded, local-only synthetic traffic for the Defense Lab."""

import base64
import json
import os
import re
import statistics
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx

BASE_URL = os.getenv("DEFENSE_BASE_URL", "http://gateway:8090").rstrip("/")
if urlparse(BASE_URL).hostname not in {"gateway", "localhost", "127.0.0.1"}:
    raise SystemExit("bot-loadgen only targets the local Defense Lab gateway")

SCENARIOS = {
    "simple_http", "no_sensor", "browser_like", "stealth_browser",
    "full_behavioral", "multi_account", "human_browser",
}
SCENARIO_ORDER = ["simple_http", "no_sensor", "browser_like", "stealth_browser",
                  "full_behavioral", "multi_account", "human_browser"]
PACK_COUNTS = {"small": 1, "medium": 5, "large": 20}
PACK = os.getenv("SCENARIO_PACK", "small")
if PACK not in PACK_COUNTS:
    raise SystemExit("SCENARIO_PACK must be small, medium, or large")
requested_count = int(os.getenv("LOADGEN_COUNT", "0"))
COUNT = min(100, max(1, requested_count or PACK_COUNTS[PACK]))
WORKERS = min(10, COUNT)
selected = os.getenv("LOADGEN_SCENARIOS", "simple_http,no_sensor,browser_like,stealth_browser,full_behavioral,multi_account,human_browser")
SELECTED = [name.strip() for name in selected.split(",") if name.strip()]
if not SELECTED or any(name not in SCENARIOS for name in SELECTED):
    raise SystemExit("invalid LOADGEN_SCENARIOS")


class Actor:
    def __init__(self, scenario, index):
        self.scenario = scenario
        self.index = index
        self.session_id = uuid.uuid4().hex
        self.ip = f"198.18.{SCENARIO_ORDER.index(scenario) + 1}.{index + 1}"
        self.last_request = 0.0
        self.client = httpx.Client(base_url=BASE_URL, timeout=12, trust_env=False,
                                   headers={"x-session-id": self.session_id, "x-forwarded-for": self.ip,
                                            "User-Agent": "DefenseLabLoadgen/1"},
                                   event_hooks={"request": [self.pace_request]})
        self.event_id = "demo-concert-2026"
        self.token = ""
        self.captcha_required = 0
        self.captcha_passed = 0
        self.started = time.monotonic()
        self.admit_ms = None
        self.locked = False
        self.paid = False

    def close(self):
        self.client.close()

    def pace_request(self, request):
        wait = 0.38 - (time.monotonic() - self.last_request)
        if wait > 0:
            time.sleep(wait)
        self.last_request = time.monotonic()

    def sensor(self, signal_count=130):
        payload = base64.b64encode(json.dumps({"signal_count": signal_count,
                                                "fingerprint": self.session_id}).encode()).decode()
        response = self.client.post("/api/sensor", json={"sensor_data": payload,
                                "session_id": self.session_id, "fingerprint": self.session_id})
        response.raise_for_status()
        return response.json()

    def browser_sensor(self, behavioral=False):
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page(extra_http_headers={"x-forwarded-for": self.ip})
            page.goto(BASE_URL + "/login", wait_until="domcontentloaded", timeout=20000)
            page.wait_for_function("window.AkamaiSensor && window.AkamaiSensor.submitSensor", timeout=10000)
            if behavioral:
                for x in (50, 120, 200, 300):
                    page.mouse.move(x, 200)
                    page.wait_for_timeout(250)
                page.mouse.wheel(0, 300)
            result = page.evaluate("window.AkamaiSensor.submitSensor()")
            self.session_id = result["session_id"]
            self.client.headers["x-session-id"] = self.session_id
            for cookie in page.context.cookies():
                if cookie["domain"] in {"gateway", "localhost", "127.0.0.1"}:
                    self.client.cookies.set(cookie["name"], cookie["value"])
            browser.close()
            return result

    def login(self):
        response = self.client.post("/api/auth/login", json={"email": f"lab-{self.scenario}-{self.index}@example.invalid",
                                    "password": "lab-only", "queue_token": self.token})
        response.raise_for_status()

    def captcha(self, position):
        self.captcha_required += 1
        response = self.client.get("/api/captcha/challenge", params={"position": position, "event_id": self.event_id})
        response.raise_for_status()
        data = response.json()
        if not data.get("required"):
            return
        numbers = [int(value) for value in re.findall(r"\d+", data["question"])]
        answer = sum(numbers)
        response = self.client.post("/api/captcha/verify", json={"position": position,
                                    "event_id": self.event_id, "answer": answer})
        response.raise_for_status()
        self.captcha_passed += 1

    def resolve_gate(self, response):
        if response.status_code != 428:
            return False
        gate = response.json()
        if gate.get("status") == "need_login":
            self.login()
        elif gate.get("status") == "need_captcha":
            self.captcha(gate["position"])
        elif gate.get("status") == "need_sensor":
            self.sensor()
        else:
            return False
        return True

    def queue(self, resolve=True):
        for _ in range(40):
            response = self.client.post("/api/funnel/queue-status", json={"eventId": self.event_id, "joinQueue": True})
            if response.status_code in (403, 429):
                return "rate_limited" if response.status_code == 429 else "denied"
            response.raise_for_status()
            state = response.json()["data"]["queueStatus"]
            status = state.get("status")
            if status == "admitted":
                self.token = state["token"]
                self.admit_ms = int((time.monotonic() - self.started) * 1000)
                return "admitted"
            if status == "need_login" and state.get("token"):
                self.token = state["token"]
            if status in {"need_login", "need_captcha", "need_sensor"} and resolve:
                if status == "need_login": self.login()
                elif status == "need_captcha": self.captcha(state.get("position", "queue"))
                else: self.sensor()
                continue
            if status in {"denied", "need_login", "need_captcha", "need_sensor"}:
                return status
            time.sleep(0.25)
        return "waiting_timeout"

    def telemetry(self):
        now = int(time.time() * 1000)
        events = ([{"type": "mousemove", "t": now + i * 30, "x": i * 9, "y": 200} for i in range(35)]
                  + [{"type": "scroll", "t": now + 1100}, {"type": "seat_hover", "t": now + 1200}])
        response = self.client.post("/api/telemetry", json={"session_id": self.session_id,
                                    "token_issued_at": time.time() - 3, "events": events})
        response.raise_for_status()

    def booking(self, behavioral=False):
        if behavioral:
            self.telemetry()
            time.sleep(1.1)
        response = self.client.get(f"/api/seats/{self.event_id}")
        for _ in range(5):
            if not self.resolve_gate(response): break
            response = self.client.get(f"/api/seats/{self.event_id}")
        if response.status_code in (403, 429):
            return "seat_denied"
        response.raise_for_status()
        available = [seat["seatId"] for seat in response.json()["seats"] if seat["status"] == "available"]
        if not available:
            return "sold_out"
        headers = {"x-queueit-token": self.token}
        for _ in range(6):
            response = self.client.post("/api/funnel/add-to-cart", headers=headers,
                                        json={"input": {"eventId": self.event_id, "ticketType": available[0], "quantity": 1}})
            if not self.resolve_gate(response): break
        if response.status_code != 200:
            return "lock_blocked"
        result = response.json().get("data", {}).get("addToCart", {})
        if not result.get("success"):
            return "lock_denied"
        self.locked = True
        return result["cartId"]

    def checkout(self, cart_id):
        headers = {"x-queueit-token": self.token}
        for _ in range(5):
            response = self.client.post("/api/funnel/checkout", headers=headers,
                                        json={"input": {"cartId": cart_id, "queueToken": self.token,
                                         "buyer": {"email": "lab@example.invalid"}, "paymentMethod": "credit_card",
                                         "card": {"number": "4111111111111111"}, "attendees": ["Lab User"]}})
            if not self.resolve_gate(response): break
        if response.status_code != 200:
            return "checkout_blocked"
        result = response.json().get("data", {}).get("checkout", {})
        if result.get("status") == "3ds_required":
            verified = self.client.post("/api/3ds/verify", json={"challenge_id": result["challengeId"],
                                                     "otp": os.getenv("THREE_DS_OTP", "123456")})
            self.paid = verified.status_code == 200 and verified.json().get("success", False)
        else:
            self.paid = result.get("status") == "success"
        return "paid" if self.paid else "payment_failed"


def run_one(scenario, index):
    actor = Actor(scenario, index)
    try:
        config = actor.client.get("/api/event-config")
        if config.is_success:
            actor.event_id = config.json().get("eventId", actor.event_id)
        if scenario in {"no_sensor", "simple_http"}:
            status = actor.queue(resolve=False)
        else:
            if scenario in {"stealth_browser", "human_browser"}:
                actor.browser_sensor(behavioral=scenario == "human_browser")
            else:
                actor.sensor(140 if scenario in {"full_behavioral", "multi_account"} else 110)
            status = actor.queue()
            if status == "admitted" and scenario in {"full_behavioral", "multi_account", "human_browser", "stealth_browser"}:
                cart = actor.booking(behavioral=scenario in {"full_behavioral", "human_browser"})
                status = (actor.checkout(cart) if actor.locked and scenario in {"full_behavioral", "human_browser"}
                          else "locked" if actor.locked else cart)
        return {"scenario": scenario, "index": index, "status": status, "admit_ms": actor.admit_ms,
                "locked": actor.locked, "paid": actor.paid, "captcha_required": actor.captcha_required,
                "captcha_passed": actor.captcha_passed}
    except Exception as exc:
        return {"scenario": scenario, "index": index, "status": "error", "error": str(exc)[:160],
                "admit_ms": actor.admit_ms, "locked": actor.locked, "paid": actor.paid,
                "captcha_required": actor.captcha_required, "captcha_passed": actor.captcha_passed}
    finally:
        actor.close()


def main():
    tasks = [(scenario, index) for scenario in SELECTED for index in range(COUNT)]
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        results = list(pool.map(lambda task: run_one(*task), tasks))
    bots = [row for row in results if row["scenario"] != "human_browser" and row["status"] != "error"]
    humans = [row for row in results if row["scenario"] == "human_browser" and row["status"] != "error"]
    blocked_statuses = {"denied", "rate_limited", "need_sensor", "need_login", "need_captcha", "seat_denied", "lock_blocked", "checkout_blocked"}
    admitted = [row["admit_ms"] for row in results if row["admit_ms"] is not None]
    bot_admit = [row["admit_ms"] for row in bots if row["admit_ms"] is not None]
    human_admit = [row["admit_ms"] for row in humans if row["admit_ms"] is not None]
    locks = sum(row["locked"] for row in results)
    scenario_summary = {}
    for name in SELECTED:
        rows = [row for row in results if row["scenario"] == name]
        completed = [row for row in rows if row["status"] != "error"]
        scenario_summary[name] = {
            "attempted": len(rows), "completed": len(completed),
            "blocked": sum(row["status"] in blocked_statuses for row in completed),
            "admitted": sum(row["admit_ms"] is not None for row in completed),
            "locked": sum(row["locked"] for row in completed),
            "paid": sum(row["paid"] for row in completed),
            "captcha_presented": sum(row["captcha_required"] for row in completed),
            "captcha_passed": sum(row["captcha_passed"] for row in completed),
        }
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(), "pack": PACK, "count_per_scenario": COUNT,
        "results": results, "by_scenario": scenario_summary,
        "bot_block_rate": sum(row["status"] in blocked_statuses for row in bots) / len(bots) if bots else None,
        "synthetic_human_false_positive_rate": sum(row["status"] in blocked_statuses for row in humans) / len(humans) if humans else None,
        "bot_seat_lock_rate": sum(row["locked"] for row in bots) / len(bots) if bots else None,
        "bot_payment_success_rate": sum(row["paid"] for row in bots) / len(bots) if bots else None,
        "harness_errors": sum(row["status"] == "error" for row in results),
        "median_time_to_admit_ms": statistics.median(admitted) if admitted else None,
        "bot_median_time_to_admit_ms": statistics.median(bot_admit) if bot_admit else None,
        "human_median_time_to_admit_ms": statistics.median(human_admit) if human_admit else None,
        "unpaid_hold_rate": sum(row["locked"] and not row["paid"] for row in results) / locks if locks else None,
        "captcha_pass_rate": sum(row["captcha_passed"] for row in results) / max(1, sum(row["captcha_required"] for row in results)),
    }
    out_dir = Path(os.getenv("REPORT_DIR", "/reports"))
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"loadgen-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in summary.items() if key != "results"}, indent=2))
    print(f"report: {out}")


if __name__ == "__main__":
    main()
