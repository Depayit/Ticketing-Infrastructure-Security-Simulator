"""Payment alerts are emitted only after a seat and order are committed."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "payment-service"))

import main as payment
import telegram_notify


class TelegramPaymentTests(unittest.TestCase):
    def setUp(self):
        self.cart = {"event_id": "lab-show", "seat_id": "VIP-1", "quantity": 2,
                     "total_price": 1500, "buyer_email": "buyer@example.com"}

    def test_alert_follows_successful_commit_only(self):
        with patch.object(payment, "commit_hold", return_value=True), \
             patch.object(payment, "queue_payment_alert") as alert:
            order_id = payment._commit_order(self.cart, "cart-1", "session-1", "visitor:one",
                                             ["Guest"], "qr")
        self.assertTrue(order_id.startswith("ORD-"))
        alert.assert_called_once()
        order = alert.call_args.args[0]
        self.assertEqual(order["order_id"], order_id)
        self.assertEqual(order["payment_method"], "qr")

        with patch.object(payment, "commit_hold", return_value=False), \
             patch.object(payment, "queue_payment_alert") as alert, \
             patch.object(payment, "log_event"):
            with self.assertRaises(HTTPException):
                payment._commit_order(self.cart, "cart-2", "session-2", "visitor:two",
                                      ["Guest"], "credit_card")
            alert.assert_not_called()

    def test_alert_is_safe_and_enqueue_failure_does_not_fail_payment(self):
        order = {"order_id": "ORD-TEST", "event_id": "lab-show", "seat_id": "VIP-1",
                 "quantity": 2, "total_price": 1500, "payment_method": "credit_card",
                 "buyer_email": "buyer@example.com", "session_id": "session-1"}
        with patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "test-token", "TELEGRAM_CHAT_ID": "123"}), \
             patch.object(telegram_notify, "r") as redis:
            telegram_notify.queue_payment_alert(order)
            self.assertEqual(redis.xadd.call_count, 1)
            self.assertNotIn("buyer@example.com", str(redis.xadd.call_args))
            redis.xadd.side_effect = RuntimeError("Redis unavailable")
            telegram_notify.queue_payment_alert(order)
        text = telegram_notify.message_text(order)
        self.assertIn("ORD-TEST", text)
        self.assertIn("ระบบจำลอง", text)
        self.assertNotIn("buyer@example.com", text)


if __name__ == "__main__":
    unittest.main()
