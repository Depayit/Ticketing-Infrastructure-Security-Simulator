"""Configure private-chat payment alerts without putting the bot token in shell history."""

import getpass
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from urllib.request import Request, urlopen


BOT_DIR = Path(__file__).resolve().parents[1]
ENV_FILE = BOT_DIR / ".env.production"


def telegram_call(token: str, method: str, payload: dict) -> dict:
    url = f"https://api.telegram.org/bot{token}/{method}"
    request = Request(url, data=json.dumps(payload).encode(),
                      headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(request, timeout=12) as response:
            result = json.load(response)
        if not result.get("ok"):
            raise ValueError("Telegram rejected the request")
        return result["result"]
    except Exception:
        # URL and HTTP errors may contain the token. Never print them.
        raise SystemExit(f"Telegram {method} failed; check the token and bot chat, then retry") from None


def private_chats(updates: list) -> dict[str, str]:
    chats = {}
    for update in updates:
        message = update.get("message") or update.get("edited_message") or {}
        chat = message.get("chat") or {}
        if chat.get("type") == "private" and "id" in chat:
            label = chat.get("username") or chat.get("first_name") or "private chat"
            chats[str(chat["id"])] = str(label)
    return chats


def save_settings(token: str, chat_id: str) -> None:
    if not ENV_FILE.exists() or os.stat(ENV_FILE).st_mode & 0o077:
        raise SystemExit(".env.production is missing or not owner-only")
    lines = [line for line in ENV_FILE.read_text().splitlines()
             if not line.startswith(("TELEGRAM_BOT_TOKEN=", "TELEGRAM_CHAT_ID="))]
    lines.extend((f"TELEGRAM_BOT_TOKEN={token}", f"TELEGRAM_CHAT_ID={chat_id}"))
    descriptor, temporary = tempfile.mkstemp(prefix=".env.production.telegram-", dir=BOT_DIR)
    try:
        with os.fdopen(descriptor, "w") as stream:
            stream.write("\n".join(lines) + "\n")
        os.chmod(temporary, 0o600)
        os.replace(temporary, ENV_FILE)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main() -> None:
    print("First send /start to your bot from your personal Telegram chat.")
    token = getpass.getpass("New BotFather token (hidden): ").strip()
    if not re.fullmatch(r"[0-9]+:[A-Za-z0-9_-]+", token):
        raise SystemExit("Token format is invalid")
    bot = telegram_call(token, "getMe", {})
    print(f"Connected to @{bot.get('username', 'unknown')} (bot ID {bot['id']})")
    chats = private_chats(telegram_call(token, "getUpdates", {"limit": 100, "timeout": 0}))
    if not chats:
        raise SystemExit("No private chat found. Send /start to the bot and run this setup again.")
    for chat_id, label in chats.items():
        print(f"Private chat: {label} (Chat ID {chat_id})")
    chat_id = next(iter(chats)) if len(chats) == 1 else input("Chat ID to receive alerts: ").strip()
    if chat_id not in chats:
        raise SystemExit("Choose one of the listed Chat IDs")
    telegram_call(token, "sendMessage", {"chat_id": chat_id,
                                        "text": "✅ Defense Live connected. Simulated payment alerts will appear here."})
    save_settings(token, chat_id)
    command = ["docker", "compose", "--project-directory", str(BOT_DIR),
               "--env-file", str(ENV_FILE), "-f", str(BOT_DIR / "docker-compose.defense.yml"),
               "-f", str(BOT_DIR / "docker-compose.production.yml"), "up", "-d", "--no-deps",
               "payment-service"]
    subprocess.run(command, check=True)
    print("Telegram payment alerts enabled. The bot token was not printed.")


if __name__ == "__main__":
    main()
