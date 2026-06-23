import httpx
import hashlib
import random
from typing import Dict, List, Optional

async def acquire_proxies(
    proxy_rotator_url: str,
    instance_id: str,
    count: int,
    fallback_proxies: List[str]
) -> List[str]:
    url = f"{proxy_rotator_url}/api/proxies/acquire"
    payload = {
        "worker_id": instance_id,
        "count": count
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                new_proxies = data.get("proxies", [])
                if new_proxies:
                    return new_proxies
            raise Exception(f"HTTP {resp.status_code}")
    except Exception:
        return fallback_proxies

def generate_deterministic_profile(proxy: str) -> Dict:
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

def get_browser_profile(proxy: str, browser_profiles: List[Dict], proxies: List[str]) -> Dict:
    if browser_profiles and len(browser_profiles) >= len(proxies):
        idx = int(hashlib.md5(proxy.encode()).hexdigest(), 16) % len(browser_profiles)
        return browser_profiles[idx]
    return generate_deterministic_profile(proxy)

def get_buyer_profile(proxy: str, profiles: List[Dict], proxies: List[str]) -> Dict:
    if profiles and len(profiles) >= len(proxies):
        idx = int(hashlib.md5(proxy.encode()).hexdigest(), 16) % len(profiles)
        return profiles[idx]
    elif profiles:
        return random.choice(profiles)
    return {}
