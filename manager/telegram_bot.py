import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime

import redis
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler, 
    ContextTypes, MessageHandler, filters, ConversationHandler,
    Application
)
from typing import Optional

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")
r = redis.from_url(REDIS_URL, decode_responses=True)

# Conversation states
ASK_URL, ASK_EVENT_ID = range(2)

def get_config():
    try:
        raw = r.get("ticket:config")
        if raw:
            return json.loads(raw)
    except Exception as e:
        logger.error(f"Error reading config from Redis: {e}")
    return {}

def save_config(config):
    config["_saved_at"] = datetime.now().isoformat()
    r.set("ticket:config", json.dumps(config))
    r.publish("ticket:config_updates", "updated")

def get_bot_config_by_token(token: str) -> Optional[dict]:
    config = get_config()
    bots_list = config.get("telegram_bots", [])
    for b in bots_list:
        if b.get("token") == token:
            return b
    # Check fallback/default
    fallback_token = config.get("telegram_token", "")
    if fallback_token == token:
        return {
            "id": "default",
            "name": "Default Bot",
            "token": fallback_token,
            "chat_id": config.get("telegram_chat_id", ""),
            "enabled": True
        }
    return None

def is_authorized(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    bot_token = context.bot.token
    bot_cfg = get_bot_config_by_token(bot_token)
    if not bot_cfg:
        return False
    
    allowed_chat_id = str(bot_cfg.get("chat_id", ""))
    
    # Allow if no chat ID configured (fallback), or if it matches
    if not allowed_chat_id:
        return True
        
    chat_id = str(update.effective_chat.id)
    return chat_id == allowed_chat_id

def build_dashboard_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("▶️ START ALL", callback_data="cmd_start"),
            InlineKeyboardButton("⏹ STOP ALL", callback_data="cmd_stop"),
        ],
        [
            InlineKeyboardButton("📊 Refresh", callback_data="cmd_status"),
            InlineKeyboardButton("📝 View Logs", callback_data="cmd_logs"),
        ],
        [
            InlineKeyboardButton("🌐 Proxies", callback_data="cmd_proxies"),
            InlineKeyboardButton("👥 Profiles", callback_data="cmd_profiles"),
        ],
        [
            InlineKeyboardButton("⚙️ Bot Setup", callback_data="menu_setup"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def build_setup_keyboard(config):
    current_mode = config.get("bot_mode", "queueit")
    
    keyboard = [
        [
            InlineKeyboardButton(f"Mode: {current_mode} 🔄", callback_data="setup_cycle_mode"),
        ],
        [
            InlineKeyboardButton("✏️ Edit Target URL", callback_data="setup_edit_url"),
        ],
        [
            InlineKeyboardButton("✏️ Edit Event ID", callback_data="setup_edit_event"),
        ],
        [
            InlineKeyboardButton("🔙 Back to Dashboard", callback_data="cmd_status"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_status_text():
    config = get_config()
    active_workers = len(r.keys("worker:*"))
    success_count = int(r.get("ticket:success_count") or 0)
    is_running = r.get("ticket:running") == "1"
    global_stop = r.get("ticket:global_stop") == "1"
    
    try:
        active_proxies = int(r.scard("ticket:proxies:active") or 0)
        total_proxies = int(r.scard("ticket:proxies:raw") or 0)
        dead_proxies = int(r.scard("ticket:proxies:dead") or 0)
    except Exception:
        active_proxies = total_proxies = dead_proxies = 0

    browser_profiles = len(config.get("browser_profiles", []))
    buyer_profiles = len(config.get("profiles", []))

    mode = config.get("bot_mode", "queueit")
    event_id = config.get("event_id", "N/A")
    target_url = config.get("target_url", "N/A")
    if target_url and len(target_url) > 40:
        target_url = target_url[:37] + "..."

    status_str = "🟢 RUNNING" if is_running else "🟡 STANDBY"
    if global_stop:
         status_str = "🛑 FORCE STOPPED"

    text = "🤖 <b>Playwright Stealth Bot Dashboard</b>\n\n"
    text += f"🎯 <b>Target:</b> <code>{target_url if target_url != 'N/A' else event_id}</code>\n"
    text += f"<i>Mode: {mode}</i> | <i>Sync: {datetime.now().strftime('%H:%M:%S')}</i>\n\n"
    
    text += "========================\n"
    text += f"📊 <b>System Status:</b> {status_str}\n"
    text += f"👷 <b>Active Workers:</b> <code>{active_workers}</code>\n"
    text += f"✅ <b>Success Orders:</b> <code>{success_count}</code>\n"
    text += f"🌐 <b>Proxies:</b> <code>{active_proxies}</code> Active / <code>{total_proxies}</code> Total"
    if dead_proxies > 0:
        text += f" (⚠️ {dead_proxies} dead)"
    text += "\n"
    text += f"👥 <b>Profiles:</b> <code>{browser_profiles}</code> Browsers / <code>{buyer_profiles}</code> Buyers\n"
    text += "========================\n\n"

    if active_proxies > 0 and browser_profiles < active_proxies:
        text += "⚠️ <b>WARNING: Fingerprint Mismatch</b>\n"
        text += f"Active proxies (<code>{active_proxies}</code>) exceed browser profiles (<code>{browser_profiles}</code>). Dynamic Fallback enabled to prevent bans.\n"
        
    return text

async def check_auth(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if not is_authorized(update, context):
        await update.effective_message.reply_text("⛔ Unauthorized. Your chat ID is not permitted to control this bot.")
        return False
    return True

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update, context): return ConversationHandler.END
    await update.message.reply_text(
        get_status_text(),
        reply_markup=build_dashboard_keyboard(),
        parse_mode="HTML",
        disable_web_page_preview=True
    )
    return ConversationHandler.END

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update, context): return ConversationHandler.END
    
    query = update.callback_query
    await query.answer()
    
    action = query.data
    user_name = query.from_user.first_name

    if action == "cmd_start":
        r.delete("ticket:global_stop")
        r.set("ticket:command", "start")
        r.set("ticket:running", "1")
        log_msg = f"[{datetime.now().strftime('%H:%M:%S')}] Telegram: ▶ START ALL WORKERS — ordered by {user_name}"
        logger.info(log_msg)
        r.lpush("ticket:logs", log_msg)
        r.ltrim("ticket:logs", 0, 99)
        
        await query.edit_message_text(
            text=f"✅ <b>Command sent: START ALL</b>\n\n" + get_status_text(),
            reply_markup=build_dashboard_keyboard(),
            parse_mode="HTML",
            disable_web_page_preview=True
        )
        return ConversationHandler.END
        
    elif action == "cmd_stop":
        r.set("ticket:global_stop", "1", ex=7200)
        r.set("ticket:command", "stop")
        r.delete("ticket:running")
        log_msg = f"[{datetime.now().strftime('%H:%M:%S')}] Telegram: ⏹ STOP ALL WORKERS — ordered by {user_name}"
        logger.info(log_msg)
        r.lpush("ticket:logs", log_msg)
        r.ltrim("ticket:logs", 0, 99)
        
        await query.edit_message_text(
            text=f"✅ <b>Command sent: STOP ALL</b>\n\n" + get_status_text(),
            reply_markup=build_dashboard_keyboard(),
            parse_mode="HTML",
            disable_web_page_preview=True
        )
        return ConversationHandler.END
        
    elif action == "cmd_status":
        try:
            await query.edit_message_text(
                text=get_status_text(),
                reply_markup=build_dashboard_keyboard(),
                parse_mode="HTML",
                disable_web_page_preview=True
            )
        except Exception:
            pass
        return ConversationHandler.END

    elif action == "cmd_logs":
        logs = r.lrange("ticket:logs", 0, 14)
        if not logs:
            log_text = "No recent logs."
        else:
            log_text = "📝 <b>Recent Logs (Last 15)</b>\n<pre><code class=\"language-text\">" + "\n".join(logs) + "</code></pre>"
        
        # Add a back button
        kbd = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Dashboard", callback_data="cmd_status")]])
        await query.edit_message_text(text=log_text, reply_markup=kbd, parse_mode="HTML")
        return ConversationHandler.END

    elif action == "cmd_proxies":
        try:
            active_proxies = int(r.scard("ticket:proxies:active") or 0)
            total_proxies = int(r.scard("ticket:proxies:raw") or 0)
            dead_proxies = int(r.scard("ticket:proxies:dead") or 0)
        except Exception:
            active_proxies = total_proxies = dead_proxies = 0
            
        text = "🌐 <b>Proxy Status</b>\n\n"
        text += f"<b>Total:</b> <code>{total_proxies}</code>\n"
        text += f"<b>Active/Healthy:</b> <code>{active_proxies}</code>\n"
        text += f"<b>Dead:</b> <code>{dead_proxies}</code>\n\n"
        text += "<i>Manage proxy lists via the Web Dashboard.</i>"
        
        kbd = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Dashboard", callback_data="cmd_status")]])
        await query.edit_message_text(text=text, reply_markup=kbd, parse_mode="HTML")
        return ConversationHandler.END

    elif action == "cmd_profiles":
        config = get_config()
        browser_profiles = len(config.get("browser_profiles", []))
        buyer_profiles = len(config.get("profiles", []))
        
        text = "👥 <b>Profile Settings</b>\n\n"
        text += f"<b>Browser Profiles:</b> <code>{browser_profiles}</code>\n"
        text += f"<b>Buyer/Card Profiles:</b> <code>{buyer_profiles}</code>\n\n"
        text += "<i>Add or remove profiles via the Web Dashboard.</i>"
        
        kbd = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Dashboard", callback_data="cmd_status")]])
        await query.edit_message_text(text=text, reply_markup=kbd, parse_mode="HTML")
        return ConversationHandler.END

    elif action == "menu_setup":
        config = get_config()
        await query.edit_message_text(
            text="⚙️ <b>Bot Setup Menu</b>\nSelect an option to configure:",
            reply_markup=build_setup_keyboard(config),
            parse_mode="HTML"
        )
        return ConversationHandler.END
        
    elif action == "setup_cycle_mode":
        config = get_config()
        current_mode = config.get("bot_mode", "queueit")
        modes = ["queueit", "defense_demo"]
        try:
            idx = modes.index(current_mode)
            next_mode = modes[(idx + 1) % len(modes)]
        except ValueError:
            next_mode = modes[0]
            
        config["bot_mode"] = next_mode
        save_config(config)
        
        log_msg = f"[{datetime.now().strftime('%H:%M:%S')}] Telegram: ⚙️ Mode changed to {next_mode}"
        r.lpush("ticket:logs", log_msg)
        
        await query.edit_message_text(
            text=f"✅ Mode changed to <b>{next_mode}</b>.\n\n⚙️ <b>Bot Setup Menu</b>:",
            reply_markup=build_setup_keyboard(config),
            parse_mode="HTML"
        )
        return ConversationHandler.END

    elif action == "setup_edit_url":
        await query.edit_message_text(
            text="🔗 <b>Please type the new Target URL:</b>\n<i>(or type /cancel to abort)</i>",
            parse_mode="HTML"
        )
        return ASK_URL

    elif action == "setup_edit_event":
        await query.edit_message_text(
            text="🎫 <b>Please type the new Event ID:</b>\n<i>(or type /cancel to abort)</i>",
            parse_mode="HTML"
        )
        return ASK_EVENT_ID

async def handle_url_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update, context): return ConversationHandler.END
    new_url = update.message.text.strip()
    
    config = get_config()
    config["target_url"] = new_url
    save_config(config)
    
    log_msg = f"[{datetime.now().strftime('%H:%M:%S')}] Telegram: ⚙️ Target URL updated"
    r.lpush("ticket:logs", log_msg)
    
    await update.message.reply_text(
        text=f"✅ Target URL updated to:\n<code>{new_url}</code>\n\n⚙️ <b>Bot Setup Menu</b>:",
        reply_markup=build_setup_keyboard(config),
        parse_mode="HTML",
        disable_web_page_preview=True
    )
    return ConversationHandler.END

async def handle_event_id_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update, context): return ConversationHandler.END
    new_event = update.message.text.strip()
    
    config = get_config()
    config["event_id"] = new_event
    save_config(config)
    
    log_msg = f"[{datetime.now().strftime('%H:%M:%S')}] Telegram: ⚙️ Event ID updated to {new_event}"
    r.lpush("ticket:logs", log_msg)
    
    await update.message.reply_text(
        text=f"✅ Event ID updated to: <code>{new_event}</code>\n\n⚙️ <b>Bot Setup Menu</b>:",
        reply_markup=build_setup_keyboard(config),
        parse_mode="HTML"
    )
    return ConversationHandler.END

async def cancel_setup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update, context): return ConversationHandler.END
    await update.message.reply_text(
        get_status_text(),
        reply_markup=build_dashboard_keyboard(),
        parse_mode="HTML",
        disable_web_page_preview=True
    )
    return ConversationHandler.END

async def start_bot(token: str, bot_id: str) -> Application:
    application = ApplicationBuilder().token(token).build()

    setup_conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start_command),
            CallbackQueryHandler(button_callback)
        ],
        states={
            ASK_URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url_input)],
            ASK_EVENT_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_event_id_input)],
        },
        fallbacks=[CommandHandler("cancel", cancel_setup)],
        allow_reentry=True
    )

    application.add_handler(setup_conv_handler)
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    return application

async def stop_bot(application: Application):
    try:
        if application.updater and application.updater.running:
            await application.updater.stop()
        if application.running:
            await application.stop()
        await application.shutdown()
    except Exception as e:
        logger.error(f"Error stopping bot application: {e}")

class TelegramBotManager:
    def __init__(self):
        self.running_bots = {}  # bot_id -> application
        self.bot_configs = {}  # bot_id -> {token, chat_id, name}
        self.last_saved_at = None

    async def sync_bots(self):
        try:
            config = get_config()
        except Exception as e:
            logger.error(f"Failed to read config: {e}")
            return

        bots_list = config.get("telegram_bots", [])
        if not bots_list:
            token = config.get("telegram_token", "")
            chat_id = config.get("telegram_chat_id", "")
            if token and token != "YOUR_2CAPTCHA_OR_CAPMONSTER_KEY_HERE" and not token.startswith("YOUR_") and chat_id:
                bots_list = [{
                    "id": "default",
                    "name": "Default Bot",
                    "token": token,
                    "chat_id": chat_id,
                    "enabled": True
                }]

        active_ids = set()
        bot_statuses = {}

        for b in bots_list:
            bot_id = b.get("id") or "default"
            name = b.get("name", "Unnamed Bot")
            token = b.get("token", "").strip()
            chat_id = b.get("chat_id", "").strip()
            enabled = b.get("enabled", True)

            if not token or not chat_id or token.startswith("YOUR_"):
                bot_statuses[bot_id] = {
                    "name": name,
                    "status": "error",
                    "message": "Token or Chat ID not configured"
                }
                if bot_id in self.running_bots:
                    logger.info(f"Stopping bot {name} (incomplete credentials)")
                    app = self.running_bots.pop(bot_id)
                    self.bot_configs.pop(bot_id, None)
                    await stop_bot(app)
                continue

            if not enabled:
                bot_statuses[bot_id] = {
                    "name": name,
                    "status": "disabled",
                    "message": "Disabled"
                }
                if bot_id in self.running_bots:
                    logger.info(f"Stopping bot {name} (disabled)")
                    app = self.running_bots.pop(bot_id)
                    self.bot_configs.pop(bot_id, None)
                    await stop_bot(app)
                continue

            active_ids.add(bot_id)

            current_cfg = self.bot_configs.get(bot_id)
            needs_restart = current_cfg and (current_cfg["token"] != token or current_cfg["chat_id"] != chat_id)

            if needs_restart:
                logger.info(f"Restarting bot {name} due to credentials change")
                app = self.running_bots.pop(bot_id)
                self.bot_configs.pop(bot_id, None)
                await stop_bot(app)

            if bot_id not in self.running_bots:
                logger.info(f"Starting bot: {name}")
                try:
                    app = await start_bot(token, bot_id)
                    self.running_bots[bot_id] = app
                    self.bot_configs[bot_id] = {"token": token, "chat_id": chat_id, "name": name}
                    bot_statuses[bot_id] = {
                        "name": name,
                        "status": "running",
                        "message": "Polling / Active"
                    }
                except Exception as e:
                    logger.error(f"Failed to start bot {name}: {e}")
                    bot_statuses[bot_id] = {
                        "name": name,
                        "status": "error",
                        "message": f"Start failed: {str(e)}"
                    }
            else:
                bot_statuses[bot_id] = {
                    "name": name,
                    "status": "running",
                    "message": "Polling / Active"
                }

        # Stop bots that were deleted
        for bot_id in list(self.running_bots.keys()):
            if bot_id not in active_ids:
                logger.info(f"Stopping removed bot ID: {bot_id}")
                app = self.running_bots.pop(bot_id)
                self.bot_configs.pop(bot_id, None)
                await stop_bot(app)

        try:
            r.set("ticket:telegram_bot_statuses", json.dumps(bot_statuses))
        except Exception as e:
            logger.error(f"Failed to save bot statuses to Redis: {e}")

    async def monitor_proxy_health(self):
        last_dead_count = None
        last_success_count = None
        
        while True:
            try:
                dead_proxies = int(r.scard("ticket:proxies:dead") or 0)
                success_count = int(r.get("ticket:success_count") or 0)
                
                if last_dead_count is not None and dead_proxies > last_dead_count:
                    diff = dead_proxies - last_dead_count
                    # Proxy dead alerts disabled as per user request
                    pass
                
                if last_success_count is not None and success_count > last_success_count:
                    diff = success_count - last_success_count
                    for bot_id, app in self.running_bots.items():
                        cfg = self.bot_configs.get(bot_id)
                        if cfg and cfg.get("chat_id"):
                            try:
                                await app.bot.send_message(
                                    chat_id=cfg["chat_id"],
                                    text=f"🎉 <b>SUCCESS ALERT</b>\nSystem just scored {diff} new successful order(s)! Total success: {success_count}",
                                    parse_mode="HTML"
                                )
                            except Exception:
                                pass
                                
                last_dead_count = dead_proxies
                last_success_count = success_count
            except Exception as e:
                logger.error(f"Error in monitor_proxy_health: {e}")
            
            await asyncio.sleep(10)

    async def run_loop(self):
        logger.info("Starting Telegram Bot Manager loop...")
        asyncio.create_task(self.monitor_proxy_health())
        while True:
            try:
                config = get_config()
                saved_at = config.get("_saved_at")
                if saved_at != self.last_saved_at:
                    self.last_saved_at = saved_at
                    await self.sync_bots()
            except Exception as e:
                logger.error(f"Error in Bot Manager loop sync: {e}")
            await asyncio.sleep(3.0)

def main():
    logger.info("Starting Telegram Bot Dashboard service...")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    manager = TelegramBotManager()
    try:
        loop.run_until_complete(manager.run_loop())
    except KeyboardInterrupt:
        logger.info("Received shutdown signal. Stopping bots...")
        for bot_id, app in list(manager.running_bots.items()):
            loop.run_until_complete(stop_bot(app))
    except Exception as e:
        logger.error(f"Bot service crashed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.error(f"Bot crashed: {e}")
        sys.exit(1)
