"""Durable, best-effort Telegram alerts for committed simulated payments."""

import asyncio
import json
import logging
import os

import httpx
from redis.exceptions import ResponseError

from shared.redis_client import r


STREAM = "defense:telegram:payment-alerts"
GROUP = "telegram-payment-alerts"
CONSUMER = "payment-service"
logger = logging.getLogger(__name__)


def configured() -> bool:
    return bool(os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID"))


def queue_payment_alert(order: dict) -> None:
    if not configured():
        return
    payload = {key: order[key] for key in (
        "order_id", "event_id", "seat_id", "quantity", "total_price", "payment_method"
    )}
    try:
        r.xadd(STREAM, {"order": json.dumps(payload, ensure_ascii=False)}, maxlen=10000, approximate=True)
    except Exception:
        # The seat is already committed; Telegram must never turn a successful
        # simulated payment into an HTTP error or cause another seat purchase.
        logger.error("Could not queue Telegram alert for committed order %s", order["order_id"])


def message_text(order: dict) -> str:
    method = {"qr": "QR จำลอง", "credit_card": "บัตรจำลอง"}.get(order["payment_method"], "ชำระเงินจำลอง")
    return ("✅ ชำระเงินสำเร็จ (ระบบจำลอง)\n"
            f"ออเดอร์: {order['order_id']}\n"
            f"อีเวนต์: {order['event_id']}\n"
            f"ที่นั่ง/โซน: {order['seat_id']}\n"
            f"จำนวน: {order['quantity']}\n"
            f"ยอดจำลอง: ฿{order['total_price']:,.0f}\n"
            f"วิธี: {method}\n"
            "ไม่มีการตัดเงินจริง")


async def send_payment_alert(order: dict) -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(f"https://api.telegram.org/bot{token}/sendMessage",
                                     json={"chat_id": chat_id, "text": message_text(order)})
    # Avoid logging the response or exception: API URLs include the bot token.
    if response.status_code != 200 or not response.json().get("ok"):
        raise RuntimeError("Telegram sendMessage was not accepted")


async def delivery_loop() -> None:
    if not configured():
        return
    while True:
        try:
            try:
                await asyncio.to_thread(r.xgroup_create, STREAM, GROUP, id="0", mkstream=True)
            except ResponseError as exc:
                if "BUSYGROUP" not in str(exc):
                    raise
            pending = await asyncio.to_thread(r.xreadgroup, GROUP, CONSUMER, {STREAM: "0"}, count=1)
            messages = pending or await asyncio.to_thread(
                r.xreadgroup, GROUP, CONSUMER, {STREAM: ">"}, count=1, block=3000
            )
            if not messages:
                continue
            for _, entries in messages:
                for message_id, fields in entries:
                    order = json.loads(fields["order"])
                    await send_payment_alert(order)
                    r.xack(STREAM, GROUP, message_id)
                    r.xdel(STREAM, message_id)
                    logger.info("Telegram alert sent for committed order %s", order["order_id"])
        except asyncio.CancelledError:
            raise
        except Exception:
            # Keep the stream entry pending for a later retry. Never log the
            # exception text, which could contain a Telegram URL with its token.
            logger.warning("Telegram alert delivery failed; retrying pending message")
            await asyncio.sleep(30)
