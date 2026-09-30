"""Redis integration tests; run against the dedicated test DB 15."""

import os
import sys
import time
import unittest
import uuid
from pathlib import Path

import redis

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "queue-service"))

from shared import redis_client, seat_state
import admission


class RedisLabTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        url = os.getenv("TEST_REDIS_URL", "redis://localhost:6379/15")
        if not url.endswith("/15"):
            raise RuntimeError("integration tests require Redis DB 15")
        cls.redis = redis.from_url(url, decode_responses=True)
        cls.redis.ping()
        redis_client.r = cls.redis
        seat_state.r = cls.redis
        admission.r = cls.redis

    def test_atomic_hold_commit_and_owner_check(self):
        event, seat, session = uuid.uuid4().hex, "VIP", uuid.uuid4().hex
        cart_a, cart_b = uuid.uuid4().hex, uuid.uuid4().hex
        payload = {"event_id": event, "seat_id": seat, "session_id": session}
        self.assertEqual(seat_state.lock_hold(event, seat, cart_a, session, "127.0.0.1", payload, 20), "locked")
        self.assertEqual(seat_state.lock_hold(event, seat, cart_b, session, "127.0.0.1", payload, 20), "unavailable")
        self.assertFalse(seat_state.release_hold(event, seat, cart_b))
        order = {"order_id": uuid.uuid4().hex, "session_id": session}
        self.assertTrue(seat_state.commit_hold(event, seat, cart_a, order))
        self.assertEqual(seat_state.read_seat(event, seat)["status"], "sold")
        self.assertFalse(seat_state.commit_hold(event, seat, cart_a, order))

    def test_expired_hold_releases_and_counts_abuse(self):
        event, seat, session = uuid.uuid4().hex, "RED", uuid.uuid4().hex
        cart = uuid.uuid4().hex
        payload = {"event_id": event, "seat_id": seat, "session_id": session}
        self.assertEqual(seat_state.lock_hold(event, seat, cart, session, "127.0.0.1", payload, 1), "locked")
        time.sleep(1.1)
        self.assertEqual(seat_state.read_seat(event, seat)["status"], "available")
        self.assertGreaterEqual(int(self.redis.get(f"defense:abuse:session:{session}") or 0), 1)

    def test_priority_admits_lower_bot_score_first(self):
        event = uuid.uuid4().hex
        first = uuid.uuid4().hex
        high = uuid.uuid4().hex
        low = uuid.uuid4().hex
        while time.time() % 1 > 0.15:
            time.sleep(0.02)
        self.assertTrue(admission.admission(event, first, 50, "priority_score", rate=1)[0])
        self.assertFalse(admission.admission(event, high, 80, "priority_score", rate=1)[0])
        self.assertFalse(admission.admission(event, low, 10, "priority_score", rate=1)[0])
        time.sleep(1.1)
        self.assertFalse(admission.admission(event, high, 80, "priority_score", rate=1)[0])
        self.assertTrue(admission.admission(event, low, 10, "priority_score", rate=1)[0])


if __name__ == "__main__":
    unittest.main()
