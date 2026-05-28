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
from typing import Dict, List, Optional
from urllib.parse import urlparse
from playwright.async_api import async_playwright

# Browser-side stealth toolkit (fingerprint + behaviour + JS injection).
# This bot is browser-only — there is no GraphQL/HTTP purchase path.
import stealth

# ── Config loading ─────────────────────────────────────────────────────────────
REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")

def _load_config_from_file() -> dict:
    try:
        with open("config.json") as f:
            return json.load(f)
    except Exception:
        return {}

def _load_config_from_redis(r: redis.Redis) -> Optional[dict]:
    try:
        raw = r.get("ttm:config")
        if raw:
            return json.loads(raw)
    except Exception:
        pass
    return None

def load_config(r: redis.Redis) -> dict:
    cfg = _load_config_from_redis(r)
    if cfg:
        return cfg
    return _load_config_from_file()

r = redis.from_url(REDIS_URL, decode_responses=True)
config = load_config(r)

_tg_bot: Optional[telegram.Bot] = None
_tg_token: str = ""

def get_tg_bot() -> Optional[telegram.Bot]:
    global _tg_bot, _tg_token
    token = config.get("telegram_token", "")
    if not token or token.startswith("YOUR_"):
        _tg_bot = None
        _tg_token = ""
        return None
    if _tg_bot is None or _tg_token != token:
        _tg_bot = telegram.Bot(token=token)
        _tg_token = token
    return _tg_bot

QUEUE_CAPTCHA_URL_TPL = "https://www.thaiticketmajor.com/concert/{event_id}"


# ── TTMWorker ─────────────────────────────────────────────────────────────────

class TTMWorker:
    def __init__(self):
        self.instance_id = f"worker-{uuid.uuid4().hex[:8]}"
        self.heartbeat_ttl = 30
        self.worker_key = f"worker:{self.instance_id}"
        self.success = False
        self.current_profile_idx = 0
        self._refresh_config()

    # ── config ─────────────────────────────────────────────────────────────────

    def _refresh_config(self):
        global config
        config = load_config(r)
        # Browser-only bot. "queueit" = real TTM/Queue-it funnel (default),
        # "general" = generic button-click automation. (legacy "ttm" GraphQL
        # mode has been removed.)
        self.bot_mode: str = config.get("bot_mode", "queueit")
        if self.bot_mode == "ttm":
            self.bot_mode = "queueit"
        self.target_url: str = config.get("target_url", "")
        self.click_selector: str = config.get("click_selector", "button:has-text('Add to Cart'), button:has-text('ซื้อเลย'), button:has-text('ใส่ตะกร้า')")
        self.refresh_mode: str = config.get("refresh_mode", "auto_refresh")
        self.refresh_interval: float = float(config.get("refresh_interval", 1.0))
        self.action_after_click: str = config.get("action_after_click", "notify")
        self.event_id: str = config.get("event_id", "")
        self.proxies: List[str] = config.get("proxies", [])
        self.profiles: List[Dict] = config.get("profiles", [])
        self.ticket_priorities: List[str] = config.get(
            "ticket_priorities", ["VIP", "GA", "Standing"]
        )
        self.browser_profiles: List[Dict] = config.get("browser_profiles", [])
        self.proxy_rotator_url: str = os.environ.get("PROXY_ROTATOR_URL") or config.get("proxy_rotator_url", "http://proxy-rotator:8080")
        self.proxies_per_worker: int = int(config.get("proxies_per_worker", 5))

        # ── Queue-it browser flow (bot_mode == "queueit") ─────────────────────
        qi = config.get("queueit", {}) or {}
        self.qi_headless: bool = bool(qi.get("headless", True))
        # Selector groups — each is a comma-separated CSS list; we also fall
        # back to text matching for the standard Queue-it widget labels.
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
            ".seat:not(.sold):not(.unavailable), .zone-available, [data-seat-available='true'], "
            "li.available, .seatAvailable",
        )
        self.qi_addtocart_selector: str = qi.get(
            "addtocart_selector",
            "button:has-text('ใส่ตะกร้า'), button:has-text('Add to Cart'), "
            "button:has-text('สั่งซื้อ'), button:has-text('ดำเนินการต่อ'), "
            "button:has-text('Confirm'), button:has-text('ยืนยัน')",
        )
        # Markers that mean "still inside the Queue-it waiting flow".
        self.qi_queue_markers: List[str] = qi.get(
            "queue_markers", ["queue-it.net", "queue-it", "/waiting", "entry zone", "buying queue"],
        )
        # Keep the seat-holding session alive (sec) for manual payment.
        self.qi_hold_seconds: int = int(qi.get("hold_seconds", 600))
        self.qi_max_minutes: int = int(qi.get("max_minutes", 120))
        # Multi-instance: stop ALL workers on the first successful hold, or
        # let each worker hold its own seat independently (more tickets).
        self.qi_stop_on_first: bool = bool(qi.get("stop_on_first", True))

    async def _update_leased_proxies(self):
        """
        Dynamically acquire/lease proxies from the Proxy Rotator service.
        Prevents duplicates across workers.
        """
        url = f"{self.proxy_rotator_url}/api/proxies/acquire"
        payload = {
            "worker_id": self.instance_id,
            "count": self.proxies_per_worker
        }
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(url, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    new_proxies = data.get("proxies", [])
                    if new_proxies:
                        if set(self.proxies) != set(new_proxies):
                            await self.send_log(
                                f"🌐 Proxy Rotator: Swapped/updated leased proxies. Active count: {len(new_proxies)}", 
                                "INFO"
                            )
                        self.proxies = new_proxies
                else:
                    raise Exception(f"HTTP {resp.status_code}")
        except Exception as e:
            # Fallback to local config list if empty
            if not self.proxies:
                self.proxies = config.get("proxies", [])
            await self.send_log(
                f"⚠️ Rotator contact error: {e}. Fallback to {len(self.proxies)} static proxies.",
                "WARN"
            )

    async def _proxy_lease_loop(self):
        """Background coroutine to periodically renew and fetch leased proxies."""
        while not self.success:
            await self._update_leased_proxies()
            await asyncio.sleep(15)


    def _generate_deterministic_profile(self, proxy: str) -> Dict:
        """
        Dynamically and deterministically generate a unique, highly realistic 
        browser profile based on the proxy string as a seed. This ensures that:
        1. A proxy always gets the exact same browser profile across restarts.
        2. Different proxies get distinct, realistic profiles.
        3. No manual setup is needed even when running hundreds of workers.
        """
        import random
        rng = random.Random(proxy)
        
        browser = rng.choice(['chrome', 'chrome', 'chrome', 'edge', 'firefox'])
        
        chrome_versions = ['128.0.6613.120', '129.0.6668.89', '130.0.6723.58', '130.0.6723.116', '131.0.6778.85', '131.0.6778.108']
        edge_versions = ['128.0.2739.67', '129.0.2792.89', '130.0.2849.52', '131.0.2903.70']
        firefox_versions = ['127.0', '128.0', '129.0', '130.0', '131.0']
        
        if browser == 'chrome':
            version = rng.choice(chrome_versions)
        elif browser == 'edge':
            version = rng.choice(edge_versions)
        else:
            version = rng.choice(firefox_versions)
            
        gpu_pool = [
            {"vendor": "Google Inc. (NVIDIA)", "renderer": "ANGLE (NVIDIA, NVIDIA GeForce RTX 4090 Direct3D11 vs_5_0 ps_5_0, D3D11)"},
            {"vendor": "Google Inc. (NVIDIA)", "renderer": "ANGLE (NVIDIA, NVIDIA GeForce RTX 4080 Direct3D11 vs_5_0 ps_5_0, D3D11)"},
            {"vendor": "Google Inc. (NVIDIA)", "renderer": "ANGLE (NVIDIA, NVIDIA GeForce RTX 4070 Ti Direct3D11 vs_5_0 ps_5_0, D3D11)"},
            {"vendor": "Google Inc. (NVIDIA)", "renderer": "ANGLE (NVIDIA, NVIDIA GeForce RTX 4070 Direct3D11 vs_5_0 ps_5_0, D3D11)"},
            {"vendor": "Google Inc. (NVIDIA)", "renderer": "ANGLE (NVIDIA, NVIDIA GeForce RTX 3090 Direct3D11 vs_5_0 ps_5_0, D3D11)"},
            {"vendor": "Google Inc. (NVIDIA)", "renderer": "ANGLE (NVIDIA, NVIDIA GeForce RTX 3080 Direct3D11 vs_5_0 ps_5_0, D3D11)"},
            {"vendor": "Google Inc. (NVIDIA)", "renderer": "ANGLE (NVIDIA, NVIDIA GeForce RTX 3070 Direct3D11 vs_5_0 ps_5_0, D3D11)"},
            {"vendor": "Google Inc. (NVIDIA)", "renderer": "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Ti Direct3D11 vs_5_0 ps_5_0, D3D11)"},
            {"vendor": "Google Inc. (NVIDIA)", "renderer": "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)"},
            {"vendor": "Google Inc. (AMD)", "renderer": "ANGLE (AMD, AMD Radeon RX 7900 XTX Direct3D11 vs_5_0 ps_5_0, D3D11)"},
            {"vendor": "Google Inc. (AMD)", "renderer": "ANGLE (AMD, AMD Radeon RX 7800 XT Direct3D11 vs_5_0 ps_5_0, D3D11)"},
            {"vendor": "Google Inc. (AMD)", "renderer": "ANGLE (AMD, AMD Radeon RX 6800 XT Direct3D11 vs_5_0 ps_5_0, D3D11)"},
            {"vendor": "Google Inc. (Intel)", "renderer": "ANGLE (Intel, Intel(R) Iris(R) Xe Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)"},
            {"vendor": "Google Inc. (Intel)", "renderer": "ANGLE (Intel, Intel(R) Arc(TM) A770 Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)"}
        ]
        gpu = rng.choice(gpu_pool)
        
        viewport_pool = [
            {"w": 1920, "h": 1080},
            {"w": 2560, "h": 1440},
            {"w": 1366, "h": 768},
            {"w": 1536, "h": 864},
            {"w": 1440, "h": 900},
            {"w": 1280, "h": 800}
        ]
        vp = rng.choice(viewport_pool)
        
        concurrency = rng.choice([4, 6, 8, 12, 16])
        memory = rng.choice([4, 8, 16, 32])
        
        major = version.split('.')[0]
        
        if browser == 'chrome':
            ua = f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{version} Safari/537.36"
            sec_ch_ua = f'"Chromium";v="{major}", "Google Chrome";v="{major}", "Not-A.Brand";v="99"'
        elif browser == 'edge':
            cver = f"{major}.0.0.0"
            ua = f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{cver} Safari/537.36 Edg/{version}"
            sec_ch_ua = f'"Chromium";v="{major}", "Microsoft Edge";v="{major}", "Not-A.Brand";v="24"'
        else:
            ua = f"Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:{version}) Gecko/20100101 Firefox/{version}"
            sec_ch_ua = ""
            
        return {
            "browser": browser,
            "browser_version": version,
            "os": "windows",
            "os_version": "10.0",
            "user_agent": ua,
            "platform": "Win32",
            "language": "th-TH,th;q=0.9,en-US;q=0.8,en;q=0.7",
            "sec_ch_ua": sec_ch_ua,
            "sec_ch_ua_platform": "Windows",
            "viewport_width": vp["w"],
            "viewport_height": vp["h"],
            "screen_width": vp["w"],
            "screen_height": vp["h"],
            "color_depth": 24,
            "timezone": "Asia/Bangkok",
            "hardware_concurrency": concurrency,
            "device_memory": memory,
            "webgl_vendor": gpu["vendor"],
            "webgl_renderer": gpu["renderer"],
            "do_not_track": False,
            "touch_support": False
        }

    def _get_browser_profile(self, proxy: str) -> Dict:
        """
        Deterministically assign a browser profile to a proxy so each proxy
        always uses the same fingerprint (consistent across retries), but
        different proxies get different profiles.
        """
        profiles = self.browser_profiles
        if profiles and len(profiles) >= len(self.proxies):
            idx = int(hashlib.md5(proxy.encode()).hexdigest(), 16) % len(profiles)
            return profiles[idx]
        return self._generate_deterministic_profile(proxy)

    def _parse_playwright_proxy(self, proxy_str: str) -> Optional[dict]:
        try:
            if not proxy_str.startswith("http://") and not proxy_str.startswith("https://"):
                proxy_str = "http://" + proxy_str
            parsed = urlparse(proxy_str)
            server = f"{parsed.scheme or 'http'}://{parsed.hostname}"
            if parsed.port:
                server += f":{parsed.port}"
            proxy_config = {"server": server}
            if parsed.username:
                proxy_config["username"] = parsed.username
            if parsed.password:
                proxy_config["password"] = parsed.password
            return proxy_config
        except Exception:
            return None

    async def _run_auto_checkout(self, page) -> bool:
        """
        Attempts to autofill checkout forms using the first Buyer Profile.
        This is a best-effort general form filler.
        """
        try:
            if not self.profiles:
                await self.send_log("⚠️ ไม่มีโปรไฟล์ผู้ซื้อสำหรับใช้กรอกฟอร์ม Auto-Checkout", "WARN")
                return False
                
            profile = self.profiles[0]
            card = profile.get("card", {})
            
            await self.send_log("🤖 เริ่มการกรอกข้อมูลอัตโนมัติ (Auto-Checkout Best-effort)...")
            
            inputs = await page.locator("input, select").all()
            for inp in inputs:
                try:
                    name = (await inp.get_attribute("name") or "").lower()
                    placeholder = (await inp.get_attribute("placeholder") or "").lower()
                    inp_type = (await inp.get_attribute("type") or "").lower()
                    inp_id = (await inp.get_attribute("id") or "").lower()
                    
                    if "email" in name or "email" in placeholder or inp_type == "email":
                        await inp.fill(profile["email"])
                        continue
                        
                    if "phone" in name or "tel" in name or "phone" in placeholder or inp_type == "tel" or "phone" in inp_id:
                        await inp.fill(profile["phone"])
                        continue
                        
                    if "name" in name or "fullname" in name or "name" in placeholder or "name" in inp_id:
                        if "first" in name or "first" in placeholder or "first" in inp_id:
                            await inp.fill(profile["fullname"].split()[0])
                        elif "last" in name or "last" in placeholder or "last" in inp_id:
                            parts = profile["fullname"].split()
                            await inp.fill(parts[1] if len(parts) > 1 else parts[0])
                        else:
                            await inp.fill(profile["fullname"])
                        continue
                        
                    if "id_card" in name or "national" in name or "citizen" in name or "id" in placeholder or "citizen" in placeholder:
                        if profile.get("id_card"):
                            await inp.fill(profile["id_card"])
                        continue
                        
                    if "cardnumber" in name or "number" in name or "card" in placeholder or "number" in placeholder or "card" in inp_id:
                        if "card" in name or "card" in placeholder or "card" in inp_id:
                            await inp.fill(card.get("number", ""))
                        continue
                        
                    if "exp" in name or "date" in name or "exp" in placeholder or "exp" in inp_id:
                        exp_val = card.get("exp", "")
                        if len(exp_val) == 4:
                            await inp.fill(f"{exp_val[:2]}/{exp_val[2:]}")
                        continue
                        
                    if "cvv" in name or "cvc" in name or "security" in placeholder or "cvv" in placeholder or "cvv" in inp_id:
                        await inp.fill(card.get("cvv", ""))
                        continue
                        
                except Exception:
                    pass
            
            await self.send_log("✅ กรอกข้อมูลเบื้องต้นเรียบร้อยแล้ว กรุณาตรวจสอบและดำเนินการต่อเพื่อความปลอดภัย", "SUCCESS")
            return True
        except Exception as e:
            await self.send_log(f"❌ Auto-Checkout เกิดข้อผิดพลาด: {e}", "ERROR")
            return False

    async def run_general_mode(self):
        """
        Runs the browser automation mode using Playwright.
        Each worker gets its own browser instance.
        """
        await self.send_log("🚀 เริ่มต้นโหมด General Website (Browser Automation)...")
        
        # Acquire/lease healthy proxies from the Rotator
        await self._update_leased_proxies()
        
        target_url = self.target_url
        click_selector = self.click_selector
        refresh_mode = self.refresh_mode
        refresh_interval = self.refresh_interval
        action_after_click = self.action_after_click

        
        if not target_url:
            await self.send_log("❌ กรุณาตั้งค่า Target URL ในหน้า Setup ก่อนเริ่มต้นบอท", "ERROR")
            while not self.target_url:
                await asyncio.sleep(5)
                self._refresh_config()
                target_url = self.target_url
            
        proxy_str = self.proxies[0] if self.proxies else None
        proxy_config = None
        if proxy_str:
            proxy_config = self._parse_playwright_proxy(proxy_str)
            await self.send_log(f"🌐 ใช้ Proxy สำหรับ Browser: {proxy_str[-15:]}")
            
        bp = self._get_browser_profile(proxy_str or "default_seed")
        user_agent = bp.get("user_agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        viewport = {"width": bp.get("viewport_width", 1280), "height": bp.get("viewport_height", 800)}
        
        async with async_playwright() as p:
            await self.send_log("⚙️ กำลังสร้างบราวเซอร์เซสชัน...")
            try:
                browser = await p.chromium.launch(
                    headless=True,
                    proxy=proxy_config,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                    ]
                )
                
                context = await browser.new_context(
                    user_agent=user_agent,
                    viewport=viewport,
                    locale=bp.get("language", "th-TH"),
                    timezone_id=bp.get("timezone", "Asia/Bangkok"),
                )
                
                await context.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    });
                """)
                
                page = await context.new_page()
                await self.send_log(f"🔗 กำลังเปิดหน้าเว็บเป้าหมาย: {target_url}")
                await page.goto(target_url, timeout=60000, wait_until="domcontentloaded")
                await self.send_log("📄 โหลดหน้าเว็บเรียบร้อยแล้ว เฝ้ารอปุ่มสั่งซื้อ...")
                
                attempts = 0
                while not self.success:
                    if await self.global_stopped() or not await self.is_running():
                        await self.send_log("⏹ STOP — บอทถูกสั่งหยุดทำงาน")
                        break
                        
                    try:
                        button = page.locator(click_selector).first
                        count = await button.count()
                        
                        if count > 0:
                            is_disabled = False
                            try:
                                is_disabled = await button.get_attribute("disabled") is not None
                                if not is_disabled:
                                    classes = (await button.get_attribute("class") or "").lower()
                                    if "disabled" in classes or "disabled" in (await button.inner_text()).lower():
                                        is_disabled = True
                            except Exception:
                                pass
                                
                            if not is_disabled:
                                await self.send_log("🎯 เจอปุ่มสั่งซื้อที่พร้อมกดแล้ว! กำลังทำการคลิก...", "SUCCESS")
                                await button.click()
                                await self.send_log("✅ คลิกปุ่มสำเร็จแล้ว!", "SUCCESS")
                                
                                if action_after_click == "notify":
                                    await self.send_log("📢 [Success] บอทคลิกสั่งซื้อเรียบร้อย! โปรดดำเนินการต่อในบราวเซอร์หรือตรวจสอบความถูกต้อง", "SUCCESS")
                                    await self.set_global_stop()
                                    self.success = True
                                    await asyncio.sleep(180)
                                    break
                                elif action_after_click == "auto_checkout":
                                    await self._run_auto_checkout(page)
                                    await self.send_log("📢 [Success] บอทกรอกข้อมูลชำระเงินเรียบร้อย! โปรดเข้าหน้าเว็บเพื่อทำการตรวจสอบ/กดชำระเงินต่อ", "SUCCESS")
                                    await self.set_global_stop()
                                    self.success = True
                                    await asyncio.sleep(180)
                                    break
                            else:
                                attempts += 1
                                if attempts % 10 == 0:
                                    await self.send_log(f"⏳ เจอปุ่มแต่ยังอยู่ในสถานะล็อก/ปิดการใช้งาน (Disabled) - รอบที่ {attempts}", "DEBUG")
                        else:
                            attempts += 1
                            if attempts % 10 == 0:
                                await self.send_log(f"🔍 ยังไม่พบปุ่มเป้าหมายบนหน้านี้ - รอบที่ {attempts}", "DEBUG")
                                
                    except Exception as e:
                        await self.send_log(f"เกิดข้อผิดพลาดในการหาปุ่ม: {e}", "WARN")
                        
                    if refresh_mode == "auto_refresh":
                        await asyncio.sleep(refresh_interval)
                        try:
                            await page.reload(timeout=30000, wait_until="domcontentloaded")
                        except Exception as e:
                            await self.send_log(f"🔄 รีเฟรชหน้าเว็บล้มเหลว: {e}", "WARN")
                    else:
                        await asyncio.sleep(0.5)
                        
            except Exception as e:
                await self.send_log(f"❌ Playwright เกิดข้อผิดพลาดรุนแรง: {e}", "ERROR")
                await asyncio.sleep(5)
            finally:
                try:
                    await browser.close()
                except Exception:
                    pass

    # ── logging ────────────────────────────────────────────────────────────────

    async def send_log(self, message: str, level: str = "INFO"):
        log_line = f"[{datetime.now().strftime('%H:%M:%S')}] [{level}] [{self.instance_id}] {message}"
        print(log_line)
        try:
            r.lpush("ttm:logs", log_line)
            r.ltrim("ttm:logs", 0, 100)
        except Exception:
            pass
        try:
            bot = get_tg_bot()
            if bot:
                await bot.send_message(
                    chat_id=config.get("telegram_chat_id", ""),
                    text=f"<b>[{self.instance_id}]</b> {message}",
                    parse_mode="HTML",
                )
        except Exception:
            pass

    # ── lifecycle ──────────────────────────────────────────────────────────────

    def register_worker(self):
        r.setex(self.worker_key, self.heartbeat_ttl, datetime.now().isoformat())

    def heartbeat(self):
        r.setex(self.worker_key, self.heartbeat_ttl, datetime.now().isoformat())

    def unregister_worker(self):
        r.delete(self.worker_key)

    async def global_stopped(self) -> bool:
        return r.get("ttm:global_stop") == "1"

    async def is_running(self) -> bool:
        return r.get("ttm:running") == "1"

    async def set_global_stop(self):
        r.set("ttm:global_stop", "1", ex=7200)
        r.incr("ttm:success_count")
        await self.send_log("🚨 ได้บัตรสำเร็จ! สั่งหยุดทุก worker แล้ว", "SUCCESS")

    # ── CAPTCHA ────────────────────────────────────────────────────────────────

    async def solve_captcha(self, sitekey: str, page_url: str) -> Optional[str]:
        captcha_key = config.get("captcha_key", "")
        if not captcha_key or captcha_key.startswith("YOUR_"):
            return None

        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                resp = await client.post(
                    "http://2captcha.com/in.php",
                    data={
                        "key": captcha_key,
                        "method": "turnstile",
                        "googlekey": sitekey,
                        "pageurl": page_url,
                        "json": 1,
                    },
                )
                task_id = resp.json().get("request")
                if not task_id:
                    return None
                for _ in range(40):
                    await asyncio.sleep(2.5)
                    res = await client.get(
                        "http://2captcha.com/res.php",
                        params={
                            "key": captcha_key,
                            "action": "get",
                            "id": task_id,
                            "json": 1,
                        },
                    )
                    data = res.json()
                    if data.get("status") == 1:
                        return data.get("request")
            except Exception as e:
                await self.send_log(f"CAPTCHA error: {e}", "ERROR")
        return None

    # ── Queue-it aware browser flow ─────────────────────────────────────────────

    def _qi_frames(self, page):
        """All frames to search — Queue-it widgets often live in an iframe
        (or on queue-it.net), so we scan the main page and every child frame."""
        try:
            return [page] + [f for f in page.frames]
        except Exception:
            return [page]

    async def _qi_click_text(self, page, behavior, texts: List[str]) -> bool:
        """Click the first visible button/link/role=button matching any text,
        searching the main page AND all iframes, with a human-like click."""
        for frame in self._qi_frames(page):
            for txt in texts:
                for sel in (
                    f"button:has-text('{txt}')",
                    f"a:has-text('{txt}')",
                    f"[role=button]:has-text('{txt}')",
                    f"input[value='{txt}']",
                ):
                    try:
                        loc = frame.locator(sel).first
                        if await loc.count() == 0 or not await loc.is_visible():
                            continue
                        box = await loc.bounding_box()
                        if box and frame == page:
                            await behavior.click(
                                page, box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
                            )
                        else:
                            await loc.click(timeout=3000)
                        return True
                    except Exception:
                        continue
        return False

    async def _qi_try_selector(self, page, behavior, selector: str) -> bool:
        """Human-click the first match of a CSS selector list (main + frames)."""
        for frame in self._qi_frames(page):
            try:
                loc = frame.locator(selector).first
                if await loc.count() == 0 or not await loc.is_visible():
                    continue
                box = await loc.bounding_box()
                if box and frame == page:
                    await behavior.click(
                        page, box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
                    )
                else:
                    await loc.click(timeout=3000)
                return True
            except Exception:
                continue
        return False

    async def _qi_in_queue(self, page) -> bool:
        """True while the page still looks like a Queue-it waiting screen."""
        try:
            url = (page.url or "").lower()
            if any(m.lower() in url for m in self.qi_queue_markers if "/" in m or "." in m):
                return True
            for frame in self._qi_frames(page):
                try:
                    body = (await frame.inner_text("body"))[:4000].lower()
                except Exception:
                    continue
                for m in ("entry zone", "buying queue", "waiting room", "you are now in",
                          "please wait", "your turn", "ห้องรอ", "กำลังรอ"):
                    if m in body:
                        return True
        except Exception:
            pass
        return False

    async def _qi_on_purchase_page(self, page) -> bool:
        """Heuristic: released from the queue onto a seat/cart page."""
        try:
            for frame in self._qi_frames(page):
                try:
                    if await frame.locator(self.qi_seat_selector).count() > 0:
                        return True
                    if await frame.locator(self.qi_addtocart_selector).count() > 0:
                        return True
                    body = (await frame.inner_text("body"))[:4000].lower()
                except Exception:
                    continue
                if any(k in body for k in ("เลือกที่นั่ง", "เลือกโซน", "select seat", "ใส่ตะกร้า", "add to cart")):
                    return True
        except Exception:
            pass
        return False

    async def _qi_notify_payment_ready(self, page, proxy: Optional[str]) -> None:
        """Hold-only deliverable: capture proof + handoff data so a human can
        finish payment (OTP/3DS) on the already-warmed session."""
        url = ""
        shot_path = ""
        cookie_str = ""
        try:
            url = page.url
        except Exception:
            pass
        try:
            shot_path = f"/app/payment_ready_{self.instance_id}.png"
            await page.screenshot(path=shot_path, full_page=True)
        except Exception:
            shot_path = ""
        try:
            ctx_cookies = await page.context.cookies()
            cookie_str = "; ".join(f"{c['name']}={c['value']}" for c in ctx_cookies)
        except Exception:
            pass

        handoff = {
            "worker": self.instance_id,
            "proxy": (proxy[-16:] if proxy else "direct"),
            "checkout_url": url,
            "cookies": cookie_str,
            "ts": datetime.now().isoformat(),
        }
        try:
            r.lpush("ttm:payment_ready", json.dumps(handoff))
            r.ltrim("ttm:payment_ready", 0, 50)
        except Exception:
            pass

        await self.send_log(
            f"🎟️ HOLD สำเร็จ! ล็อกที่นั่งได้แล้ว — เปิดลิงก์นี้เพื่อจ่าย (เหลือเวลา ~{self.qi_hold_seconds // 60} นาที):\n{url}",
            "SUCCESS",
        )
        try:
            bot = get_tg_bot()
            if bot and shot_path:
                with open(shot_path, "rb") as fh:
                    await bot.send_photo(
                        chat_id=config.get("telegram_chat_id", ""),
                        photo=fh,
                        caption=f"🎟️ ล็อกที่นั่งสำเร็จ ({handoff['proxy']})\nจ่ายต่อที่: {url}",
                    )
        except Exception:
            pass

    async def run_queueit_mode(self):
        """Full ThaiTicketMajor + Queue-it browser flow (hold-only).

        State machine mirroring the real funnel:
          event page → click book → wait pre-queue countdown →
          Join the Queue → answer "Still here?" → wait progress bar →
          released → pick seat → add to cart → HOLD + notify human to pay.

        Multi-instance: each worker drives its own stealthed Chromium on its
        own leased proxy, so it holds an independent queue position. A small
        per-worker join jitter avoids identical timing across the fleet.
        """
        from playwright.async_api import async_playwright

        await self.send_log("🎫 เริ่มโหมด Queue-it Browser Flow (Hold-only)...")
        await self._update_leased_proxies()

        while not self.target_url:
            await self.send_log("❌ ตั้งค่า Target URL (หน้า event) ก่อนเริ่ม", "ERROR")
            await asyncio.sleep(5)
            self._refresh_config()

        proxy_str = self.proxies[0] if self.proxies else None
        proxy_cfg = self._parse_playwright_proxy(proxy_str) if proxy_str else None
        seed = proxy_str or self.instance_id
        bp = self._get_browser_profile(seed)
        fp = stealth.build_fingerprint(bp, seed)
        stealth_js = stealth.build_stealth_script(fp)
        viewport = {"width": int(fp.get("viewport_width", 1920)), "height": int(fp.get("viewport_height", 1080))}

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=self.qi_headless,
                proxy=proxy_cfg,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage",
                ],
            )
            context = await browser.new_context(
                user_agent=fp.get("user_agent"),
                viewport=viewport,
                device_scale_factor=float(fp.get("device_pixel_ratio", 1.0)),
                locale=(fp.get("language") or "th-TH").split(",")[0],
                timezone_id=fp.get("timezone", "Asia/Bangkok"),
            )
            await context.add_init_script(stealth_js)
            page = await context.new_page()
            try:
                cdp = await context.new_cdp_session(page)
                await cdp.send("Page.addScriptToEvaluateOnNewDocument", {"source": stealth_js})
            except Exception:
                pass

            behavior = stealth.HumanBehavior(seed, viewport)
            deadline = time.time() + self.qi_max_minutes * 60
            phase = "open"

            try:
                await page.goto(self.target_url, timeout=60000, wait_until="domcontentloaded")
                await self.send_log(f"🔗 เปิดหน้า event: {self.target_url}")
                await behavior.wander(page, moves=3)

                while not self.success and time.time() < deadline:
                    if await self.global_stopped() or not await self.is_running():
                        await self.send_log("⏹ STOP — ออกจาก Queue-it flow")
                        break

                    # Highest priority: never get dropped by the inactivity modal.
                    if await self._qi_click_text(page, behavior, self.qi_stillhere_texts):
                        await self.send_log("🟢 ตอบ 'Still here? → Yes' อัตโนมัติ", "DEBUG")
                        await behavior.think(0.2, 0.6)
                        continue

                    # Released onto the real purchase page?
                    if await self._qi_on_purchase_page(page):
                        if phase != "purchase":
                            phase = "purchase"
                            await self.send_log("🎯 ทะลุคิวแล้ว! เข้าหน้าซื้อบัตร — กำลังเลือกที่นั่ง", "SUCCESS")
                        await self._qi_try_selector(page, behavior, self.qi_seat_selector)
                        await behavior.think(0.3, 0.9)
                        if await self._qi_try_selector(page, behavior, self.qi_addtocart_selector):
                            await self.send_log("🛒 กดใส่ตะกร้า/ดำเนินการต่อแล้ว", "INFO")
                            await behavior.think(1.0, 2.0)
                            body = ""
                            try:
                                body = (await page.inner_text("body"))[:4000].lower()
                            except Exception:
                                pass
                            url_l = (page.url or "").lower()
                            if any(k in body for k in (
                                "checkout", "ชำระเงิน", "บัตรเครดิต", "payment",
                                "ยืนยันการสั่งซื้อ", "order summary", "สรุปคำสั่งซื้อ",
                            )) or any(k in url_l for k in ("checkout", "cart", "payment", "order")):
                                await self._qi_notify_payment_ready(page, proxy_str)
                                self.success = True
                                if self.qi_stop_on_first:
                                    await self.set_global_stop()
                                await self.send_log(
                                    f"⌛ คงเซสชันไว้ {self.qi_hold_seconds}s เพื่อให้จ่ายเงินต่อ...", "INFO"
                                )
                                await asyncio.sleep(self.qi_hold_seconds)
                                break
                        continue

                    # Still in the waiting funnel → try to join, else keep alive.
                    if await self._qi_in_queue(page):
                        if await self._qi_click_text(page, behavior, self.qi_join_texts):
                            if phase != "queue":
                                phase = "queue"
                                await self.send_log("⏩ กด 'Join the Queue' แล้ว — กำลังรอคิว", "INFO")
                        elif phase == "queue":
                            await behavior.wander(page, moves=1)
                        await asyncio.sleep(random.uniform(0.8, 1.8))
                        continue

                    # Pre-queue: event page or countdown — try the book button.
                    if await self._qi_try_selector(page, behavior, self.qi_book_selector):
                        await self.send_log("📨 กดปุ่มจอง/ซื้อบัตรแล้ว", "INFO")
                        # Small per-worker jitter so the fleet doesn't join in lockstep.
                        await asyncio.sleep(random.uniform(0.1, 1.0))
                        await behavior.think(0.4, 1.0)
                        continue

                    # Countdown not finished / nothing actionable → gentle reload.
                    await behavior.wander(page, moves=1)
                    await asyncio.sleep(random.uniform(1.5, 3.0))
                    try:
                        await page.reload(timeout=30000, wait_until="domcontentloaded")
                    except Exception:
                        pass

                if not self.success and time.time() >= deadline:
                    await self.send_log("⌛ หมดเวลา (max_minutes) — ออกจาก Queue-it flow", "WARN")

            except Exception as e:
                await self.send_log(f"❌ Queue-it flow error: {e}", "ERROR")
            finally:
                try:
                    await context.close()
                    await browser.close()
                except Exception:
                    pass

    # ── Main run loop ──────────────────────────────────────────────────────────

    async def run(self):
        self.register_worker()
        try:
            await self.send_log("Worker พร้อมแล้ว ⏳ — รอคำสั่ง START จาก Dashboard")

            # ── Standby: wait for START ───────────────────────────────────────
            while not await self.is_running():
                self.heartbeat()
                await asyncio.sleep(2)

            self._refresh_config()

            # Browser-only bot. "general" = generic button-click automation;
            # anything else (incl. legacy "ttm") → real Queue-it funnel.
            if self.bot_mode == "general":
                await self.run_general_mode()
            else:
                await self.run_queueit_mode()

        finally:
            self.unregister_worker()


if __name__ == "__main__":
    asyncio.run(TTMWorker().run())

