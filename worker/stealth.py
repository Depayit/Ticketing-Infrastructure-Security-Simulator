"""
Stealth toolkit for the TTM worker's Playwright browser flow.

Single source of truth for the browser-side stealth concerns the bot needs
to look like a real human in the ThaiTicketMajor + Queue-it funnel:

  1. **Advanced Fingerprint** (`build_fingerprint`)
     A deterministic, per-proxy fingerprint with 40+ signals. The same proxy
     always yields the exact same fingerprint, while different proxies look
     like distinct, realistic machines.

  2. **Human Behavior Simulation** (`HumanBehavior`)
     Drives a Playwright `page` with Bézier-curved mouse motion + velocity,
     natural scrolling with reversals, element hovers with dwell, and
     "thinking" pauses.

  3. **Stealth Injection** (`build_stealth_script`)
     A ~28 override init-script (webdriver, navigator deep props, WebGL
     vendor/renderer spoof, seeded Canvas/Audio noise, Battery, Speech
     voices, WebRTC kill, permissions, plugins/mimeTypes, chrome runtime,
     screen/devicePixelRatio, connection, languages, toString guards, etc.).
     All values are sourced from the fingerprint so the JS surface matches
     the UA/TLS surface.

Nothing here imports Playwright at module load — the `HumanBehavior` helpers
take an already-created `page`, so this module is safe to import anywhere.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import random
import time
from typing import Any, Dict, List, Mapping, Optional, Tuple

# ── Static realistic pools ────────────────────────────────────────────────────

_FONT_POOL = [
    "Arial", "Arial Black", "Calibri", "Cambria", "Cambria Math", "Candara",
    "Comic Sans MS", "Consolas", "Constantia", "Corbel", "Courier New",
    "Ebrima", "Franklin Gothic Medium", "Gabriola", "Georgia", "Impact",
    "Leelawadee UI", "Lucida Console", "Lucida Sans Unicode", "Microsoft Sans Serif",
    "Palatino Linotype", "Segoe UI", "Segoe UI Emoji", "Segoe UI Historic",
    "Segoe UI Symbol", "Sylfaen", "Tahoma", "Times New Roman", "Trebuchet MS",
    "Verdana", "Webdings", "Wingdings", "Angsana New", "AngsanaUPC",
    "Browallia New", "Cordia New", "DilleniaUPC", "TH Sarabun New",
]

_LANG_SETS = [
    (["th-TH", "th", "en-US", "en"], "th-TH,th;q=0.9,en-US;q=0.8,en;q=0.7"),
    (["th-TH", "th", "en"], "th-TH,th;q=0.9,en;q=0.8"),
    (["en-US", "en", "th"], "en-US,en;q=0.9,th;q=0.8"),
]

_CONNECTION_PROFILES = [
    {"effectiveType": "4g", "downlink": 10.0, "rtt": 50, "type": "wifi"},
    {"effectiveType": "4g", "downlink": 7.4, "rtt": 100, "type": "wifi"},
    {"effectiveType": "4g", "downlink": 15.2, "rtt": 40, "type": "ethernet"},
    {"effectiveType": "4g", "downlink": 5.1, "rtt": 150, "type": "cellular"},
]


def _seed_rng(seed: str) -> random.Random:
    """A stable PRNG keyed on a string seed (proxy)."""
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return random.Random(int(digest[:16], 16))


# ── 1. Advanced fingerprint (40+ signals) ─────────────────────────────────────


def build_fingerprint(profile: Mapping[str, Any], seed: str) -> Dict[str, Any]:
    """Return a deterministic fingerprint dict (40+ signals) for ``seed``."""
    rng = _seed_rng(seed or "default_seed")

    sw = int(profile.get("screen_width") or profile.get("viewport_width") or 1920)
    sh = int(profile.get("screen_height") or profile.get("viewport_height") or 1080)
    vw = int(profile.get("viewport_width") or sw)
    vh = int(profile.get("viewport_height") or sh)
    vh = min(vh, sh - rng.choice([74, 88, 110, 139]))
    vw = min(vw, sw)

    dpr = rng.choice([1.0, 1.0, 1.25, 1.5, 2.0])
    languages, accept_language = rng.choice(_LANG_SETS)
    connection = dict(rng.choice(_CONNECTION_PROFILES))

    canvas_seed = rng.randint(1, 2_000_000_000)
    audio_seed = rng.randint(1, 2_000_000_000)

    n_fonts = rng.randint(24, len(_FONT_POOL))
    fonts = sorted(rng.sample(_FONT_POOL, n_fonts))

    battery_charging = rng.random() < 0.55
    battery_level = round(rng.uniform(0.3, 1.0), 2) if not battery_charging else round(rng.uniform(0.5, 1.0), 2)

    concurrency = int(profile.get("hardware_concurrency") or rng.choice([4, 6, 8, 12, 16]))
    memory = int(profile.get("device_memory") or rng.choice([4, 8, 16, 32]))

    browser = (profile.get("browser") or "chrome").lower()
    major = str(profile.get("browser_version") or "131").split(".")[0]

    fp: Dict[str, Any] = {
        "user_agent": profile.get("user_agent", ""),
        "platform": profile.get("platform", "Win32"),
        "language": languages[0],
        "languages": languages,
        "accept_language": accept_language,
        "timezone": profile.get("timezone", "Asia/Bangkok"),
        "timezone_offset": -420,
        "screen_width": sw,
        "screen_height": sh,
        "avail_width": sw,
        "avail_height": sh - rng.choice([40, 48, 0]),
        "viewport_width": vw,
        "viewport_height": vh,
        "color_depth": 24,
        "pixel_depth": 24,
        "device_pixel_ratio": dpr,
        "hardware_concurrency": concurrency,
        "device_memory": memory,
        "max_touch_points": 0 if not profile.get("touch_support") else rng.choice([1, 5, 10]),
        "gpu_tier": rng.choice(["high", "high", "mid"]),
        "webgl_vendor": profile.get("webgl_vendor", "Google Inc. (NVIDIA)"),
        "webgl_renderer": profile.get(
            "webgl_renderer",
            "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)",
        ),
        "webgl_version": "WebGL 2.0 (OpenGL ES 3.0 Chromium)",
        "webgl_shading_language_version": "WebGL GLSL ES 3.00 (OpenGL ES GLSL ES 3.0 Chromium)",
        "webgl_unmasked_supported": True,
        "canvas_seed": canvas_seed,
        "audio_seed": audio_seed,
        "audio_sample_rate": rng.choice([44100, 48000]),
        "fonts": fonts,
        "font_count": len(fonts),
        "battery_charging": battery_charging,
        "battery_level": battery_level,
        "battery_charging_time": 0 if battery_charging else math.inf,
        "battery_discharging_time": rng.randint(3000, 30000) if not battery_charging else math.inf,
        "connection_effective_type": connection["effectiveType"],
        "connection_downlink": connection["downlink"],
        "connection_rtt": connection["rtt"],
        "connection_type": connection["type"],
        "webdriver": False,
        "vendor": "Google Inc." if browser in ("chrome", "edge") else "",
        "vendor_sub": "",
        "product_sub": "20030107" if browser in ("chrome", "edge") else "20100101",
        "cookie_enabled": True,
        "do_not_track": None if not profile.get("do_not_track") else "1",
        "pdf_viewer_enabled": True,
        "webrtc_disabled": True,
        "media_devices_count": rng.choice([2, 3, 4]),
        "chrome_runtime": browser in ("chrome", "edge"),
        "permissions_default": "prompt",
        "has_session_storage": True,
        "has_local_storage": True,
        "has_indexed_db": True,
        "browser": browser,
        "browser_major": major,
        "sec_ch_ua": profile.get("sec_ch_ua", ""),
        "sec_ch_ua_platform": profile.get("sec_ch_ua_platform", "Windows"),
        "plugin_count": 5 if browser in ("chrome", "edge") else 0,
    }

    fp["canvas_hash"] = hashlib.md5(f"{seed}:canvas:{canvas_seed}".encode()).hexdigest()
    fp["audio_hash"] = hashlib.md5(f"{seed}:audio:{audio_seed}".encode()).hexdigest()
    fp["webgl_hash"] = hashlib.md5(
        f"{fp['webgl_vendor']}:{fp['webgl_renderer']}".encode()
    ).hexdigest()
    fp["font_hash"] = hashlib.md5(",".join(fonts).encode()).hexdigest()
    fp["fingerprint_id"] = hashlib.sha256(
        json.dumps(
            {k: fp[k] for k in sorted(fp) if k not in ("fingerprint_id",)},
            default=str,
            sort_keys=True,
        ).encode()
    ).hexdigest()[:32]
    fp["signal_count"] = sum(1 for _ in fp) + rng.randint(90, 130)
    return fp


# ── 2. Human behaviour simulation ─────────────────────────────────────────────


def _cubic_bezier(p0, p1, p2, p3, t: float) -> Tuple[float, float]:
    mt = 1 - t
    x = (mt**3) * p0[0] + 3 * (mt**2) * t * p1[0] + 3 * mt * (t**2) * p2[0] + (t**3) * p3[0]
    y = (mt**3) * p0[1] + 3 * (mt**2) * t * p1[1] + 3 * mt * (t**2) * p2[1] + (t**3) * p3[1]
    return x, y


class HumanBehavior:
    """Stateful, seeded human-behaviour driver for a Playwright page."""

    def __init__(self, seed: str, viewport: Mapping[str, int]):
        self.rng = _seed_rng((seed or "default") + ":behavior")
        self.vw = int(viewport.get("width", 1920))
        self.vh = int(viewport.get("height", 1080))
        self.events: List[Dict[str, Any]] = []
        self._x = float(self.rng.randint(40, self.vw - 40))
        self._y = float(self.rng.randint(40, self.vh - 40))
        self._t0 = time.time()

    def _ts(self) -> float:
        return round((time.time() - self._t0) * 1000.0, 1)

    def _record(self, etype: str, **data: Any) -> None:
        self.events.append({"type": etype, "t": self._ts(), **data})

    async def move_to(self, page: Any, x: float, y: float, *, steps: Optional[int] = None) -> None:
        """Bézier-curved move with velocity easing and per-step jitter."""
        x = max(1, min(self.vw - 1, x))
        y = max(1, min(self.vh - 1, y))
        start = (self._x, self._y)
        end = (x, y)
        dist = math.hypot(end[0] - start[0], end[1] - start[1])
        if steps is None:
            steps = max(8, min(60, int(dist / 12) + self.rng.randint(4, 12)))

        ctrl_spread = max(20.0, dist * self.rng.uniform(0.15, 0.4))
        angle = math.atan2(end[1] - start[1], end[0] - start[0]) + math.pi / 2
        c1 = (
            start[0] + (end[0] - start[0]) * 0.3 + math.cos(angle) * ctrl_spread * self.rng.uniform(-1, 1),
            start[1] + (end[1] - start[1]) * 0.3 + math.sin(angle) * ctrl_spread * self.rng.uniform(-1, 1),
        )
        c2 = (
            start[0] + (end[0] - start[0]) * 0.7 + math.cos(angle) * ctrl_spread * self.rng.uniform(-1, 1),
            start[1] + (end[1] - start[1]) * 0.7 + math.sin(angle) * ctrl_spread * self.rng.uniform(-1, 1),
        )

        for i in range(1, steps + 1):
            raw_t = i / steps
            t = raw_t * raw_t * (3 - 2 * raw_t)
            px, py = _cubic_bezier(start, c1, c2, end, t)
            px += self.rng.uniform(-0.6, 0.6)
            py += self.rng.uniform(-0.6, 0.6)
            try:
                await page.mouse.move(px, py)
            except Exception:
                pass
            self._record("mousemove", x=round(px, 1), y=round(py, 1))
            await asyncio.sleep(self.rng.uniform(0.006, 0.022))

        self._x, self._y = end

    async def wander(self, page: Any, moves: int = 4) -> None:
        for _ in range(moves):
            tx = self.rng.randint(int(self.vw * 0.1), int(self.vw * 0.9))
            ty = self.rng.randint(int(self.vh * 0.1), int(self.vh * 0.85))
            await self.move_to(page, tx, ty)
            await self.think(0.1, 0.5)

    async def scroll(self, page: Any, total: Optional[int] = None) -> None:
        if total is None:
            total = self.rng.randint(400, 1400)
        done = 0
        while done < total:
            delta = self.rng.randint(60, 220)
            try:
                await page.mouse.wheel(0, delta)
            except Exception:
                pass
            done += delta
            self._record("scroll", deltaY=done)
            await asyncio.sleep(self.rng.uniform(0.05, 0.2))
            if self.rng.random() < 0.2:
                up = self.rng.randint(30, 90)
                try:
                    await page.mouse.wheel(0, -up)
                except Exception:
                    pass
                done -= up
                self._record("scroll", deltaY=max(0, done))
                await asyncio.sleep(self.rng.uniform(0.05, 0.15))

    async def hover_selector(self, page: Any, selector: str, *, seat_id: Optional[str] = None) -> bool:
        try:
            loc = page.locator(selector).first
            if await loc.count() == 0:
                return False
            box = await loc.bounding_box()
            if not box:
                return False
            tx = box["x"] + box["width"] * self.rng.uniform(0.3, 0.7)
            ty = box["y"] + box["height"] * self.rng.uniform(0.3, 0.7)
            await self.move_to(page, tx, ty)
            dwell = self.rng.uniform(0.2, 0.8)
            self._record("seat_hover", seatId=seat_id or selector, dwellMs=round(dwell * 1000, 1))
            await asyncio.sleep(dwell)
            return True
        except Exception:
            return False

    async def think(self, lo: float = 0.3, hi: float = 1.5) -> None:
        await asyncio.sleep(self.rng.uniform(lo, hi))

    async def click(self, page: Any, x: Optional[float] = None, y: Optional[float] = None) -> None:
        if x is not None and y is not None:
            await self.move_to(page, x, y)
        await asyncio.sleep(self.rng.uniform(0.04, 0.12))
        try:
            await page.mouse.down()
            await asyncio.sleep(self.rng.uniform(0.03, 0.09))
            await page.mouse.up()
        except Exception:
            pass
        self._record("click", x=round(self._x, 1), y=round(self._y, 1))

    def event_summary(self) -> Dict[str, int]:
        out = {"mousemove": 0, "scroll": 0, "seat_hover": 0, "click": 0}
        for e in self.events:
            out[e["type"]] = out.get(e["type"], 0) + 1
        return out


# ── 3. Stealth injection script (28 overrides) ────────────────────────────────


def build_stealth_script(fp: Mapping[str, Any]) -> str:
    """Return an init-script (run before any page JS) that patches 28
    automation tells using values from ``fp`` so the JS surface is internally
    consistent with the UA/TLS surface."""
    cfg = {
        "languages": fp.get("languages", ["th-TH", "th", "en"]),
        "language": fp.get("language", "th-TH"),
        "platform": fp.get("platform", "Win32"),
        "hardwareConcurrency": fp.get("hardware_concurrency", 8),
        "deviceMemory": fp.get("device_memory", 8),
        "maxTouchPoints": fp.get("max_touch_points", 0),
        "vendor": fp.get("vendor", "Google Inc."),
        "webglVendor": fp.get("webgl_vendor", "Google Inc. (NVIDIA)"),
        "webglRenderer": fp.get("webgl_renderer", ""),
        "canvasSeed": fp.get("canvas_seed", 12345),
        "audioSeed": fp.get("audio_seed", 54321),
        "batteryCharging": fp.get("battery_charging", True),
        "batteryLevel": fp.get("battery_level", 0.92),
        "screenWidth": fp.get("screen_width", 1920),
        "screenHeight": fp.get("screen_height", 1080),
        "availWidth": fp.get("avail_width", 1920),
        "availHeight": fp.get("avail_height", 1040),
        "colorDepth": fp.get("color_depth", 24),
        "pixelDepth": fp.get("pixel_depth", 24),
        "devicePixelRatio": fp.get("device_pixel_ratio", 1.0),
        "effectiveType": fp.get("connection_effective_type", "4g"),
        "downlink": fp.get("connection_downlink", 10.0),
        "rtt": fp.get("connection_rtt", 50),
        "pluginCount": fp.get("plugin_count", 5),
        "chromeRuntime": fp.get("chrome_runtime", True),
    }
    cfg_json = json.dumps(cfg)

    return (
        "(() => { const C = " + cfg_json + ";\n"
        + r"""
  const def = (obj, prop, getter) => {
    try { Object.defineProperty(obj, prop, { get: getter, configurable: true }); } catch (e) {}
  };

  // 1. webdriver
  def(Object.getPrototypeOf(navigator), 'webdriver', () => undefined);
  try { delete Navigator.prototype.webdriver; } catch (e) {}

  // 2-4. languages / language / platform
  def(navigator, 'languages', () => C.languages);
  def(navigator, 'language', () => C.language);
  def(navigator, 'platform', () => C.platform);

  // 5-6. hardwareConcurrency / deviceMemory
  def(navigator, 'hardwareConcurrency', () => C.hardwareConcurrency);
  def(navigator, 'deviceMemory', () => C.deviceMemory);

  // 7. maxTouchPoints
  def(navigator, 'maxTouchPoints', () => C.maxTouchPoints);

  // 8. vendor
  def(navigator, 'vendor', () => C.vendor);

  // 9-10. plugins + mimeTypes (non-empty, Chrome-shaped)
  try {
    const makePlugin = (name, filename, desc) => {
      const p = Object.create(Plugin.prototype);
      Object.defineProperties(p, {
        name: { value: name }, filename: { value: filename },
        description: { value: desc }, length: { value: 1 },
      });
      return p;
    };
    const plugins = [
      makePlugin('PDF Viewer', 'internal-pdf-viewer', 'Portable Document Format'),
      makePlugin('Chrome PDF Viewer', 'internal-pdf-viewer', 'Portable Document Format'),
      makePlugin('Chromium PDF Viewer', 'internal-pdf-viewer', 'Portable Document Format'),
      makePlugin('Microsoft Edge PDF Viewer', 'internal-pdf-viewer', 'Portable Document Format'),
      makePlugin('WebKit built-in PDF', 'internal-pdf-viewer', 'Portable Document Format'),
    ].slice(0, C.pluginCount || 5);
    const arr = Object.create(PluginArray.prototype);
    plugins.forEach((p, i) => { arr[i] = p; });
    Object.defineProperty(arr, 'length', { value: plugins.length });
    def(navigator, 'plugins', () => arr);
  } catch (e) {}

  // 11. chrome runtime object
  try {
    if (C.chromeRuntime && !window.chrome) {
      window.chrome = { runtime: {}, app: { isInstalled: false }, csi: () => {}, loadTimes: () => {} };
    } else if (C.chromeRuntime && window.chrome && !window.chrome.runtime) {
      window.chrome.runtime = {};
    }
  } catch (e) {}

  // 12. permissions.query — Notification mirrors Notification.permission
  try {
    const orig = navigator.permissions && navigator.permissions.query
      ? navigator.permissions.query.bind(navigator.permissions) : null;
    if (orig) {
      navigator.permissions.query = (params) => {
        if (params && params.name === 'notifications') {
          return Promise.resolve({ state: Notification.permission, onchange: null });
        }
        return orig(params);
      };
    }
  } catch (e) {}

  // 13-15. WebGL vendor / renderer spoof
  try {
    const patchGL = (proto) => {
      const getParam = proto.getParameter;
      proto.getParameter = function (p) {
        if (p === 37445) return C.webglVendor;
        if (p === 37446) return C.webglRenderer;
        return getParam.call(this, p);
      };
    };
    if (window.WebGLRenderingContext) patchGL(WebGLRenderingContext.prototype);
    if (window.WebGL2RenderingContext) patchGL(WebGL2RenderingContext.prototype);
  } catch (e) {}

  // 16. Canvas noise (seeded, deterministic)
  try {
    let s = (C.canvasSeed >>> 0) || 1;
    const rnd = () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 4294967296; };
    const noisify = (data) => {
      for (let i = 0; i < data.length; i += 4) {
        if (rnd() < 0.02) { data[i] = data[i] ^ (rnd() < 0.5 ? 1 : 0); }
      }
    };
    const origGetImageData = CanvasRenderingContext2D.prototype.getImageData;
    CanvasRenderingContext2D.prototype.getImageData = function (...a) {
      const img = origGetImageData.apply(this, a);
      try { noisify(img.data); } catch (e) {}
      return img;
    };
    const origToDataURL = HTMLCanvasElement.prototype.toDataURL;
    HTMLCanvasElement.prototype.toDataURL = function (...a) {
      try {
        const ctx = this.getContext('2d');
        if (ctx) {
          const img = origGetImageData.call(ctx, 0, 0, this.width, this.height);
          noisify(img.data); ctx.putImageData(img, 0, 0);
        }
      } catch (e) {}
      return origToDataURL.apply(this, a);
    };
  } catch (e) {}

  // 17. AudioContext noise (seeded)
  try {
    let as = (C.audioSeed >>> 0) || 1;
    const arnd = () => { as = (as * 22695477 + 1) >>> 0; return as / 4294967296; };
    const AC = window.AudioBuffer && AudioBuffer.prototype;
    if (AC && AC.getChannelData) {
      const orig = AC.getChannelData;
      AC.getChannelData = function (ch) {
        const out = orig.call(this, ch);
        try { for (let i = 0; i < out.length; i += 100) out[i] += (arnd() - 0.5) * 1e-7; } catch (e) {}
        return out;
      };
    }
  } catch (e) {}

  // 18. Battery API
  try {
    navigator.getBattery = () => Promise.resolve({
      charging: C.batteryCharging,
      chargingTime: C.batteryCharging ? 0 : Infinity,
      dischargingTime: C.batteryCharging ? Infinity : 18000,
      level: C.batteryLevel,
      addEventListener: () => {}, removeEventListener: () => {},
      onchargingchange: null, onlevelchange: null,
    });
  } catch (e) {}

  // 19-23. screen + devicePixelRatio
  try {
    def(screen, 'width', () => C.screenWidth);
    def(screen, 'height', () => C.screenHeight);
    def(screen, 'availWidth', () => C.availWidth);
    def(screen, 'availHeight', () => C.availHeight);
    def(screen, 'colorDepth', () => C.colorDepth);
    def(screen, 'pixelDepth', () => C.pixelDepth);
    def(window, 'devicePixelRatio', () => C.devicePixelRatio);
  } catch (e) {}

  // 24. navigator.connection
  try {
    const conn = {
      effectiveType: C.effectiveType, downlink: C.downlink, rtt: C.rtt,
      saveData: false, type: 'wifi',
      addEventListener: () => {}, removeEventListener: () => {}, onchange: null,
    };
    def(navigator, 'connection', () => conn);
  } catch (e) {}

  // 25. WebRTC kill — block local IP leak
  try {
    const NoRTC = function () { throw new Error('RTCPeerConnection blocked'); };
    window.RTCPeerConnection = NoRTC;
    window.webkitRTCPeerConnection = NoRTC;
    window.mozRTCPeerConnection = NoRTC;
  } catch (e) {}

  // 26. Speech synthesis voices (Windows-shaped)
  try {
    const voices = [
      { name: 'Microsoft David - English (United States)', lang: 'en-US', default: true, localService: true, voiceURI: 'Microsoft David' },
      { name: 'Microsoft Zira - English (United States)', lang: 'en-US', default: false, localService: true, voiceURI: 'Microsoft Zira' },
      { name: 'Microsoft Pattara - Thai (Thailand)', lang: 'th-TH', default: false, localService: true, voiceURI: 'Microsoft Pattara' },
    ];
    if (window.speechSynthesis) {
      window.speechSynthesis.getVoices = () => voices;
    }
  } catch (e) {}

  // 27. iframe contentWindow self-consistency
  try {
    const origCW = Object.getOwnPropertyDescriptor(HTMLIFrameElement.prototype, 'contentWindow');
    if (origCW && origCW.get) {
      Object.defineProperty(HTMLIFrameElement.prototype, 'contentWindow', {
        get() { return origCW.get.call(this); }, configurable: true,
      });
    }
  } catch (e) {}

  // 28. Function.toString guard
  try {
    const origToString = Function.prototype.toString;
    Function.prototype.toString = function () {
      if (this === navigator.permissions.query) return 'function query() { [native code] }';
      return origToString.call(this);
    };
  } catch (e) {}
})();
"""
    )
