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
from gql import gql
from typing import Dict, List, Optional
from urllib.parse import urlparse
from playwright.async_api import async_playwright

# Akamai BMP + TLS-spoofing transport
from akamai import (
    AkamaiCookieJar,
    AkamaiSession,
    AKAMAI_TTL,
    build_provider,
    detect_akamai_block,
)
from tls_transport import TLSGraphQLClient, impersonate_target_for

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

DEFAULT_GRAPHQL_URL = "https://api.thaiticketmajor.com/graphql/v2"


def get_graphql_url() -> str:
    return os.environ.get("GRAPHQL_URL") or config.get("graphql_url") or DEFAULT_GRAPHQL_URL


def build_graphql_client(
    headers: dict,
    proxy: Optional[str],
    *,
    cookies: Optional[Dict[str, str]] = None,
    impersonate: str = "chrome131",
    timeout: float = 30.0,
) -> TLSGraphQLClient:
    """Construct a TLS-spoofing GraphQL client targeting the current
    `graphql_url`, with Akamai cookies pre-injected when supplied."""
    return TLSGraphQLClient(
        get_graphql_url(),
        headers=headers,
        cookies=cookies,
        proxy=proxy,
        impersonate=impersonate,
        timeout=timeout,
    )




# ── Queue-it Token Pool ────────────────────────────────────────────────────────
# Each proxy gets its own cached token. Workers fetch tokens in the background
# so that when the purchase loop fires, tokens are already warm and ready.

QUEUE_TOKEN_TTL = 840  # seconds (14 min — conservative vs Queue-it 15 min)
QUEUE_CAPTCHA_URL_TPL = "https://www.thaiticketmajor.com/concert/{event_id}"

class QueueTokenPool:
    """Redis-backed per-proxy Queue-it token cache."""

    @staticmethod
    def _key(proxy: Optional[str]) -> str:
        proxy_val = proxy or "direct_connection"
        h = hashlib.md5(proxy_val.encode()).hexdigest()[:10]
        return f"ttm:qt:{h}"

    @classmethod
    def store(cls, proxy: str, queue_token: str, captcha_token: str) -> None:
        payload = json.dumps({
            "queue_token": queue_token,
            "captcha_token": captcha_token,
            "expires_at": time.time() + QUEUE_TOKEN_TTL,
        })
        r.setex(cls._key(proxy), QUEUE_TOKEN_TTL, payload)

    @classmethod
    def get(cls, proxy: str) -> Optional[Dict]:
        raw = r.get(cls._key(proxy))
        if not raw:
            return None
        data = json.loads(raw)
        if data["expires_at"] < time.time():
            r.delete(cls._key(proxy))
            return None
        return data

    @classmethod
    def invalidate(cls, proxy: str) -> None:
        r.delete(cls._key(proxy))

    @classmethod
    def warmup_count(cls, proxies: List[str]) -> int:
        """How many proxies already have a live token."""
        return sum(1 for p in proxies if cls.get(p) is not None)


# ── Shared GraphQL queries (compiled once) ────────────────────────────────────
QUEUE_STATUS_QUERY = gql("""
    query QueueStatus($eventId: String!) {
        queueStatus(eventId: $eventId) { status token captchaSitekey }
    }
""")

ADD_TO_CART_MUTATION = gql("""
    mutation AddToCart($input: AddToCartInput!) {
        addToCart(input: $input) { success cartId }
    }
""")

CHECKOUT_MUTATION = gql("""
    mutation Checkout($input: CheckoutInput!) {
        checkout(input: $input) {
            success orderId paymentUrl status
        }
    }
""")


# ── TTMWorker ─────────────────────────────────────────────────────────────────

class TTMWorker:
    def __init__(self):
        self.instance_id = f"worker-{uuid.uuid4().hex[:8]}"
        self.heartbeat_ttl = 30
        self.worker_key = f"worker:{self.instance_id}"
        self.success = False
        self.current_profile_idx = 0
        # Akamai state — provider + cookie jar; rebuilt when config changes
        self._akamai_jar = AkamaiCookieJar(r)
        self._akamai_provider = None  # built lazily in _refresh_config
        self._akamai_provider_name = ""
        self._refresh_config()

    # ── config ─────────────────────────────────────────────────────────────────

    def _refresh_config(self):
        global config
        config = load_config(r)
        self.bot_mode: str = config.get("bot_mode", "ttm")
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

        # Rebuild Akamai provider only when the configured name changes —
        # PlaywrightProvider creates Chromium contexts on demand so the
        # object itself is cheap to keep around.
        provider_name = str(config.get("akamai_provider") or "noop").lower()
        if provider_name != self._akamai_provider_name or self._akamai_provider is None:
            self._akamai_provider = build_provider(config)
            self._akamai_provider_name = provider_name

    def _akamai_target_url(self) -> str:
        """URL the sensor provider should solve against. Prefers an explicit
        `akamai_target_url`, then `target_url`, then derives one from the
        event id for the TTM concert flow."""
        explicit = config.get("akamai_target_url") or ""
        if explicit:
            return explicit
        if self.target_url:
            return self.target_url
        if self.event_id:
            return f"https://www.thaiticketmajor.com/concert/{self.event_id}"
        return "https://www.thaiticketmajor.com/"

    def _akamai_session(self) -> AkamaiSession:
        return AkamaiSession(
            self._akamai_provider,
            self._akamai_jar,
            self._akamai_target_url(),
        )

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

    # ── Queue-it token fetch ───────────────────────────────────────────────────

    async def _fetch_queue_token(self, proxy: str) -> Optional[Dict]:
        """
        Fetch a fresh Queue-it token for *proxy* using the TLS-spoofing
        transport and any cached Akamai cookies. Persists the result in
        QueueTokenPool.
        """
        bp = self._get_browser_profile(proxy or "default_seed")
        impersonate = impersonate_target_for(bp)
        # Hot-path: cache-only read; the warmup loop is responsible for
        # populating Akamai cookies via the configured sensor provider.
        akamai_cookies = self._akamai_session().peek(proxy)

        headers = {
            "User-Agent": bp.get("user_agent") or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json, */*",
            "Accept-Language": bp.get("language", "th-TH,th;q=0.9,en;q=0.8"),
            "Origin": "https://www.thaiticketmajor.com",
            "Referer": f"https://www.thaiticketmajor.com/concert/{self.event_id}",
            "x-ttm-version": "2026.5.2",
            "x-correlation-id": str(uuid.uuid4()),
            "apollographql-client-name": "ttm-web-2026",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
        }
        if bp.get("browser") in ("chrome", "edge") and bp.get("sec_ch_ua"):
            headers["Sec-CH-UA"] = bp["sec_ch_ua"]
            headers["Sec-CH-UA-Mobile"] = "?0"
            headers["Sec-CH-UA-Platform"] = f'"{bp.get("sec_ch_ua_platform", "Windows")}"'

        client = build_graphql_client(
            headers, proxy, cookies=akamai_cookies, impersonate=impersonate
        )
        try:
            async with client as session:
                qres = await session.execute(
                    QUEUE_STATUS_QUERY, variable_values={"eventId": self.event_id}
                )
                if detect_akamai_block(
                    session.last_status,
                    session.last_response_text,
                    session.last_response_cookies,
                ):
                    self._akamai_session().invalidate(proxy)
                    proxy_log = (proxy[-12:] if proxy else "direct")
                    await self.send_log(
                        f"🛡 Akamai blocked queue token fetch ({proxy_log}) — cookies invalidated",
                        "WARN",
                    )
                    return None

                qdata = qres.get("queueStatus", {})

                # No queue active — token not needed
                if qdata.get("status") in ("open", None, ""):
                    QueueTokenPool.store(proxy, "", "")
                    return {"queue_token": "", "captcha_token": ""}

                queue_token = qdata.get("token", "")
                captcha_token = ""

                if qdata.get("captchaSitekey"):
                    page_url = QUEUE_CAPTCHA_URL_TPL.format(event_id=self.event_id)
                    captcha_token = await self.solve_captcha(
                        qdata["captchaSitekey"], page_url
                    ) or ""

                QueueTokenPool.store(proxy, queue_token, captcha_token)
                return {"queue_token": queue_token, "captcha_token": captcha_token}

        except Exception as e:
            proxy_log = (proxy[-12:] if proxy else "direct")
            await self.send_log(f"Queue token fetch failed ({proxy_log}): {e}", "WARN")
            return None

    async def _get_or_fetch_queue_token(self, proxy: str) -> Dict:
        """Return cached token or fetch a fresh one. Guaranteed to return a dict."""
        cached = QueueTokenPool.get(proxy)
        if cached:
            return cached
        result = await self._fetch_queue_token(proxy)
        return result or {"queue_token": "", "captcha_token": ""}

    # ── Token warmup background task ──────────────────────────────────────────

    async def _token_warmup_loop(self):
        """
        Background coroutine that continuously pre-fetches Queue-it tokens
        for all configured proxies so purchases don't have to wait.
        Runs until the worker is done.
        """
        while not self.success:
            if not await self.is_running():
                await asyncio.sleep(2)
                continue

            self._refresh_config()
            proxies = self.proxies
            if not proxies or not self.event_id:
                await asyncio.sleep(5)
                continue

            # Fetch only for proxies that don't have a live token yet
            stale = [p for p in proxies if QueueTokenPool.get(p) is None]
            if stale:
                warm = len(proxies) - len(stale)
                await self.send_log(
                    f"🔑 Token warmup: {warm}/{len(proxies)} warm, fetching {len(stale)}…",
                    "DEBUG",
                )
                tasks = [self._fetch_queue_token(p) for p in stale]
                await asyncio.gather(*tasks, return_exceptions=True)

            # Sleep until tokens are ~80% through their TTL
            await asyncio.sleep(QUEUE_TOKEN_TTL * 0.7)

    # ── Akamai cookie warmup ───────────────────────────────────────────────────

    async def _akamai_warmup_loop(self):
        """Pre-fetch validated Akamai cookies for each proxy so purchase
        waves don't have to block on the (slow) sensor solve. Concurrency
        is intentionally capped — PlaywrightProvider spawns real Chromium
        instances and we don't want to thrash the host."""
        provider_name = self._akamai_provider_name
        if provider_name == "noop":
            await self.send_log(
                "🛡 Akamai provider = noop — skipping warmup loop "
                "(set akamai_provider=playwright|hyper to enable)",
                "DEBUG",
            )
            return

        sem_size = 2 if provider_name in ("playwright", "local", "browser") else 6
        sem = asyncio.Semaphore(sem_size)

        async def _solve_one(proxy: Optional[str]) -> None:
            bp = self._get_browser_profile(proxy or "default_seed")
            async with sem:
                sess = self._akamai_session()
                await sess.prepare(proxy, bp, force_refresh=True)

        while not self.success:
            if not await self.is_running():
                await asyncio.sleep(2)
                continue

            self._refresh_config()
            proxies = self.proxies
            if not proxies:
                await asyncio.sleep(5)
                continue

            stale = [p for p in proxies if self._akamai_jar.get(p) is None]
            if stale:
                warm = len(proxies) - len(stale)
                await self.send_log(
                    f"🛡 Akamai warmup ({self._akamai_provider_name}): "
                    f"{warm}/{len(proxies)} warm, solving {len(stale)}…",
                    "DEBUG",
                )
                await asyncio.gather(
                    *(_solve_one(p) for p in stale), return_exceptions=True
                )

            await asyncio.sleep(AKAMAI_TTL * 0.7)

    # ── Single purchase attempt ────────────────────────────────────────────────

    async def _attempt(
        self,
        proxy: str,
        ticket_type: str,
        profile: Dict,
        quantity: int = 2,
    ) -> bool:
        """
        One full purchase attempt using a browser-fingerprinted session.
        Uses QueueTokenPool so queue tokens are reused across attempts.
        """
        if await self.global_stopped():
            return False

        card = profile["card"]
        qt = await self._get_or_fetch_queue_token(proxy)
        bp = self._get_browser_profile(proxy)

        # Build full Antidetect-style headers from the browser profile
        browser = bp.get("browser", "chrome")
        headers: Dict[str, str] = {
            "User-Agent": bp.get("user_agent", ""),
            "Accept": "application/json, */*",
            "Accept-Language": bp.get("language", "th-TH"),
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Origin": "https://www.thaiticketmajor.com",
            "Referer": f"https://www.thaiticketmajor.com/concert/{self.event_id}",
            "x-ttm-version": "2026.5.2",
            "x-correlation-id": str(uuid.uuid4()),
            "apollographql-client-name": "ttm-web-2026",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
        }

        # Chromium-based browsers send Sec-CH-UA headers
        if browser in ("chrome", "edge"):
            sec_ch_ua = bp.get("sec_ch_ua", "")
            sec_ch_ua_platform = bp.get("sec_ch_ua_platform", "Windows")
            if sec_ch_ua:
                headers["Sec-CH-UA"] = sec_ch_ua
                headers["Sec-CH-UA-Mobile"] = "?0"
                headers["Sec-CH-UA-Platform"] = f'"{sec_ch_ua_platform}"'

        if bp.get("do_not_track"):
            headers["DNT"] = "1"

        if qt.get("queue_token"):
            headers["x-queueit-token"] = qt["queue_token"]
        if qt.get("captcha_token"):
            headers["x-captcha-token"] = qt["captcha_token"]

        # Akamai cookies — hot-path read only, no inline solving. The
        # warmup loop owns provider.acquire(); here we just consume cache.
        akamai_session = self._akamai_session()
        akamai_cookies = akamai_session.peek(proxy)
        impersonate = impersonate_target_for(bp)

        client = build_graphql_client(
            headers, proxy, cookies=akamai_cookies, impersonate=impersonate
        )

        try:
            async with client as session:
                # ── Add to Cart ───────────────────────────────────────────────
                cart_result = await session.execute(
                    ADD_TO_CART_MUTATION,
                    variable_values={
                        "input": {
                            "eventId": self.event_id,
                            "ticketType": ticket_type,
                            "quantity": quantity,
                            "priceTier": "standard",
                        }
                    },
                )

                # Drop cookies if Akamai downgraded _abck mid-flight
                if detect_akamai_block(
                    session.last_status,
                    session.last_response_text,
                    session.last_response_cookies,
                ):
                    akamai_session.invalidate(proxy)
                    proxy_log = (proxy[-12:] if proxy else "direct")
                    await self.send_log(
                        f"🛡 Akamai blocked addToCart ({ticket_type}|{proxy_log}) — cookies invalidated",
                        "WARN",
                    )
                    return False

                cart_data = cart_result.get("addToCart", {})

                # Token rejected by server → invalidate and retry next round
                if cart_data.get("errorCode") in ("QUEUE_TOKEN_INVALID", "QUEUE_REQUIRED"):
                    await self.send_log(
                        f"⚠ Queue token rejected ({proxy[-12:]}) — invalidating", "WARN"
                    )
                    QueueTokenPool.invalidate(proxy)
                    return False

                cart_id = cart_data.get("cartId")
                if not cart_id:
                    return False

                # ── Checkout ──────────────────────────────────────────────────
                final = await session.execute(
                    CHECKOUT_MUTATION,
                    variable_values={
                        "input": {
                            "cartId": cart_id,
                            "buyer": {
                                "fullName": profile["fullname"],
                                "email": profile["email"],
                                "phone": profile["phone"],
                                "nationalId": profile.get("id_card"),
                            },
                            "paymentMethod": "credit_card",
                            "card": {
                                "number": card["number"],
                                "expMonth": card["exp"][:2],
                                "expYear": "20" + card["exp"][2:],
                                "cvv": card["cvv"],
                                "name": profile["fullname"],
                            },
                            "queueToken": qt.get("queue_token"),
                        }
                    },
                )

                if detect_akamai_block(
                    session.last_status,
                    session.last_response_text,
                    session.last_response_cookies,
                ):
                    akamai_session.invalidate(proxy)
                    proxy_log = (proxy[-12:] if proxy else "direct")
                    await self.send_log(
                        f"🛡 Akamai blocked checkout ({ticket_type}|{proxy_log}) — cookies invalidated",
                        "WARN",
                    )
                    return False

                result = final.get("checkout", {})
                if result.get("success") or result.get("status") in ["success", "redirect"]:
                    self.success = True
                    await self.send_log(
                        f"🎉 สำเร็จ! Order: {result.get('orderId')} | "
                        f"{ticket_type} | {profile['email']}",
                        "SUCCESS",
                    )
                    await self.set_global_stop()
                    return True

                return False

        except Exception as e:
            err = str(e)
            if "queue" in err.lower() or "token" in err.lower():
                QueueTokenPool.invalidate(proxy)
            if "akamai" in err.lower() or "_abck" in err.lower() or "403" in err:
                akamai_session.invalidate(proxy)
            proxy_log = (proxy[-12:] if proxy else "direct")
            await self.send_log(
                f"Attempt error ({ticket_type}|{proxy_log}): {err}", "ERROR"
            )
            return False

    # ── Concurrent purchase wave ───────────────────────────────────────────────

    async def _purchase_wave_custom(self, proxies_list: List[str]) -> bool:
        if not self.profiles:
            await self.send_log("ไม่มี profiles — ตั้งค่าผ่าน Dashboard ก่อน", "ERROR")
            return False

        tickets = self.ticket_priorities

        for ticket_type in tickets:
            if await self.global_stopped() or not await self.is_running():
                return False

            tasks = []
            for proxy in proxies_list:
                actual_proxy = None if proxy == "direct" else proxy
                # Select a profile
                p_idx = 0
                if actual_proxy:
                    p_idx = int(hashlib.md5(actual_proxy.encode()).hexdigest(), 16) % len(self.profiles)
                else:
                    # Deterministically distribute direct profiles by worker index if any
                    p_idx = self.current_profile_idx % len(self.profiles)
                
                profile = self.profiles[p_idx]
                tasks.append(self._attempt(actual_proxy, ticket_type, profile))

            if not tasks:
                continue

            results = await asyncio.gather(*tasks, return_exceptions=True)

            for res in results:
                if res is True:
                    return True

            await asyncio.sleep(random.uniform(0.15, 0.45))

        return False

    async def _purchase_wave(self) -> bool:
        return await self._purchase_wave_custom(self.proxies)

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

            # Route to general browser automation mode if selected
            if self.bot_mode == "general":
                await self.run_general_mode()
                return

            # Dynamic initial lease before starting loops
            await self._update_leased_proxies()
            
            await self.send_log(
                f"▶ START — Worker เริ่มทำงาน | "
                f"Proxies (Leased): {len(self.proxies)} | Profiles: {len(self.profiles)}"
            )

            # Launch token warmup, Akamai warmup, and proxy lease refresh tasks
            warmup_task = asyncio.create_task(self._token_warmup_loop())
            lease_task = asyncio.create_task(self._proxy_lease_loop())
            akamai_task = asyncio.create_task(self._akamai_warmup_loop())

            try:
                # ── Main purchase loop ────────────────────────────────────────
                while not self.success:
                    self.heartbeat()
                    self._refresh_config()

                    # Return to standby if STOP pressed
                    if await self.global_stopped() or not await self.is_running():
                        await self.send_log("⏹ STOP — Worker กลับสู่ Standby mode")
                        while not await self.is_running():
                            self.heartbeat()
                            await asyncio.sleep(2)
                        self.success = False
                        await self.send_log("▶ START อีกครั้ง — Worker กลับมาทำงาน")
                        continue

                    if not self.proxies:
                        # If no proxies configured, perform direct local connection request
                        # Add a fake single string 'direct' to bypass empty loops
                        active_proxies_list = ["direct"]
                    else:
                        active_proxies_list = self.proxies

                    warm = QueueTokenPool.warmup_count(self.proxies) if self.proxies else 0
                    akamai_warm = (
                        self._akamai_jar.warm_count(self.proxies)
                        if self.proxies else 0
                    )
                    await self.send_log(
                        f"🚀 ยิง wave | "
                        f"proxies={len(self.proxies)} warm={warm} "
                        f"akamai={akamai_warm}/{len(self.proxies)} "
                        f"tickets={self.ticket_priorities}"
                    )

                    # We pass active_proxies_list to purchase wave
                    if await self._purchase_wave_custom(active_proxies_list):
                        return  # success — exit

                    # Fast re-poll: no long sleep, just a brief jitter
                    await asyncio.sleep(random.uniform(0.3, 0.8))

            finally:
                warmup_task.cancel()
                lease_task.cancel()
                akamai_task.cancel()
                try:
                    await asyncio.gather(
                        warmup_task, lease_task, akamai_task,
                        return_exceptions=True,
                    )
                except Exception:
                    pass

        finally:
            self.unregister_worker()


if __name__ == "__main__":
    asyncio.run(TTMWorker().run())

