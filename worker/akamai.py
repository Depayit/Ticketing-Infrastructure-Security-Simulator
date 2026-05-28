"""
Akamai Bot Manager defence module.

Handles three coupled problems:

  1. **`_abck` cookie state machine** — parse the cookie segments to know
     whether the current session has been validated by Akamai
     (`status == -1`), is pending (`0`), or was rejected (`1`).
  2. **`sensor_data` orchestration** — pluggable providers that produce a
     validated `_abck` + companion cookies for a given target URL through
     a given proxy. Built-in providers:
        - `NoopProvider`           (default, no solving)
        - `HyperSolutionsProvider` (external pay-per-solve API)
        - `PlaywrightProvider`     (local real browser warmup)
  3. **Per-proxy cookie jar** — Redis-backed so workers sharing a proxy
     reuse validated cookies instead of solving repeatedly.

The orchestrator `AkamaiSession.prepare(proxy, browser_profile)` returns a
cookie dict that the GraphQL transport can inject. After each GraphQL call,
the worker should pass the response cookies through `detect_akamai_block()`
to decide whether to invalidate and re-solve.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Protocol
from urllib.parse import urlparse

log = logging.getLogger("akamai")

AKAMAI_TTL = 600  # 10 minutes; conservative vs the 15-minute `_abck` lifetime
KEY_PREFIX = "ttm:akamai:"

# Cookies Akamai BMP sets that we care about
AKAMAI_COOKIE_NAMES = frozenset({
    "_abck", "bm_sz", "ak_bmsc", "bm_sv", "bm_mi", "bm_so", "bm_lso", "ak_bm",
})


# ── _abck state machine ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class AbckStatus:
    """Decoded state of an ``_abck`` cookie.

    Public reverse-engineering notes on the cookie format:

        ``<random_hex>~<status>~<padding>~<post_count>~<request_count>~<flags>``

    The second segment is the primary signal:

    * ``0``  — fresh session, no sensor payload accepted yet
    * ``-1`` — validated (sensor accepted, requests will be honoured)
    * ``1``  — invalidated / challenged / blocked

    Some Akamai versions also embed ``||0||0||-1||...`` style flag groups in a
    later segment; we treat the presence of ``||-1`` without a leading ``||0``
    as a secondary validation signal.
    """

    raw: str
    status: int  # -1 valid · 0 fresh · 1 invalid · 99 unparsable
    is_valid: bool
    needs_sensor: bool

    @classmethod
    def parse(cls, raw: Optional[str]) -> "AbckStatus":
        if not raw:
            return cls(raw="", status=99, is_valid=False, needs_sensor=True)

        parts = raw.split("~")
        try:
            status = int(parts[1]) if len(parts) >= 2 else 99
        except ValueError:
            status = 99

        is_valid = status == -1
        # Secondary heuristic — some Akamai versions don't update the primary
        # status field but flip the trailing flag group to `||-1`.
        if not is_valid and "||-1" in raw:
            head = raw.split("||", 1)[0]
            if "~0~" not in head:
                is_valid = True

        return cls(raw=raw, status=status, is_valid=is_valid, needs_sensor=not is_valid)


# ── Sensor providers ─────────────────────────────────────────────────────────


class SensorProvider(Protocol):
    """Produces a validated Akamai cookie set for a target URL via a proxy."""

    name: str

    async def acquire(
        self,
        target_url: str,
        proxy: Optional[str],
        browser_profile: Mapping[str, Any],
    ) -> Optional[Dict[str, str]]:
        ...


class NoopProvider:
    """No-op provider — emits a warning, returns nothing.

    Use when you want the rest of the bot to function on targets that don't
    deploy Akamai, or as a baseline to measure how badly we get rate-limited
    without sensor solving.
    """

    name = "noop"

    async def acquire(self, target_url, proxy, browser_profile):
        log.warning(
            "akamai.NoopProvider in use — sensor_data NOT being generated. "
            "Configure `akamai_provider` in config.json to enable real solving."
        )
        return None


class HyperSolutionsProvider:
    """Provider backed by an external pay-per-solve API
    (hyper-solutions.net or any compatible Akamai-sensor service).

    The API contract assumed here is the de-facto standard:

        POST {api_url}/akamai/solve
        Headers: Authorization: Bearer {api_key}
        JSON: {"url": "...", "userAgent": "...", "proxy": "..."}

        → 200 {"cookies": {"_abck": "...", "bm_sz": "...", ...}}

    Adapt `_extract_cookies` if your vendor returns a different envelope.
    """

    name = "hyper"

    def __init__(self, api_url: str, api_key: str, timeout: float = 25.0):
        if not api_url:
            raise ValueError("HyperSolutionsProvider requires api_url")
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    @staticmethod
    def _extract_cookies(data: Any) -> Optional[Dict[str, str]]:
        if not isinstance(data, dict):
            return None
        if isinstance(data.get("cookies"), dict):
            return {k: str(v) for k, v in data["cookies"].items() if v}
        # Common alternative envelope shapes
        flat = {}
        for k in ("_abck", "abck", "bm_sz", "ak_bmsc"):
            if k in data and data[k]:
                key = "_abck" if k == "abck" else k
                flat[key] = str(data[k])
        return flat or None

    async def acquire(self, target_url, proxy, browser_profile):
        from tls_transport import TLSClient  # local import to avoid cycles

        payload = {
            "url": target_url,
            "userAgent": browser_profile.get("user_agent", ""),
            "proxy": proxy or "",
        }
        try:
            async with TLSClient(
                impersonate="chrome131",
                timeout=self.timeout,
                default_headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
            ) as cli:
                resp = await cli.post(f"{self.api_url}/akamai/solve", json=payload)
                if resp.status_code != 200:
                    log.warning(
                        "HyperSolutionsProvider HTTP %s: %s",
                        resp.status_code, resp.text[:160],
                    )
                    return None
                return self._extract_cookies(resp.json())
        except Exception as e:
            log.warning("HyperSolutionsProvider exception: %s", e)
            return None


# Akamai sensor POSTs go to paths shaped like /<random>/<random>{,/...} that
# don't appear as static assets. We accept either of those signals.
_SENSOR_PATH_RE = re.compile(r"/[\w-]{6,}/[\w-]{4,}(?:/[\w-]{4,})?$")


class PlaywrightProvider:
    """Local-browser provider — opens Chromium via Playwright on the target
    URL, waits for the Akamai sensor POST to land, then exports the cookie
    jar. Slow (~3–6 s per warmup) but free and produces realistic cookies.

    Designed to be called from a background warmup loop so purchase waves
    don't block on it. Concurrency should be limited by the caller (real
    browsers are RAM-hungry).
    """

    name = "playwright"

    def __init__(self, headless: bool = True, wait_ms: int = 6000):
        self.headless = headless
        self.wait_ms = wait_ms

    @staticmethod
    def _parse_proxy(proxy: Optional[str]) -> Optional[Dict[str, str]]:
        if not proxy:
            return None
        url = proxy if "://" in proxy else f"http://{proxy}"
        try:
            parsed = urlparse(url)
        except Exception:
            return None
        if not parsed.hostname:
            return None
        server = f"{parsed.scheme or 'http'}://{parsed.hostname}"
        if parsed.port:
            server += f":{parsed.port}"
        cfg: Dict[str, str] = {"server": server}
        if parsed.username:
            cfg["username"] = parsed.username
        if parsed.password:
            cfg["password"] = parsed.password
        return cfg

    async def acquire(self, target_url, proxy, browser_profile):
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            log.error("Playwright not installed — cannot run PlaywrightProvider")
            return None

        proxy_cfg = self._parse_proxy(proxy)
        ua = browser_profile.get("user_agent")
        viewport = {
            "width": int(browser_profile.get("viewport_width", 1920)),
            "height": int(browser_profile.get("viewport_height", 1080)),
        }
        locale = (browser_profile.get("language", "th-TH") or "th-TH").split(",")[0]
        timezone = browser_profile.get("timezone", "Asia/Bangkok")

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=self.headless,
                    proxy=proxy_cfg,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                    ],
                )
                context = await browser.new_context(
                    user_agent=ua,
                    viewport=viewport,
                    locale=locale,
                    timezone_id=timezone,
                )
                await context.add_init_script(
                    "Object.defineProperty(navigator, 'webdriver', "
                    "{get: () => undefined});"
                )

                page = await context.new_page()
                sensor_posted = asyncio.Event()

                def on_request(req: Any) -> None:
                    if req.method != "POST":
                        return
                    body = req.post_data or ""
                    if "sensor_data" in body or _SENSOR_PATH_RE.search(req.url or ""):
                        sensor_posted.set()

                page.on("request", on_request)

                try:
                    await page.goto(
                        target_url, timeout=30000, wait_until="domcontentloaded"
                    )
                except Exception as e:
                    log.warning("PlaywrightProvider goto failed: %s", e)

                # Mouse movement so the sensor JS captures real pointer events
                try:
                    await page.mouse.move(120, 220, steps=10)
                    await page.mouse.move(420, 380, steps=15)
                    await page.mouse.move(680, 420, steps=12)
                except Exception:
                    pass

                try:
                    await asyncio.wait_for(
                        sensor_posted.wait(), timeout=self.wait_ms / 1000
                    )
                except asyncio.TimeoutError:
                    log.info(
                        "PlaywrightProvider: sensor POST not detected — "
                        "exporting whatever cookies were issued"
                    )

                # Let the server response that updates `_abck` settle
                await asyncio.sleep(0.5)

                raw_cookies = await context.cookies()
                cookies: Dict[str, str] = {
                    c["name"]: c["value"]
                    for c in raw_cookies
                    if c["name"] in AKAMAI_COOKIE_NAMES
                }

                await context.close()
                await browser.close()

                if not cookies.get("_abck"):
                    log.warning("PlaywrightProvider: no _abck cookie returned")
                    return cookies or None

                status = AbckStatus.parse(cookies["_abck"])
                if not status.is_valid:
                    log.info(
                        "PlaywrightProvider: _abck returned but not validated "
                        "(status=%s); downstream may still be challenged",
                        status.status,
                    )
                return cookies
        except Exception as e:
            log.exception("PlaywrightProvider exception: %s", e)
            return None


def build_provider(cfg: Mapping[str, Any]) -> SensorProvider:
    """Factory — pick a provider based on `akamai_provider` config key."""
    name = str(cfg.get("akamai_provider") or "noop").lower()

    if name in ("hyper", "hyper-solutions", "hypersolutions"):
        api_url = cfg.get("akamai_api_url", "")
        api_key = cfg.get("akamai_api_key", "")
        if not api_url or api_key.startswith("YOUR_") or not api_key:
            log.warning(
                "akamai_provider=hyper but akamai_api_url/akamai_api_key "
                "are missing — falling back to noop"
            )
            return NoopProvider()
        return HyperSolutionsProvider(api_url=api_url, api_key=api_key)

    if name in ("playwright", "local", "browser"):
        return PlaywrightProvider(
            headless=bool(cfg.get("akamai_headless", True)),
            wait_ms=int(cfg.get("akamai_wait_ms", 6000)),
        )

    return NoopProvider()


# ── Cookie jar ───────────────────────────────────────────────────────────────


class AkamaiCookieJar:
    """Redis-backed per-proxy Akamai cookie cache.

    Keyed by the MD5 of the proxy string so the same proxy used from any
    worker hits the same slot. On read we re-validate the `_abck` segment
    and evict if it has flipped to status `0` or `1`.
    """

    def __init__(self, redis_client: Any, ttl: int = AKAMAI_TTL):
        self.r = redis_client
        self.ttl = ttl

    @staticmethod
    def _key(proxy: Optional[str]) -> str:
        val = proxy or "direct"
        h = hashlib.md5(val.encode()).hexdigest()[:10]
        return f"{KEY_PREFIX}{h}"

    def get(self, proxy: Optional[str]) -> Optional[Dict[str, str]]:
        try:
            raw = self.r.get(self._key(proxy))
        except Exception:
            return None
        if not raw:
            return None
        try:
            data = json.loads(raw)
        except Exception:
            return None
        if data.get("expires_at", 0) < time.time():
            try:
                self.r.delete(self._key(proxy))
            except Exception:
                pass
            return None
        cookies = data.get("cookies") or {}
        if not cookies.get("_abck"):
            return None
        # Cookies are only useful if `_abck` still looks valid
        if not AbckStatus.parse(cookies["_abck"]).is_valid:
            try:
                self.r.delete(self._key(proxy))
            except Exception:
                pass
            return None
        return cookies

    def store(self, proxy: Optional[str], cookies: Mapping[str, str]) -> None:
        if not cookies:
            return
        payload = {
            "cookies": dict(cookies),
            "expires_at": time.time() + self.ttl,
            "stored_at": time.time(),
        }
        try:
            self.r.setex(self._key(proxy), self.ttl, json.dumps(payload))
        except Exception:
            pass

    def invalidate(self, proxy: Optional[str]) -> None:
        try:
            self.r.delete(self._key(proxy))
        except Exception:
            pass

    def warm_count(self, proxies: List[Optional[str]]) -> int:
        return sum(1 for p in proxies if self.get(p) is not None)


# ── Orchestrator ─────────────────────────────────────────────────────────────


class AkamaiSession:
    """Glue: provider + jar + a single target URL.

    `prepare()` returns a cookie dict to inject into the next GraphQL request.
    An empty dict means we couldn't get validated cookies — the caller can
    decide whether to proceed without them (e.g. a non-Akamai endpoint) or
    skip the attempt.
    """

    def __init__(
        self,
        provider: SensorProvider,
        jar: AkamaiCookieJar,
        target_url: str,
    ):
        self.provider = provider
        self.jar = jar
        self.target_url = target_url

    async def prepare(
        self,
        proxy: Optional[str],
        browser_profile: Mapping[str, Any],
        force_refresh: bool = False,
        allow_solve: bool = True,
    ) -> Dict[str, str]:
        """Return cached cookies, optionally solving on cache miss.

        ``allow_solve=False`` keeps callers off the slow path — purchase
        attempts should use this so they never block on a sensor solve;
        the background warmup loop should call with the default ``True``.
        """
        if not force_refresh:
            cached = self.jar.get(proxy)
            if cached:
                return cached

        if not allow_solve:
            return {}

        cookies = await self.provider.acquire(
            self.target_url, proxy, browser_profile
        )
        if not cookies:
            return {}

        self.jar.store(proxy, cookies)
        return cookies

    def peek(self, proxy: Optional[str]) -> Dict[str, str]:
        """Synchronous read of cached cookies — empty dict on cache miss.
        Use this on the hot path where solving would be too slow."""
        cached = self.jar.get(proxy)
        return cached or {}

    def invalidate(self, proxy: Optional[str]) -> None:
        self.jar.invalidate(proxy)


# ── Block detection ──────────────────────────────────────────────────────────


_BLOCK_BODY_MARKERS = (
    "Pardon Our Interruption",
    "Access Denied",
    "Reference #",
    "you have been blocked",
    "AkamaiGHost",
)


def detect_akamai_block(
    status_code: int,
    response_text: str,
    new_cookies: Mapping[str, str],
) -> bool:
    """Decide whether the response indicates an Akamai bot decision against us.

    Triggers:
      * HTTP 401/403/406/429 *combined with* fresh Akamai Set-Cookies, or
        body markers like "Pardon Our Interruption".
      * A freshly issued `_abck` whose status is no longer ``-1``
        (Akamai downgraded us from validated → fresh/blocked).
    """
    abck = new_cookies.get("_abck")
    if abck:
        st = AbckStatus.parse(abck)
        if st.status in (0, 1) and not st.is_valid:
            return True

    if status_code in (401, 403, 406, 429):
        if any(c in new_cookies for c in ("_abck", "bm_sz", "ak_bmsc")):
            return True
        for marker in _BLOCK_BODY_MARKERS:
            if marker in response_text[:2000]:
                return True

    return False
