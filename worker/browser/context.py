import asyncio
import stealth
from typing import Dict, Optional, Tuple
from playwright.async_api import Browser, BrowserContext, Page, Playwright

def parse_playwright_proxy(proxy_str: str) -> Optional[dict]:
    if not proxy_str or proxy_str == "direct":
        return None
    from urllib.parse import urlparse
    try:
        if not any(proxy_str.startswith(scheme) for scheme in ("http://", "https://", "socks5://", "socks4://")):
            proxy_str = "http://" + proxy_str
        parsed = urlparse(proxy_str)
        server = f"{parsed.scheme or 'http'}://{parsed.hostname}"
        if parsed.port:
            server += f":{parsed.port}"
        proxy_config = {
            "server": server,
            "bypass": "localhost,127.0.0.1,defense-gateway,redis,proxy-rotator,manager,defense-redis"
        }
        if parsed.username:
            proxy_config["username"] = parsed.username
        if parsed.password:
            proxy_config["password"] = parsed.password
        return proxy_config
    except Exception:
        return None

async def create_stealth_browser(
    p: Playwright,
    headless: bool,
    proxy_str: Optional[str],
    fp: dict,
    viewport: dict,
    stealth_js: str
) -> Tuple[Browser, BrowserContext, Page]:
    proxy_cfg = parse_playwright_proxy(proxy_str) if proxy_str else None
    
    browser = await p.chromium.launch(
        headless=headless,
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
        
    return browser, context, page
