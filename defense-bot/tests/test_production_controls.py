"""Guards that must hold before the lab is reachable by testers."""

import asyncio
import base64
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from starlette.requests import Request
from starlette.responses import Response

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gateway import admin_auth as gateway
from gateway.public_identity import COOKIE_NAME, public_visitor, valid_visitor
from shared import event_state
from shared.event_state import validate_event_update
from shared.request_identity import client_identity


def request(path, method="GET", auth="", origin=""):
    headers = [(b"host", b"lab.example")]
    if auth:
        headers.append((b"authorization", auth.encode()))
    if origin:
        headers.append((b"origin", origin.encode()))
    return Request({"type": "http", "method": method, "path": path,
                    "scheme": "https", "headers": headers, "query_string": b""})


async def allowed(_request):
    return Response(status_code=204)


class ProductionControlsTests(unittest.TestCase):
    def test_admin_and_write_apis_require_credentials(self):
        with patch.object(gateway, "ADMIN_PASSWORD", "secret"), patch.object(gateway, "ADMIN_USER", "operator"):
            for path, method in (("/admin", "GET"), ("/static/admin.html", "GET"),
                                 ("/admin/api/reset-seats", "POST"),
                                 ("/api/event-config", "POST"), ("/api/defense-toggles", "POST")):
                response = asyncio.run(gateway.admin_auth(request(path, method), allowed))
                self.assertEqual(response.status_code, 401, path)
            response = asyncio.run(gateway.admin_auth(request("/api/event-config"), allowed))
            self.assertEqual(response.status_code, 204)

    def test_admin_write_rejects_cross_origin(self):
        auth = "Basic " + base64.b64encode(b"operator:secret").decode()
        with patch.object(gateway, "ADMIN_PASSWORD", "secret"), patch.object(gateway, "ADMIN_USER", "operator"):
            response = asyncio.run(gateway.admin_auth(request("/api/event-config", "POST", auth, "https://other.example"), allowed))
            self.assertEqual(response.status_code, 403)
            response = asyncio.run(gateway.admin_auth(request("/api/event-config", "POST", auth, "https://lab.example"), allowed))
            self.assertEqual(response.status_code, 204)

    def test_event_config_rejects_unknown_zone_and_invalid_status(self):
        with self.assertRaises(ValueError):
            validate_event_update({"saleStatus": "anything"})
        with self.assertRaises(ValueError):
            validate_event_update({"zones": [{"id": "OTHER", "name": "Other", "price": 1,
                                               "color": "#123456", "isRestricted": False}]})

    def test_production_identity_ignores_caller_forwarded_ip(self):
        req = Request({"type": "http", "method": "GET", "path": "/", "scheme": "https",
                       "headers": [(b"x-forwarded-for", b"1.2.3.4"),
                                   (b"tailscale-user-login", b"tester@example.com")],
                       "client": ("172.18.0.1", 1234), "query_string": b""})
        with patch.dict("os.environ", {"LAB_MODE": "production", "LAB_ACCESS": "private"}):
            self.assertEqual(client_identity(req), "tailscale:tester@example.com")
        no_identity = Request({"type": "http", "method": "GET", "path": "/", "scheme": "https",
                               "headers": [(b"x-forwarded-for", b"1.2.3.4")],
                               "client": ("172.18.0.1", 1234), "query_string": b""})
        with patch.dict("os.environ", {"LAB_MODE": "production", "LAB_ACCESS": "private"}):
            self.assertEqual(client_identity(no_identity), "172.18.0.1")

    def test_public_visitors_get_distinct_signed_identities(self):
        async def identity_response(req):
            response = Response(client_identity(req))
            return response

        with patch.dict("os.environ", {"LAB_MODE": "production", "LAB_ACCESS": "public",
                                           "LAB_ADMIN_PASSWORD": "test-password"}):
            first = request("/events")
            first_response = asyncio.run(public_visitor(first, identity_response))
            cookie = first_response.headers["set-cookie"].split(";", 1)[0].split("=", 1)[1]
            self.assertTrue(valid_visitor(cookie))
            self.assertIn("Secure", first_response.headers["set-cookie"])
            self.assertIn("HttpOnly", first_response.headers["set-cookie"])
            self.assertEqual(first_response.body.decode(), f"visitor:{valid_visitor(cookie)}")

            second = request("/events")
            second_response = asyncio.run(public_visitor(second, identity_response))
            self.assertNotEqual(first_response.body, second_response.body)

            repeated = request("/events")
            repeated.scope["headers"].append((b"cookie", f"{COOKIE_NAME}={cookie}".encode()))
            repeated.scope["headers"].extend([(b"tailscale-user-login", b"spoofed@example.com"),
                                               (b"x-forwarded-for", b"1.2.3.4")])
            repeated_response = asyncio.run(public_visitor(repeated, identity_response))
            self.assertEqual(repeated_response.body, first_response.body)
            self.assertNotIn("set-cookie", repeated_response.headers)
            self.assertFalse(valid_visitor(cookie[:-1] + ("0" if cookie[-1] != "0" else "1")))

    def test_events_have_independent_sale_status(self):
        class RedisStub:
            def get(self, _key):
                return None

            def hget(self, _key, event_id):
                return json.dumps({"eventId": event_id, "eventName": "Other",
                                   "saleStatus": "paused", "zones": [{"price": 100}]}).encode() if event_id == "other-show" else None

            def hvals(self, _key):
                return [self.hget("", "other-show")]

        with patch.object(event_state, "r", RedisStub()):
            self.assertEqual(event_state.sale_status(), "open")
            self.assertEqual(event_state.sale_status("other-show"), "paused")
            self.assertEqual(event_state.sale_status("missing-show"), "missing")
            self.assertEqual(len(event_state.list_events()), 2)
        with self.assertRaises(ValueError):
            event_state.validate_event_id("../bad")


if __name__ == "__main__":
    unittest.main()
