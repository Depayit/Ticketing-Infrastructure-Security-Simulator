import httpx
import asyncio
import json
import random
import uuid
import os
import time
import hashlib
import redis
import telegram
from datetime import datetime
from typing import Dict, List, Optional, Any
from urllib.parse import urlparse
from playwright.async_api import async_playwright

# Browser-side stealth toolkit (fingerprint + behaviour + JS injection).
import stealth
from ai_recovery import AIVisualRecoveryManager

# Import refactored packages
import core.config
import core.proxy
import core.logger
import browser.context
import browser.challenge
import flows.queue
import flows.purchase
import flows.checkout
import flows.forms

# ── Config loading ─────────────────────────────────────────────────────────────
REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")
r = redis.from_url(REDIS_URL, decode_responses=True)
config = core.config.load_config(r)

def get_tg_bot_instances() -> List[tuple[telegram.Bot, str]]:
    return core.config.get_tg_bot_instances(config)

def get_tg_bot() -> Optional[telegram.Bot]:
    return core.config.get_tg_bot(config)

# ── TTMWorker ─────────────────────────────────────────────────────────────────

class TTMWorker:
    def __init__(self):
        self.instance_id = f"worker-{uuid.uuid4().hex[:8]}"
        self.heartbeat_ttl = 30
        self.worker_key = f"worker:{self.instance_id}"
        self.success = False
        self.current_profile_idx = 0
        self.status = "STANDBY"
        self.current_url = "N/A"
        self.last_log = "Worker initialized"
        self.proxy = "direct"
        self._refresh_config()
        self.ai_recovery = AIVisualRecoveryManager(
            api_key=config.get("gemini_api_key") or config.get("captcha_key"),
            model_name=config.get("ai_model", "gemini-2.5-pro")
        )

    # ── config ─────────────────────────────────────────────────────────────────

    def _refresh_config(self):
        global config
        config = core.config.load_config(r)
        
        self.bot_mode: str = config.get("bot_mode", "queueit")
        self.target_url: str = config.get("target_url", "")
        self.click_selector: str = config.get("click_selector", "button:has-text('Add to Cart'), button:has-text('ซื้อเลย'), button:has-text('ใส่ตะกร้า')")
        self.refresh_mode: str = config.get("refresh_mode", "auto_refresh")
        self.refresh_interval: float = float(config.get("refresh_interval", 1.0))
        self.action_after_click: str = config.get("action_after_click", "notify")
        self.event_id: str = config.get("event_id", "")
        self.proxies: List[str] = config.get("proxies", [])
        self.profiles: List[Dict] = config.get("profiles", [])
        self.ticket_priorities: List[str] = config.get("ticket_priorities", ["VIP", "GA", "Standing"])
        self.membership_code: str = config.get("membership_code", "")
        
        self.browser_profiles: List[Dict] = config.get("browser_profiles", [])
        self.proxy_rotator_url: str = os.environ.get("PROXY_ROTATOR_URL") or config.get("proxy_rotator_url", "http://proxy-rotator:8080")
        self.proxies_per_worker: int = int(config.get("proxies_per_worker", 5))

        self.ticket_count: int = 1
        self.ticket_buyers: List[str] = []
        self.current_profile: Dict = {}

        qi = config.get("queueit", {}) or {}
        # Force headless mode in Docker container environment to prevent XServer launch failure.
        self.qi_headless: bool = True if os.path.exists("/.dockerenv") else bool(qi.get("headless", True))
        self.qi_manual_takeover: bool = bool(qi.get("manual_takeover", False))
        self.qi_book_selector: str = qi.get(
            "book_selector",
            "a:has-text('จอง'), a:has-text('ซื้อบัตร'), button:has-text('จอง'), "
            "button:has-text('ซื้อบัตร'), a:has-text('Buy'), button:has-text('Buy Now')",
        )
        self.qi_join_texts: List[str] = qi.get(
            "join_texts",
            ["Join the Queue", "Join Queue", "เข้าสู่คิว", "เข้าคิว", "Join now"],
        )
        self.qi_stillhere_texts: List[str] = qi.get(
            "stillhere_texts",
            ["Yes", "Yes, I'm here", "I'm here", "ใช่", "ยังอยู่", "Continue"],
        )
        self.qi_seat_selector: str = qi.get(
            "seat_selector",
            ".seat:not(.sold):not(.unavailable), .seat.available, .seat.open, .seat-available, "
            ".zone-available, .zone-clickable, .zone-open, [data-zone-status='available'], "
            "[data-seat-available='true'], [data-status='available'], "
            "li.available, .seatAvailable, "
            "svg .seat-circle:not(.sold), svg rect.available, svg .seat-node:not(.unavailable)",
        )
        self.qi_addtocart_selector: str = qi.get(
            "addtocart_selector",
            "button:has-text('ใส่ตะกร้า'), button:has-text('Add to Cart'), "
            "button:has-text('สั่งซื้อ'), button:has-text('ดำเนินการต่อ'), "
            "button:has-text('Confirm'), button:has-text('ยืนยัน')",
        )
        self.qi_queue_markers: List[str] = qi.get(
            "queue_markers", ["queue-it.net", "queue-it", "/waiting", "entry zone", "buying queue", "defense-gateway"],
        )
        self.qi_hold_seconds: int = int(qi.get("hold_seconds", 600))
        self.qi_max_minutes: int = int(qi.get("max_minutes", 120))
        self.qi_stop_on_first: bool = bool(qi.get("stop_on_first", True))

        self.qi_show_date_preference: str = str(qi.get("show_date_preference", "")).strip()
        self.qi_show_dates: List[str] = qi.get("show_dates", [
            "วันพฤหัสบดีที่ 3 ธันวาคม 2569",
            "วันเสาร์ที่ 5 ธันวาคม 2569",
            "วันอาทิตย์ที่ 6 ธันวาคม 2569",
        ])

        self.qi_seat_color_priorities: List[str] = qi.get("seat_color_priorities", [])
        self.qi_zone_name_priorities: List[str] = qi.get("zone_name_priorities", []) or self.ticket_priorities
        self.qi_auto_scroll: bool = bool(qi.get("auto_scroll_for_buttons", True))
        self.qi_max_scroll_px: int = int(qi.get("max_scroll_search_px", 3000))

        hv = config.get("human_verification", {}) or qi.get("human_verification", {}) or {}
        self.hv_markers: List[str] = list(hv.get("markers") or core.config.DEFAULT_HV_MARKERS)
        self.hv_robot_texts: List[str] = list(hv.get("robot_texts") or core.config.DEFAULT_HV_ROBOT_TEXTS)
        self.hv_proceed_texts: List[str] = list(hv.get("proceed_texts") or core.config.DEFAULT_HV_PROCEED_TEXTS)

    async def _update_leased_proxies(self):
        fallback = config.get("proxies", [])
        try:
            self.proxies = await core.proxy.acquire_proxies(
                self.proxy_rotator_url,
                self.instance_id,
                self.proxies_per_worker,
                fallback
            )
        except Exception:
            self.proxies = fallback

    async def _proxy_lease_loop(self):
        while not self.success:
            await asyncio.sleep(45)
            if not self.success:
                await self._update_leased_proxies()

    def _generate_deterministic_profile(self, proxy: str) -> Dict:
        return core.proxy.generate_deterministic_profile(proxy)

    def _get_browser_profile(self, proxy: str) -> Dict:
        return core.proxy.get_browser_profile(proxy, self.browser_profiles, self.proxies)

    def _apply_buyer_profile(self, proxy: str):
        self.current_profile = core.proxy.get_buyer_profile(proxy, self.profiles, self.proxies)
        self.ticket_count = int(self.current_profile.get("ticket_count", 1))
        
        configured_buyers = self.current_profile.get("ticket_buyers", [])
        self.ticket_buyers = []
        
        if self.ticket_count >= 1:
            first_buyer = configured_buyers[0] if len(configured_buyers) > 0 and configured_buyers[0].strip() else self.current_profile.get("fullname", "")
            self.ticket_buyers.append(first_buyer)
            
        if self.ticket_count > 1:
            dummy_firsts = ["สมชาย", "สมศักดิ์", "สมหญิง", "มาลี", "วิชัย", "นงนุช", "กฤษณะ", "พงศกร", "ศิริพร", "รัตนา"]
            dummy_lasts = ["รักดี", "ใจดี", "มีสุข", "เจริญพร", "มั่งคั่ง", "สวัสดี", "มั่นคง", "พิทักษ์", "สายทอง", "งามเลิศ"]
            
            for i in range(1, self.ticket_count):
                if i < len(configured_buyers) and configured_buyers[i].strip():
                    self.ticket_buyers.append(configured_buyers[i])
                else:
                    dummy_name = f"{random.choice(dummy_firsts)} {random.choice(dummy_lasts)}"
                    self.ticket_buyers.append(dummy_name)

    def _parse_playwright_proxy(self, proxy_str: str) -> Optional[dict]:
        return browser.context.parse_playwright_proxy(proxy_str)

    # ── Ticket quantity & registration ──────────────────────────────────────

    async def _qi_select_ticket_quantity(self, page, behavior=None) -> bool:
        return await flows.purchase.select_ticket_quantity(page, behavior, self.ticket_count, self.send_log)

    async def _qi_fill_registration_names(self, page, behavior=None) -> bool:
        return await flows.forms.fill_registration_names(page, behavior, self.ticket_buyers, self.send_log)

    async def _qi_select_promptpay_payment(self, page, behavior=None) -> bool:
        return await flows.checkout.select_promptpay_payment(page, behavior, self.send_log)

    async def _qi_notify_payment_ready(self, page, proxy: Optional[str]) -> None:
        await flows.checkout.notify_payment_ready(
            page, proxy, self.instance_id, self.qi_hold_seconds, r, config, self.send_log
        )

    # ── logging and state ──────────────────────────────────────────────────────

    async def send_log(self, message: str, level: str = "INFO"):
        log_line = core.logger.send_log_sync(
            r, self.instance_id, self.worker_key, message, level, config, self.update_status
        )
        self.last_log = message
        self.update_status()
        await core.logger.send_log_async(r, self.instance_id, message, level, config)

    def update_status(self, status: str = None, url: str = None):
        if status is not None:
            self.status = status
        if url is not None:
            self.current_url = url
        if hasattr(self, "proxies") and self.proxies:
            self.proxy = self.proxies[0]
        else:
            self.proxy = "direct"
        vw = getattr(self, "viewport_width", 1920)
        vh = getattr(self, "viewport_height", 1080)
        core.logger.update_status_in_redis(
            r, self.worker_key, self.heartbeat_ttl, self.instance_id,
            self.status, self.current_url, self.last_log, self.proxy,
            viewport_width=vw, viewport_height=vh
        )

    def register_worker(self):
        self.update_status()

    def heartbeat(self):
        self.update_status()

    async def _heartbeat_loop(self):
        while True:
            try:
                self.heartbeat()
            except Exception:
                pass
            await asyncio.sleep(5)

    def unregister_worker(self):
        r.delete(self.worker_key)

    async def global_stopped(self) -> bool:
        return r.get("ttm:global_stop") == "1"

    async def is_running(self) -> bool:
        return r.get("ttm:running") == "1"

    async def is_worker_stopped(self) -> bool:
        return r.get(f"ttm:stop:{self.instance_id}") == "1"

    async def set_global_stop(self):
        r.set("ttm:global_stop", "1", ex=7200)
        r.incr("ttm:success_count")
        await self.send_log("🚨 ได้บัตรสำเร็จ! สั่งหยุดทุก worker แล้ว", "SUCCESS")

    async def _live_stream_task(self, page):
        import base64
        while True:
            try:
                if r.get(f"ttm:live_stream:{self.instance_id}") == "1":
                    if not page.is_closed():
                        screenshot_bytes = await page.screenshot(type="jpeg", quality=40)
                        b64 = base64.b64encode(screenshot_bytes).decode('utf-8')
                        r.setex(f"ttm:live_frame:{self.instance_id}", 10, b64)
                    await asyncio.sleep(0.5)
                else:
                    await asyncio.sleep(1.0)
            except Exception:
                await asyncio.sleep(1.0)
                if page.is_closed():
                    break

    async def _check_screenshot_command(self, page):
        req_id = r.get(f"ttm:cmd:screenshot:{self.instance_id}")
        if req_id:
            try:
                r.delete(f"ttm:cmd:screenshot:{self.instance_id}")
                await self.send_log("📸 AI Controller สั่งแคปหน้าจอ...", "INFO")
                await asyncio.sleep(0.5)
                screenshot_bytes = await page.screenshot(type="jpeg", quality=60)
                import base64
                b64 = base64.b64encode(screenshot_bytes).decode('utf-8')
                r.setex(f"ttm:screenshot:{req_id}", 60, b64)
            except Exception as e:
                await self.send_log(f"⚠️ ถ่ายภาพหน้าจอไม่สำเร็จ: {e}", "WARN")

    async def _control_listener_task(self, page):
        import redis.asyncio as aioredis
        async_r = aioredis.from_url(REDIS_URL, decode_responses=True)
        pubsub = async_r.pubsub()
        await pubsub.subscribe(f"ttm:control:{self.instance_id}")
        try:
            while not page.is_closed():
                try:
                    msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.1)
                    if msg and msg.get("type") == "message":
                        data_str = msg.get("data")
                        if data_str:
                            data = json.loads(data_str)
                            act_type = data.get("type")
                            if act_type == "click":
                                x = float(data.get("x", 0))
                                y = float(data.get("y", 0))
                                await self.send_log(f"🖱️ รีโมท: คลิกพิกัด ({x}, {y})", "INFO")
                                await page.mouse.click(x, y)
                            elif act_type == "type":
                                text = str(data.get("text", ""))
                                await self.send_log(f"⌨️ รีโมท: พิมพ์ข้อความ '{text}'", "INFO")
                                await page.keyboard.type(text)
                            elif act_type == "keypress":
                                key = str(data.get("key", ""))
                                await self.send_log(f"⌨️ รีโมท: กดปุ่ม '{key}'", "INFO")
                                await page.keyboard.press(key)
                except Exception:
                    pass
                await asyncio.sleep(0.05)
        finally:
            try:
                await pubsub.unsubscribe(f"ttm:control:{self.instance_id}")
                await pubsub.close()
                await async_r.close()
            except Exception:
                pass

    async def _run_manual_takeover_loop(self, page, proxy_str):
        self.update_status("MANUAL_CONTROL", page.url)
        await self.send_log("🚨 [MANUAL TAKEOVER] บอทผ่านคิวแล้ว! เปิดหน้าจอ Live View เพื่อควบคุมมือได้ทันที...", "SUCCESS")
        
        # Turn on live stream automatically for 1 hour
        r.setex(f"ttm:live_stream:{self.instance_id}", 3600, "1")
        
        while not self.success:
            if await self.global_stopped() or not await self.is_running() or await self.is_worker_stopped():
                await self.send_log("⏹ STOP [MANUAL TAKEOVER] — ออกจากโหมดควบคุมมือ")
                break
            if page.is_closed():
                break
            await asyncio.sleep(1.0)

    def _qi_frames(self, page):
        return browser.challenge.get_qi_frames(page)

    async def _human_challenge_visible(self, page) -> bool:
        return await browser.challenge.is_human_challenge_visible(page, self.hv_markers)

    async def _human_click_locator(self, page, frame, loc, behavior=None) -> bool:
        return await browser.challenge.human_click_locator(page, frame, loc, behavior)

    async def _try_tick_robot_checkbox(self, page, behavior=None) -> bool:
        return await browser.challenge.try_tick_robot_checkbox(page, behavior, self.hv_robot_texts)

    async def _try_click_proceed_after_human_check(self, page, behavior=None) -> bool:
        return await browser.challenge.try_click_proceed_after_human_check(page, behavior, self.hv_proceed_texts)

    async def _try_human_verification(self, page, behavior=None) -> bool:
        return await browser.challenge.solve_human_challenge(
            page, behavior, self.hv_markers, self.hv_robot_texts, self.hv_proceed_texts,
            self.update_status, self.send_log
        )

    async def _qi_click_text(self, page, behavior, texts: List[str], wait_hidden: bool = False) -> bool:
        return await flows.queue.click_text(page, behavior, texts, wait_hidden)

    async def _qi_try_selector(self, page, behavior, selector: str, hover_delay: bool = True) -> bool:
        return await flows.purchase.try_selector(page, behavior, selector, hover_delay)

    async def _qi_scroll_and_try_selector(self, page, behavior, selector: str, max_px: int = 0) -> bool:
        return await flows.purchase.scroll_and_try_selector(page, behavior, selector, max_px or self.qi_max_scroll_px)

    async def _qi_select_show_date(self, page, behavior=None) -> bool:
        return await flows.purchase.select_show_date(page, behavior, self.qi_show_date_preference, self.qi_show_dates, self.send_log)

    async def _qi_in_queue(self, page) -> bool:
        return await flows.queue.is_in_queue(page, self.qi_queue_markers)

    async def _qi_on_purchase_page(self, page) -> bool:
        return await flows.queue.is_on_purchase_page(page, self.qi_queue_markers, self.qi_seat_selector, self.qi_addtocart_selector)

    # ── Seat selection with scroll + AI color priorities ────────────────

    def _build_seat_context(self, scroll_info: Dict) -> Dict:
        return {
            "seat_color_priorities": self.qi_seat_color_priorities or None,
            "zone_name_priorities": self.qi_zone_name_priorities or None,
            "scroll_info": scroll_info,
            "show_dates": self.qi_show_dates or None,
            "show_date_preference": self.qi_show_date_preference or None,
        }

    async def _qi_get_scroll_info(self, page) -> Dict:
        try:
            info = await page.evaluate("""() => ({
                scrollY: window.scrollY || window.pageYOffset || 0,
                pageHeight: document.documentElement.scrollHeight || document.body.scrollHeight || 0,
                viewportHeight: window.innerHeight || 0,
                isScrollable: (document.documentElement.scrollHeight || 0) > (window.innerHeight || 0) + 50
            })""")
            return {
                "current_scroll_y": int(info.get("scrollY", 0)),
                "page_height": int(info.get("pageHeight", 0)),
                "viewport_height": int(info.get("viewportHeight", 0)),
                "is_scrollable": bool(info.get("isScrollable", False)),
            }
        except Exception:
            return {"current_scroll_y": 0, "page_height": 0, "viewport_height": 0, "is_scrollable": False}

    async def _qi_smart_seat_selection(self, page, behavior) -> bool:
        await self._qi_select_show_date(page, behavior)
        await asyncio.sleep(random.uniform(0.3, 0.6))

        scroll_info = await self._qi_get_scroll_info(page)
        seat_context = self._build_seat_context(scroll_info)

        if self.qi_seat_color_priorities:
            await self.send_log(f"🎨 AI Seat: ลำดับสี = {self.qi_seat_color_priorities}", "INFO")
        if self.qi_zone_name_priorities:
            await self.send_log(f"🏟️ AI Seat: ลำดับโซน = {self.qi_zone_name_priorities}", "INFO")

        seat_clicked = await self._qi_try_selector(page, behavior, self.qi_seat_selector)
        if seat_clicked:
            await self.send_log("✅ CSS selector เจอที่นั่งว่าง — คลิกแล้ว", "INFO")
            await behavior.think(0.3, 0.8)
        else:
            if self.qi_auto_scroll:
                await self.send_log("📜 ไม่เจอที่นั่งในหน้าจอ — กำลัง scroll ลงหา...", "INFO")
                seat_clicked = await self._qi_scroll_and_try_selector(
                    page, behavior, self.qi_seat_selector, max_px=self.qi_max_scroll_px
                )
                if seat_clicked:
                    await self.send_log("✅ Scroll แล้วเจอที่นั่งว่าง — คลิกแล้ว", "INFO")
                    await behavior.think(0.3, 0.8)

        if not seat_clicked:
            await self.send_log("🤖 CSS ไม่เจอ — ส่ง AI วิเคราะห์ที่นั่งพร้อมลำดับสี/โซน...", "INFO")
            scroll_info = await self._qi_get_scroll_info(page)
            seat_context = self._build_seat_context(scroll_info)
            try:
                ai_recovered = await asyncio.wait_for(
                    self.ai_recovery.attempt_recovery(
                        page, screenshot_dir="/app/tmp",
                        behavior=behavior, phase="seat_selection",
                        seat_context=seat_context,
                    ),
                    timeout=40.0,
                )
                if ai_recovered:
                    await self.send_log("🤖 AI วิเคราะห์และช่วยเลือกที่นั่ง/โซนสำเร็จ", "SUCCESS")
                    seat_clicked = True
                    await behavior.think(0.5, 1.0)
            except asyncio.TimeoutError:
                await self.send_log("⏰ AI seat analysis timeout", "DEBUG")
            except Exception as ai_err:
                await self.send_log(f"⚠️ AI seat selection ขัดข้อง: {ai_err}", "DEBUG")

        cart_clicked = False
        if seat_clicked:
            cart_clicked = await self._qi_try_selector(page, behavior, self.qi_addtocart_selector)
            if not cart_clicked and self.qi_auto_scroll:
                await self.send_log("📜 กำลัง scroll หาปุ่ม 'ใส่ตะกร้า'...", "INFO")
                cart_clicked = await self._qi_scroll_and_try_selector(page, behavior, self.qi_addtocart_selector, max_px=1500)
        else:
            cart_clicked = await self._qi_try_selector(page, behavior, self.qi_addtocart_selector)
            if not cart_clicked and self.qi_auto_scroll:
                cart_clicked = await self._qi_scroll_and_try_selector(page, behavior, self.qi_addtocart_selector, max_px=1500)

        if not seat_clicked and not cart_clicked:
            scroll_info = await self._qi_get_scroll_info(page)
            seat_context = self._build_seat_context(scroll_info)
            try:
                recovered = await self.ai_recovery.attempt_recovery(
                    page, screenshot_dir="/app/tmp",
                    behavior=behavior, phase="add_to_cart",
                    seat_context=seat_context,
                )
                if recovered:
                    await self.send_log("🤖 AI ช่วยดำเนินการในหน้าซื้อบัตร", "SUCCESS")
                    cart_clicked = await self._qi_try_selector(page, behavior, self.qi_addtocart_selector)
            except Exception as ai_err:
                await self.send_log(f"⚠️ AI Recovery ขัดข้อง: {ai_err}", "DEBUG")

        return cart_clicked

    async def run_queueit_mode(self):
        await self.send_log("🎫 เริ่มโหมด Queue-it Browser Flow (Hold-only)...")
        await self._update_leased_proxies()
        asyncio.create_task(self._proxy_lease_loop())

        while not self.target_url:
            await self.send_log("❌ ตั้งค่า Target URL (หน้า event) ก่อนเริ่ม", "ERROR")
            await asyncio.sleep(5)
            self._refresh_config()

        proxy_str = self.proxies[0] if self.proxies else None
        proxy_cfg = self._parse_playwright_proxy(proxy_str) if proxy_str else None
        seed = proxy_str or self.instance_id
        bp = self._get_browser_profile(seed)
        self._apply_buyer_profile(seed)
        fp = stealth.build_fingerprint(bp, seed)
        stealth_js = stealth.build_stealth_script(fp)
        viewport = {"width": int(fp.get("viewport_width", 1920)), "height": int(fp.get("viewport_height", 1080))}

        async with async_playwright() as p:
            browser_instance, context, page = await browser.context.create_stealth_browser(
                p, self.qi_headless, proxy_str, fp, viewport, stealth_js
            )
            asyncio.create_task(self._live_stream_task(page))
            behavior = stealth.HumanBehavior(seed, viewport)
            deadline = time.time() + self.qi_max_minutes * 60
            phase = "open"

            try:
                self.update_status("QUEUING", self.target_url)
                await page.goto(self.target_url, timeout=60000, wait_until="domcontentloaded")
                await self.send_log(f"🔗 เปิดหน้า event: {self.target_url}")
                await self._try_human_verification(page, behavior)
                await behavior.wander(page, moves=3)

                while not self.success and time.time() < deadline:
                    if await self.global_stopped() or not await self.is_running() or await self.is_worker_stopped():
                        await self.send_log("⏹ STOP — ออกจาก Queue-it flow")
                        break

                    await self._check_screenshot_command(page)

                    if await self._try_human_verification(page, behavior):
                        continue

                    # Highest priority: never get dropped by the inactivity modal.
                    if await self._qi_click_text(page, behavior, self.qi_stillhere_texts, wait_hidden=True):
                        await self.send_log("🟢 ตอบ 'Still here? → Yes' อัตโนมัติ", "DEBUG")
                        await behavior.think(0.5, 1.2)
                        continue

                    # Check for "ผ่านคิวแล้ว!" / "เลือกที่นั่ง" button
                    if await self._qi_click_text(page, behavior, ["เลือกที่นั่ง", "select seats", "enter seats", "เข้าสู่การเลือกที่นั่ง"]):
                        self.update_status("ADMITTED", page.url)
                        await self.send_log("🎉 ผ่านคิวแล้ว! กำลังกดปุ่ม 'เลือกที่นั่ง' เพื่อไปยังแผนผัง...", "SUCCESS")
                        await behavior.think(0.5, 1.2)
                        if self.qi_manual_takeover:
                            await self._run_manual_takeover_loop(page, proxy_str)
                            break
                        continue

                    # Check for member code input page (e.g. pre-sale member verification)
                    member_input = page.locator("input#member-code-input").first
                    if await member_input.count() > 0 and await member_input.is_visible():
                        self.update_status("ENTERING_MEMBER_CODE", page.url)
                        if not self.membership_code:
                            await self.send_log("⚠️ พบหน้าให้กรอกรหัสสมาชิก แต่ไม่ได้ตั้งค่า Membership Code ไว้ใน UI Setup!", "WARN")
                            await asyncio.sleep(3)
                        else:
                            await self.send_log(f"🔑 พบหน้ากรอกรหัสสมาชิก กำลังกรอกรหัส: {self.membership_code}...", "INFO")
                            
                            # Clear input if any value is already present, then type human-like
                            current_val = await member_input.input_value()
                            if current_val != self.membership_code:
                                await member_input.scroll_into_view_if_needed()
                                box = await member_input.bounding_box()
                                if box:
                                    await behavior.click(page, box["x"] + box["width"]/2, box["y"] + box["height"]/2)
                                else:
                                    await member_input.click()
                                await member_input.fill("")
                                await behavior.type_text(page, self.membership_code, mistake_prob=0.03)
                                await behavior.think(0.2, 0.6)
                            
                            # Click the "ตกลง" submit button
                            submit_btn = page.locator("button.submit-btn, button:has-text('ตกลง')").first
                            if await submit_btn.count() > 0 and await submit_btn.is_visible():
                                await submit_btn.scroll_into_view_if_needed()
                                box = await submit_btn.bounding_box()
                                if box:
                                    await behavior.click(page, box["x"] + box["width"]/2, box["y"] + box["height"]/2)
                                else:
                                    await submit_btn.click()
                                await self.send_log("✅ กดปุ่มส่งรหัสสมาชิกสำเร็จ", "INFO")
                                await behavior.think(0.5, 1.2)
                        continue

                    if await self._qi_click_text(page, behavior, self.qi_join_texts):
                        self.update_status("JOINING_QUEUE", page.url)
                        await self.send_log("🚶 ปุ่ม 'Join the Queue' โผล่แล้ว! กำลังกดปุ่มเข้าคิว...", "INFO")
                        await behavior.think(0.5, 1.0)
                        continue

                    try:
                        body_text = (await page.inner_text("body"))[:4000].lower()
                        if "ยังไม่ถึงเวลาเปิดขาย" in body_text or "the event will begin at" in body_text or "รอเวลาเปิดขาย" in body_text:
                            self.update_status("WAITING_SALE_START", page.url)
                            await self.send_log("⏳ รอหน้า Pre-Queue (Countdown) - กำลังจอดรอจนกว่าปุ่มเข้าคิวจะขึ้น...", "INFO")
                            await asyncio.sleep(5)
                            continue
                    except Exception:
                        pass

                    # Check for Checkout / Payment Page
                    url_l = (page.url or "").lower()
                    try:
                        body_lower = (await page.inner_text("body"))[:4000].lower()
                    except Exception:
                        body_lower = ""

                    is_payment_page = False
                    if not any(k in url_l for k in ("/seats", "booking")):
                        if any(k in url_l for k in ("checkout", "cart", "payment", "order", "2c2p")) or any(k in body_lower for k in (
                            "checkout", "ชำระเงิน", "บัตรเครดิต", "payment",
                            "ยืนยันการสั่งซื้อ", "order summary", "สรุปคำสั่งซื้อ",
                        )):
                            # Ensure we are not on the "Passed Queue" intermediate landing page
                            if not any(k in body_lower for k in ("ผ่านคิวแล้ว", "admitted", "เลือกที่นั่ง", "select seat", "select seats")):
                                if not await self._qi_on_purchase_page(page):
                                    is_payment_page = True

                    if is_payment_page:
                        self.update_status("CHECKING_OUT", page.url)
                        await self.send_log("💳 พบหน้าชำระเงิน/สรุปคำสั่งซื้อ — กำลังเลือกชำระเงินด้วย PromptPay...", "INFO")
                        await self._qi_select_promptpay_payment(page, behavior)

                        try:
                            verify_result = await self.ai_recovery.verify_checkout(page)
                            if verify_result:
                                v_status = verify_result.get("status")
                                if v_status == "action_required":
                                    await self.send_log(
                                        f"⚠️ AI ตรวจพบปัญหาในหน้า checkout: {verify_result.get('explanation', '')[:200]}",
                                        "WARN",
                                    )
                                    await self.ai_recovery.attempt_recovery(
                                        page, screenshot_dir="/app/tmp",
                                        behavior=behavior, phase="checkout"
                                    )
                                    await behavior.think(0.5, 1.0)
                                elif v_status == "human_intervention_required":
                                    await self.send_log(
                                        f"🚨 AI แจ้งว่าต้องการคนช่วย: {verify_result.get('explanation', '')[:200]}",
                                        "WARN",
                                    )
                                else:
                                    await self.send_log("✅ AI ยืนยันหน้า checkout ถูกต้อง", "INFO")
                        except Exception as ve:
                            await self.send_log(f"⚠️ AI verification ขัดข้อง (ไม่กระทบ flow): {ve}", "DEBUG")

                        self.update_status("SUCCESS", page.url)
                        await self._qi_notify_payment_ready(page, proxy_str)
                        self.success = True
                        if self.qi_stop_on_first:
                            await self.set_global_stop()
                        await self.send_log(f"⌛ คงเซสชันไว้ {self.qi_hold_seconds}s เพื่อให้จ่ายเงินต่อ...", "INFO")
                        await asyncio.sleep(self.qi_hold_seconds)
                        break

                    # Check for Registration Page
                    is_registration_page = False
                    if not any(k in url_l for k in ("/seats", "booking")):
                        if any(k in url_l for k in ("register", "registration")) or any(k in body_lower for k in ("ลงทะเบียน", "register", "กรอกรายละเอียด", "ชื่อ-นามสกุลบน")):
                            if not await self._qi_on_purchase_page(page):
                                is_registration_page = True

                    if is_registration_page:
                        if self.ticket_buyers:
                            self.update_status("CHECKING_OUT", page.url)
                            await self.send_log("📝 พบหน้าลงทะเบียน/กรอกรายละเอียด — กำลังกรอกข้อมูลผู้เข้าชม...", "INFO")
                            await self._qi_fill_registration_names(page, behavior)
                            await behavior.think(0.5, 1.0)
                            try:
                                await self.ai_recovery.attempt_recovery(
                                    page, screenshot_dir="/app/tmp",
                                    behavior=behavior, phase="registration"
                                )
                            except Exception:
                                pass
                        continue

                    # Check for Purchase / Seat Selection Page
                    if await self._qi_on_purchase_page(page):
                        if self.qi_manual_takeover:
                            await self._run_manual_takeover_loop(page, proxy_str)
                            break

                        if phase != "purchase":
                            phase = "purchase"
                            self.update_status("SELECTING_SEAT", page.url)
                            await self.send_log("🎯 ทะลุคิวแล้ว! เข้าหน้าซื้อบัตร — กำลังเลือกที่นั่ง", "SUCCESS")

                            try:
                                ai_plan = await self.ai_recovery.analyze_purchase_page(page)
                                if ai_plan:
                                    detected = ai_plan.get("detected_elements", {})
                                    if detected:
                                        await self.send_log(
                                            f"🔍 AI Pre-scan: พบปุ่ม {detected.get('buttons', [])[:5]}, "
                                            f"inputs {detected.get('inputs', [])[:3]}",
                                            "INFO",
                                        )
                            except Exception as e:
                                await self.send_log(f"⚠️ AI Pre-scan ขัดข้อง (ไม่กระทบ flow หลัก): {e}", "DEBUG")

                            if self.ticket_count > 1:
                                await self._qi_select_ticket_quantity(page, behavior)
                                await behavior.think(0.3, 0.8)

                        self.update_status("SELECTING_SEAT", page.url)
                        cart_clicked = await self._qi_smart_seat_selection(page, behavior)

                        if cart_clicked:
                            self.update_status("ADDING_TO_CART", page.url)
                            await self.send_log("🛒 กดใส่ตะกร้า/ดำเนินการต่อแล้ว", "INFO")
                            await behavior.think(1.0, 2.0)
                            
                            try:
                                body_after = (await page.inner_text("body"))[:4000].lower()
                                if "ที่นั่งถูกล็อกโดย" in body_after or "seat locked by" in body_after or "ที่นั่งถูกล็อกโดยคนอื่นแล้ว" in body_after:
                                    await self.send_log("💥 ที่นั่งถูกล็อกโดยผู้อื่น (โดนแย่ง) — กำลังเริ่มสแกนหาที่นั่งใหม่...", "WARN")
                                    await asyncio.sleep(1.5)
                                    continue
                            except Exception:
                                pass

                            if self.ticket_buyers:
                                await self._qi_fill_registration_names(page, behavior)
                                await behavior.think(0.5, 1.2)
                        continue

                    try:
                        login_btn = page.locator("button:has-text('เข้าสู่ระบบ'), button[type='submit']").filter(has_text="เข้าสู่ระบบ").first
                        if await login_btn.count() > 0 and await login_btn.is_visible():
                            if getattr(self, "_login_attempts", 0) < 3:
                                self._login_attempts = getattr(self, "_login_attempts", 0) + 1
                                await self.send_log(f"🔑 เริ่มกระบวนการล็อกอินเสมือนมนุษย์ (ครั้งที่ {self._login_attempts})...", "INFO")
                                try:
                                    profile = self.profiles[0] if self.profiles else {}
                                    email = profile.get("email") or "bot@example.com"
                                    pwd = profile.get("password") or "password123"
                                    
                                    email_input = page.locator("input[type='email'], input[name='email'], input[name='username'], input#email").first
                                    pwd_input = page.locator("input[type='password'], input[name='password'], input#password").first
                                    
                                    if behavior:
                                        current_email = await email_input.input_value()
                                        if current_email != email:
                                            await email_input.scroll_into_view_if_needed()
                                            box = await email_input.bounding_box()
                                            if box:
                                                await behavior.click(page, box["x"] + box["width"]/2, box["y"] + box["height"]/2)
                                            else:
                                                await email_input.click()
                                            await email_input.fill("")
                                            await behavior.type_text(page, email, mistake_prob=0.06)
                                            await behavior.think(0.2, 0.5)
                                            
                                            await pwd_input.scroll_into_view_if_needed()
                                            box = await pwd_input.bounding_box()
                                            if box:
                                                await behavior.click(page, box["x"] + box["width"]/2, box["y"] + box["height"]/2)
                                            else:
                                                await pwd_input.click()
                                            await pwd_input.fill("")
                                            await behavior.type_text(page, pwd, mistake_prob=0.03)
                                            await behavior.think(0.2, 0.6)
                                        
                                        captcha_box = page.locator("#login-captcha, .recaptcha-checkbox-border, iframe[src*='recaptcha']").first
                                        if await captcha_box.count() > 0 and await captcha_box.is_visible():
                                            await captcha_box.scroll_into_view_if_needed()
                                            box = await captcha_box.bounding_box()
                                            if box:
                                                await behavior.click(page, box["x"] + box["width"]/2, box["y"] + box["height"]/2)
                                                await behavior.think(0.4, 0.8)
                                        
                                        await behavior.scroll(page, 400)
                                        await behavior.think(0.3, 0.7)
                                        
                                        await login_btn.scroll_into_view_if_needed()
                                        box = await login_btn.bounding_box()
                                        if box:
                                            await behavior.click(page, box["x"] + box["width"]/2, box["y"] + box["height"]/2)
                                        else:
                                            await login_btn.click()
                                    else:
                                        await email_input.fill(email)
                                        await pwd_input.fill(pwd)
                                        captcha_box = page.locator("#login-captcha, .recaptcha-checkbox-border").first
                                        if await captcha_box.count() > 0 and await captcha_box.is_visible():
                                            await captcha_box.check()
                                        await login_btn.click()
                                        
                                    await self.send_log("✅ กดล็อกอินแล้ว รอดูผล...", "INFO")
                                    await asyncio.sleep(2.5)
                                except Exception as e:
                                    await self.send_log(f"⚠️ ข้อผิดพลาดล็อกอิน: {e}", "WARN")
                            else:
                                if not getattr(self, "_login_failed_alerted", False):
                                    await self.send_log("❌ ล็อกอินไม่สำเร็จเกิน 3 ครั้ง กำลังให้ AI เบื้องหลังช่วยแก้ปัญหา...", "WARN")
                                    self._login_failed_alerted = True
                                    
                                try:
                                    recovered = await self.ai_recovery.attempt_recovery(
                                        page, screenshot_dir="/app/tmp",
                                        behavior=behavior, phase="login"
                                    )
                                    if recovered:
                                        await self.send_log("🤖 AI เบื้องหลังวิเคราะห์และช่วยดำเนินการล็อกอินแล้ว", "SUCCESS")
                                except Exception:
                                    pass
                                continue
                    except Exception:
                        pass

                    if await self._qi_in_queue(page):
                        try:
                            captcha_modal = page.locator("#final-captcha-modal").first
                            if await captcha_modal.count() > 0:
                                class_attr = await captcha_modal.get_attribute("class") or ""
                                if "hidden" not in class_attr:
                                    await self.send_log("🚨 พบ CAPTCHA ด่านสุดท้าย (ก่อนเข้าหน้าซื้อตั๋ว) กำลังดำเนินการแก้ไข...", "WARN")
                                    try:
                                        solved = await browser.challenge.solve_final_captcha(
                                            page, behavior, self.send_log
                                        )
                                        if solved:
                                            await self.send_log("🤖 แก้ไข CAPTCHA ด่านสุดท้ายสำเร็จ!", "SUCCESS")
                                            await behavior.think(1.0, 2.0)
                                        else:
                                            await self.send_log("⚠️ แก้ไข CAPTCHA ด่านสุดท้ายไม่สำเร็จ กำลังลองใหม่...", "WARN")
                                    except Exception as ai_err:
                                        await self.send_log(f"⚠️ แก้ไข CAPTCHA ด่านสุดท้ายขัดข้อง: {ai_err}", "DEBUG")
                                    continue
                        except Exception:
                            pass

                        if await self._qi_click_text(page, behavior, ["เลือกที่นั่ง", "select seats", "enter seats", "เข้าสู่การเลือกที่นั่ง"]):
                            self.update_status("ADMITTED", page.url)
                            await self.send_log("🎉 ผ่านคิวแล้ว! กำลังกดปุ่ม 'เลือกที่นั่ง' เพื่อไปยังแผนผัง...", "SUCCESS")
                            await behavior.think(0.5, 1.0)
                            continue

                        if await self._qi_click_text(page, behavior, self.qi_join_texts):
                            if phase != "queue":
                                phase = "queue"
                                await self.send_log("⏩ กด 'Join the Queue' แล้ว — กำลังรอคิว", "INFO")
                        elif phase == "queue":
                            await behavior.wander(page, moves=1)
                            if random.random() > 0.3:
                                scroll_y = random.randint(100, 600)
                                await page.mouse.wheel(0, scroll_y)
                                await asyncio.sleep(random.uniform(0.2, 0.6))
                                await page.mouse.wheel(0, -scroll_y)
                        await asyncio.sleep(random.uniform(0.8, 1.8))
                        continue

                    if await self._qi_try_selector(page, behavior, self.qi_book_selector):
                        await self.send_log("📨 กดปุ่มจอง/ซื้อบัตรแล้ว", "INFO")
                        await asyncio.sleep(random.uniform(0.1, 1.0))
                        await behavior.think(0.4, 1.0)
                        continue

                    try:
                        # Check if final captcha modal is visible first
                        captcha_modal = page.locator("#final-captcha-modal").first
                        if await captcha_modal.count() > 0 and "hidden" not in (await captcha_modal.get_attribute("class") or ""):
                            await self.send_log("🚨 พบ CAPTCHA ด่านสุดท้าย (ก่อนเข้าหน้าซื้อตั๋ว) กำลังดำเนินการแก้ไข...", "WARN")
                            solved = await browser.challenge.solve_final_captcha(page, behavior, self.send_log)
                            if solved:
                                await self.send_log("🤖 แก้ไข CAPTCHA ด่านสุดท้ายสำเร็จ!", "SUCCESS")
                                await behavior.think(1.0, 2.0)
                            else:
                                await self.send_log("⚠️ แก้ไข CAPTCHA ด่านสุดท้ายไม่สำเร็จ กำลังลองใหม่...", "WARN")
                            continue

                        _ai_phase = "queue" if await self._qi_in_queue(page) else "captcha"
                        recovered = await self.ai_recovery.attempt_recovery(
                            page, screenshot_dir="/app/tmp", phase=_ai_phase
                        )
                        if recovered:
                            await self.send_log("🤖 AI กู้คืนสถานะหน้าจอและดำเนินการอัตโนมัติสำเร็จ", "SUCCESS")
                            await asyncio.sleep(1.0)
                            continue
                    except Exception as ai_err:
                        await self.send_log(f"⚠️ ระบบ AI Recovery ขัดข้อง: {ai_err}", "DEBUG")

                    await behavior.wander(page, moves=1)
                    sleep_interval = max(10.0, self.refresh_interval)
                    sleep_jittered = sleep_interval * random.uniform(0.85, 1.15)
                    await asyncio.sleep(sleep_jittered)
                    try:
                        await page.reload(timeout=30000, wait_until="domcontentloaded")
                        await self._try_human_verification(page, behavior)
                    except Exception:
                        pass

                if not self.success and time.time() >= deadline:
                    await self.send_log("⌛ หมดเวลา (max_minutes) — ออกจาก Queue-it flow", "WARN")

            except Exception as e:
                await self.send_log(f"❌ Queue-it flow error: {e}", "ERROR")
            finally:
                try:
                    control_task.cancel()
                    await control_task
                except Exception:
                    pass
                try:
                    await context.close()
                    await browser_instance.close()
                except Exception:
                    pass

    # ── Main run loop ──────────────────────────────────────────────────────────

    async def run(self):
        while True:
            self.success = False
            self.status = "STANDBY"
            self.current_url = "N/A"
            self.register_worker()
            heartbeat_task = asyncio.create_task(self._heartbeat_loop())
            try:
                await self.send_log("Worker พร้อมแล้ว ⏳ — รอคำสั่ง START จาก Dashboard")

                while not await self.is_running() or await self.is_worker_stopped():
                    if await self.is_worker_stopped():
                        self.update_status("STOPPED")
                    else:
                        self.update_status("STANDBY")
                    await asyncio.sleep(2)

                self._refresh_config()
                self.update_status("RUNNING", self.target_url)

                try:
                    if r.get("ttm:global_stop") == "1":
                        r.delete("ttm:global_stop")
                        await self.send_log("🔄 ล้างสถานะ global_stop สำหรับรอบการทำงานใหม่", "INFO")
                except Exception:
                    pass

                if self.bot_mode == "defense_demo":
                    await self.send_log("🛡️ โหมด Defense Demo — รวมติ๊ก Akamai + ห้องรอ sandbox")
                await self.run_queueit_mode()

            except Exception as e:
                self.update_status("FAILED")
                await self.send_log(f"❌ ระบบเกิดข้อผิดพลาดในการรัน: {e}", "ERROR")
            finally:
                heartbeat_task.cancel()
                try:
                    await heartbeat_task
                except asyncio.CancelledError:
                    pass
                self.unregister_worker()
            
            await asyncio.sleep(3)


if __name__ == "__main__":
    asyncio.run(TTMWorker().run())
