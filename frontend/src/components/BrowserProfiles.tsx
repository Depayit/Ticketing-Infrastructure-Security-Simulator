import { useState } from 'react';

// ── Types ─────────────────────────────────────────────────────────────────────

export interface BrowserProfile {
  id: string;
  name: string;
  browser: 'chrome' | 'firefox' | 'edge';
  browser_version: string;
  os: 'windows' | 'macos' | 'linux';
  os_version: string;
  user_agent: string;
  platform: string;
  language: string;
  sec_ch_ua: string;
  sec_ch_ua_platform: string;
  viewport_width: number;
  viewport_height: number;
  screen_width: number;
  screen_height: number;
  color_depth: number;
  timezone: string;
  hardware_concurrency: number;
  device_memory: number;
  webgl_vendor: string;
  webgl_renderer: string;
  do_not_track: boolean;
  touch_support: boolean;
}

// ── Constants & helpers ───────────────────────────────────────────────────────

const BROWSER_COLOR: Record<string, string> = {
  chrome: '#4285F4',
  firefox: '#FF7139',
  edge: '#0078D7',
};
const BROWSER_LABEL: Record<string, string> = {
  chrome: 'Chrome',
  firefox: 'Firefox',
  edge: 'Edge',
};
const OS_EMOJI: Record<string, string> = {
  windows: '🪟',
  macos: '🍎',
  linux: '🐧',
};
const OS_LABEL: Record<string, string> = {
  windows: 'Windows',
  macos: 'macOS',
  linux: 'Linux',
};

const CHROME_VERSIONS = [
  '128.0.6613.120', '129.0.6668.89', '130.0.6723.58',
  '130.0.6723.116', '131.0.6778.85', '131.0.6778.108',
];
const EDGE_VERSIONS = [
  '128.0.2739.67', '129.0.2792.89', '130.0.2849.52', '131.0.2903.70',
];
const FIREFOX_VERSIONS = ['127.0', '128.0', '129.0', '130.0', '131.0'];

const GPU_POOL: { vendor: string; renderer: string }[] = [
  { vendor: 'Google Inc. (NVIDIA)', renderer: 'ANGLE (NVIDIA, NVIDIA GeForce RTX 4090 Direct3D11 vs_5_0 ps_5_0, D3D11)' },
  { vendor: 'Google Inc. (NVIDIA)', renderer: 'ANGLE (NVIDIA, NVIDIA GeForce RTX 4080 Direct3D11 vs_5_0 ps_5_0, D3D11)' },
  { vendor: 'Google Inc. (NVIDIA)', renderer: 'ANGLE (NVIDIA, NVIDIA GeForce RTX 4070 Ti Direct3D11 vs_5_0 ps_5_0, D3D11)' },
  { vendor: 'Google Inc. (NVIDIA)', renderer: 'ANGLE (NVIDIA, NVIDIA GeForce RTX 4070 Direct3D11 vs_5_0 ps_5_0, D3D11)' },
  { vendor: 'Google Inc. (NVIDIA)', renderer: 'ANGLE (NVIDIA, NVIDIA GeForce RTX 3090 Direct3D11 vs_5_0 ps_5_0, D3D11)' },
  { vendor: 'Google Inc. (NVIDIA)', renderer: 'ANGLE (NVIDIA, NVIDIA GeForce RTX 3080 Direct3D11 vs_5_0 ps_5_0, D3D11)' },
  { vendor: 'Google Inc. (NVIDIA)', renderer: 'ANGLE (NVIDIA, NVIDIA GeForce RTX 3070 Direct3D11 vs_5_0 ps_5_0, D3D11)' },
  { vendor: 'Google Inc. (NVIDIA)', renderer: 'ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Ti Direct3D11 vs_5_0 ps_5_0, D3D11)' },
  { vendor: 'Google Inc. (NVIDIA)', renderer: 'ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)' },
  { vendor: 'Google Inc. (NVIDIA)', renderer: 'ANGLE (NVIDIA, NVIDIA GeForce GTX 1080 Ti Direct3D11 vs_5_0 ps_5_0, D3D11)' },
  { vendor: 'Google Inc. (AMD)', renderer: 'ANGLE (AMD, AMD Radeon RX 7900 XTX Direct3D11 vs_5_0 ps_5_0, D3D11)' },
  { vendor: 'Google Inc. (AMD)', renderer: 'ANGLE (AMD, AMD Radeon RX 7800 XT Direct3D11 vs_5_0 ps_5_0, D3D11)' },
  { vendor: 'Google Inc. (AMD)', renderer: 'ANGLE (AMD, AMD Radeon RX 6800 XT Direct3D11 vs_5_0 ps_5_0, D3D11)' },
  { vendor: 'Google Inc. (AMD)', renderer: 'ANGLE (AMD, AMD Radeon RX 6700 XT Direct3D11 vs_5_0 ps_5_0, D3D11)' },
  { vendor: 'Google Inc. (Intel)', renderer: 'ANGLE (Intel, Intel(R) Arc(TM) A770 Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)' },
  { vendor: 'Google Inc. (Intel)', renderer: 'ANGLE (Intel, Intel(R) Iris(R) Xe Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)' },
  { vendor: 'Google Inc. (Intel)', renderer: 'ANGLE (Intel, Intel(R) UHD Graphics 770 Direct3D11 vs_5_0 ps_5_0, D3D11)' },
  { vendor: 'Google Inc. (Intel)', renderer: 'ANGLE (Intel, Intel(R) UHD Graphics 630 Direct3D11 vs_5_0 ps_5_0, D3D11)' },
];

const VIEWPORT_POOL = [
  { w: 1920, h: 1080 },
  { w: 2560, h: 1440 },
  { w: 3840, h: 2160 },
  { w: 1366, h: 768 },
  { w: 1536, h: 864 },
  { w: 1440, h: 900 },
  { w: 1280, h: 800 },
  { w: 1600, h: 900 },
];

const CONCURRENCY_POOL = [4, 6, 8, 10, 12, 16, 20, 24];
const MEMORY_POOL = [4, 8, 8, 16, 16, 32];

function pick<T>(arr: T[]): T {
  return arr[Math.floor(Math.random() * arr.length)];
}

function genId(): string {
  return Math.random().toString(36).slice(2, 10);
}

function buildSecChUa(browser: string, version: string): string {
  const major = version.split('.')[0];
  if (browser === 'chrome')
    return `"Chromium";v="${major}", "Google Chrome";v="${major}", "Not-A.Brand";v="99"`;
  if (browser === 'edge')
    return `"Chromium";v="${major}", "Microsoft Edge";v="${major}", "Not-A.Brand";v="24"`;
  return '';
}

function buildUA(browser: string, version: string): string {
  if (browser === 'chrome')
    return `Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/${version} Safari/537.36`;
  if (browser === 'edge') {
    const cver = version.split('.')[0] + '.0.0.0';
    return `Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/${cver} Safari/537.36 Edg/${version}`;
  }
  if (browser === 'firefox')
    return `Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:${version}) Gecko/20100101 Firefox/${version}`;
  return '';
}

function gpuShortLabel(renderer: string): string {
  const m = renderer.match(/NVIDIA GeForce (.+?) Direct/) ||
            renderer.match(/AMD (.+?) Direct/) ||
            renderer.match(/Intel\(R\) (.+?) Direct/) ||
            renderer.match(/Intel\(R\) Arc.+? (.+?) Graphics/);
  return m ? m[1].trim() : renderer.slice(0, 22);
}

// ── Random generator ─────────────────────────────────────────────────────────

export function generateRandomProfile(): BrowserProfile {
  const browser = pick(['chrome', 'chrome', 'chrome', 'edge', 'firefox'] as const);
  const version =
    browser === 'edge' ? pick(EDGE_VERSIONS)
    : browser === 'firefox' ? pick(FIREFOX_VERSIONS)
    : pick(CHROME_VERSIONS);
  const gpu = pick(GPU_POOL);
  const vp = pick(VIEWPORT_POOL);
  const concurrency = pick(CONCURRENCY_POOL);
  const memory = pick(MEMORY_POOL);
  const major = version.split('.')[0];
  const gpuLabel = gpuShortLabel(gpu.renderer);
  const name = `${BROWSER_LABEL[browser]} ${major} / Win / ${gpuLabel}`;

  return {
    id: genId(),
    name,
    browser,
    browser_version: version,
    os: 'windows',
    os_version: '10.0',
    user_agent: buildUA(browser, version),
    platform: 'Win32',
    language: 'th-TH,th;q=0.9,en-US;q=0.8,en;q=0.7',
    sec_ch_ua: buildSecChUa(browser, version),
    sec_ch_ua_platform: 'Windows',
    viewport_width: vp.w,
    viewport_height: vp.h,
    screen_width: vp.w,
    screen_height: vp.h,
    color_depth: 24,
    timezone: 'Asia/Bangkok',
    hardware_concurrency: concurrency,
    device_memory: memory,
    webgl_vendor: gpu.vendor,
    webgl_renderer: gpu.renderer,
    do_not_track: false,
    touch_support: false,
  };
}

// ── Default profiles ─────────────────────────────────────────────────────────

export const DEFAULT_BROWSER_PROFILES: BrowserProfile[] = [
  {
    id: 'bp-1', name: 'Chrome 130 / Win11 / RTX 4070', browser: 'chrome',
    browser_version: '130.0.6723.58', os: 'windows', os_version: '10.0',
    user_agent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.6723.58 Safari/537.36',
    platform: 'Win32', language: 'th-TH,th;q=0.9,en-US;q=0.8,en;q=0.7',
    sec_ch_ua: '"Chromium";v="130", "Google Chrome";v="130", "Not-A.Brand";v="99"',
    sec_ch_ua_platform: 'Windows', viewport_width: 1920, viewport_height: 1080,
    screen_width: 1920, screen_height: 1080, color_depth: 24, timezone: 'Asia/Bangkok',
    hardware_concurrency: 12, device_memory: 16,
    webgl_vendor: 'Google Inc. (NVIDIA)',
    webgl_renderer: 'ANGLE (NVIDIA, NVIDIA GeForce RTX 4070 Direct3D11 vs_5_0 ps_5_0, D3D11)',
    do_not_track: false, touch_support: false,
  },
  {
    id: 'bp-2', name: 'Chrome 129 / Win10 / RTX 3080', browser: 'chrome',
    browser_version: '129.0.6668.89', os: 'windows', os_version: '10.0',
    user_agent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.6668.89 Safari/537.36',
    platform: 'Win32', language: 'th-TH,th;q=0.9,en;q=0.8',
    sec_ch_ua: '"Chromium";v="129", "Google Chrome";v="129", "Not-A.Brand";v="24"',
    sec_ch_ua_platform: 'Windows', viewport_width: 2560, viewport_height: 1440,
    screen_width: 2560, screen_height: 1440, color_depth: 24, timezone: 'Asia/Bangkok',
    hardware_concurrency: 8, device_memory: 8,
    webgl_vendor: 'Google Inc. (NVIDIA)',
    webgl_renderer: 'ANGLE (NVIDIA, NVIDIA GeForce RTX 3080 Direct3D11 vs_5_0 ps_5_0, D3D11)',
    do_not_track: false, touch_support: false,
  },
  {
    id: 'bp-3', name: 'Edge 130 / Win11 / Intel Iris Xe', browser: 'edge',
    browser_version: '130.0.2849.52', os: 'windows', os_version: '10.0',
    user_agent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Edg/130.0.2849.52',
    platform: 'Win32', language: 'th-TH,th;q=0.9,en;q=0.8',
    sec_ch_ua: '"Chromium";v="130", "Microsoft Edge";v="130", "Not-A.Brand";v="24"',
    sec_ch_ua_platform: 'Windows', viewport_width: 1920, viewport_height: 1080,
    screen_width: 1920, screen_height: 1080, color_depth: 24, timezone: 'Asia/Bangkok',
    hardware_concurrency: 16, device_memory: 16,
    webgl_vendor: 'Google Inc. (Intel)',
    webgl_renderer: 'ANGLE (Intel, Intel(R) Iris(R) Xe Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)',
    do_not_track: false, touch_support: false,
  },
  {
    id: 'bp-4', name: 'Chrome 128 / Win10 / RX 6800 XT', browser: 'chrome',
    browser_version: '128.0.6613.120', os: 'windows', os_version: '10.0',
    user_agent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.6613.120 Safari/537.36',
    platform: 'Win32', language: 'th-TH,th;q=0.9,en-US;q=0.8,en;q=0.7',
    sec_ch_ua: '"Chromium";v="128", "Google Chrome";v="128", "Not-A.Brand";v="99"',
    sec_ch_ua_platform: 'Windows', viewport_width: 1440, viewport_height: 900,
    screen_width: 1440, screen_height: 900, color_depth: 24, timezone: 'Asia/Bangkok',
    hardware_concurrency: 8, device_memory: 8,
    webgl_vendor: 'Google Inc. (AMD)',
    webgl_renderer: 'ANGLE (AMD, AMD Radeon RX 6800 XT Direct3D11 vs_5_0 ps_5_0, D3D11)',
    do_not_track: false, touch_support: false,
  },
  {
    id: 'bp-5', name: 'Firefox 131 / Win11 / UHD 770', browser: 'firefox',
    browser_version: '131.0', os: 'windows', os_version: '10.0',
    user_agent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:131.0) Gecko/20100101 Firefox/131.0',
    platform: 'Win32', language: 'th-TH,th;q=0.9,en-US;q=0.8,en;q=0.7',
    sec_ch_ua: '', sec_ch_ua_platform: '',
    viewport_width: 1366, viewport_height: 768,
    screen_width: 1366, screen_height: 768, color_depth: 24, timezone: 'Asia/Bangkok',
    hardware_concurrency: 6, device_memory: 4,
    webgl_vendor: 'Google Inc. (Intel)',
    webgl_renderer: 'ANGLE (Intel, Intel(R) UHD Graphics 770 Direct3D11 vs_5_0 ps_5_0, D3D11)',
    do_not_track: true, touch_support: false,
  },
];

// ── Edit Modal ────────────────────────────────────────────────────────────────

function EditModal({
  profile,
  onSave,
  onClose,
}: {
  profile: BrowserProfile;
  onSave: (p: BrowserProfile) => void;
  onClose: () => void;
}) {
  const [draft, setDraft] = useState<BrowserProfile>({ ...profile });
  const [tab, setTab] = useState<'identity' | 'system' | 'graphics'>('identity');

  const field = <K extends keyof BrowserProfile>(
    label: string,
    key: K,
    type: string = 'text',
    hint?: string
  ) => (
    <div>
      <label className="block text-xs text-zinc-400 mb-1 font-medium">{label}</label>
      <input
        type={type}
        value={draft[key] as string | number}
        onChange={(e) =>
          setDraft({
            ...draft,
            [key]: type === 'number' ? Number(e.target.value) : e.target.value,
          })
        }
        className="w-full px-3 py-2 bg-zinc-700 border border-zinc-600 rounded-lg text-white text-sm focus:border-emerald-500 focus:outline-none font-mono"
      />
      {hint && <p className="text-xs text-zinc-500 mt-1">{hint}</p>}
    </div>
  );

  const tabBtn = (name: typeof tab, label: string) => (
    <button
      onClick={() => setTab(name)}
      className={`px-4 py-2 rounded-lg text-sm font-medium transition ${
        tab === name ? 'bg-emerald-600 text-white' : 'bg-zinc-700 text-zinc-300 hover:bg-zinc-600'
      }`}
    >
      {label}
    </button>
  );

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
      <div className="bg-zinc-900 border border-zinc-700 rounded-2xl w-full max-w-2xl max-h-[90vh] overflow-y-auto shadow-2xl mx-auto">
        {/* Header */}
        <div
          className="px-6 py-4 border-b border-zinc-700 flex justify-between items-center"
          style={{ borderTopColor: BROWSER_COLOR[draft.browser], borderTopWidth: 3 }}
        >
          <div>
            <h2 className="font-bold text-white text-lg">✏️ แก้ไข Browser Profile</h2>
            <p className="text-zinc-400 text-sm font-mono truncate max-w-md">{draft.name}</p>
          </div>
          <button onClick={onClose} className="text-zinc-400 hover:text-white text-2xl">✕</button>
        </div>

        {/* Profile name */}
        <div className="px-6 pt-5">
          <div>
            <label className="block text-xs text-zinc-400 mb-1 font-medium">ชื่อ Profile</label>
            <input
              type="text"
              value={draft.name}
              onChange={(e) => setDraft({ ...draft, name: e.target.value })}
              className="w-full px-3 py-2.5 bg-zinc-800 border border-zinc-600 rounded-lg text-white font-semibold focus:border-emerald-500 focus:outline-none"
            />
          </div>
        </div>

        {/* Tabs */}
        <div className="flex gap-2 px-6 pt-4">
          {tabBtn('identity', '🧬 Identity')}
          {tabBtn('system', '💻 System')}
          {tabBtn('graphics', '🎮 Graphics')}
        </div>

        {/* Tab content */}
        <div className="px-6 py-5 space-y-4">
          {tab === 'identity' && (
            <>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div>
                  <label className="block text-xs text-zinc-400 mb-1 font-medium">Browser</label>
                  <select
                    value={draft.browser}
                    onChange={(e) => {
                      const b = e.target.value as BrowserProfile['browser'];
                      setDraft({
                        ...draft,
                        browser: b,
                        user_agent: buildUA(b, draft.browser_version),
                        sec_ch_ua: buildSecChUa(b, draft.browser_version),
                      });
                    }}
                    className="w-full px-3 py-2 bg-zinc-700 border border-zinc-600 rounded-lg text-white text-sm focus:border-emerald-500 focus:outline-none"
                  >
                    <option value="chrome">Chrome</option>
                    <option value="firefox">Firefox</option>
                    <option value="edge">Edge</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs text-zinc-400 mb-1 font-medium">Version</label>
                  <input
                    type="text"
                    value={draft.browser_version}
                    onChange={(e) =>
                      setDraft({
                        ...draft,
                        browser_version: e.target.value,
                        user_agent: buildUA(draft.browser, e.target.value),
                        sec_ch_ua: buildSecChUa(draft.browser, e.target.value),
                      })
                    }
                    className="w-full px-3 py-2 bg-zinc-700 border border-zinc-600 rounded-lg text-white text-sm focus:border-emerald-500 focus:outline-none font-mono"
                  />
                </div>
                <div>
                  <label className="block text-xs text-zinc-400 mb-1 font-medium">OS</label>
                  <select
                    value={draft.os}
                    onChange={(e) => setDraft({ ...draft, os: e.target.value as BrowserProfile['os'] })}
                    className="w-full px-3 py-2 bg-zinc-700 border border-zinc-600 rounded-lg text-white text-sm focus:border-emerald-500 focus:outline-none"
                  >
                    <option value="windows">Windows</option>
                    <option value="macos">macOS</option>
                    <option value="linux">Linux</option>
                  </select>
                </div>
              </div>
              {field('User-Agent', 'user_agent')}
              {field('Platform', 'platform', 'text', 'Win32 / MacIntel / Linux x86_64')}
              {field('Accept-Language', 'language')}
              {field('Sec-CH-UA', 'sec_ch_ua')}
              {field('Sec-CH-UA-Platform', 'sec_ch_ua_platform')}
              <div className="flex gap-4 pt-1">
                <label className="flex items-center gap-2 text-sm text-zinc-300 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={draft.do_not_track}
                    onChange={(e) => setDraft({ ...draft, do_not_track: e.target.checked })}
                    className="accent-emerald-500 w-4 h-4"
                  />
                  Do Not Track
                </label>
                <label className="flex items-center gap-2 text-sm text-zinc-300 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={draft.touch_support}
                    onChange={(e) => setDraft({ ...draft, touch_support: e.target.checked })}
                    className="accent-emerald-500 w-4 h-4"
                  />
                  Touch Support
                </label>
              </div>
            </>
          )}

          {tab === 'system' && (
            <>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {field('Viewport Width', 'viewport_width', 'number')}
                {field('Viewport Height', 'viewport_height', 'number')}
                {field('Screen Width', 'screen_width', 'number')}
                {field('Screen Height', 'screen_height', 'number')}
                {field('Color Depth', 'color_depth', 'number')}
                <div>
                  <label className="block text-xs text-zinc-400 mb-1 font-medium">Timezone</label>
                  <select
                    value={draft.timezone}
                    onChange={(e) => setDraft({ ...draft, timezone: e.target.value })}
                    className="w-full px-3 py-2 bg-zinc-700 border border-zinc-600 rounded-lg text-white text-sm focus:border-emerald-500 focus:outline-none"
                  >
                    {['Asia/Bangkok', 'Asia/Singapore', 'Asia/Tokyo', 'Asia/Seoul',
                      'America/New_York', 'America/Los_Angeles', 'Europe/London', 'Europe/Berlin'].map(tz => (
                      <option key={tz} value={tz}>{tz}</option>
                    ))}
                  </select>
                </div>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs text-zinc-400 mb-1 font-medium">Hardware Concurrency (cores)</label>
                  <select
                    value={draft.hardware_concurrency}
                    onChange={(e) => setDraft({ ...draft, hardware_concurrency: Number(e.target.value) })}
                    className="w-full px-3 py-2 bg-zinc-700 border border-zinc-600 rounded-lg text-white text-sm focus:border-emerald-500 focus:outline-none"
                  >
                    {[2, 4, 6, 8, 10, 12, 16, 20, 24, 32].map(n => (
                      <option key={n} value={n}>{n} cores</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-xs text-zinc-400 mb-1 font-medium">Device Memory (GB)</label>
                  <select
                    value={draft.device_memory}
                    onChange={(e) => setDraft({ ...draft, device_memory: Number(e.target.value) })}
                    className="w-full px-3 py-2 bg-zinc-700 border border-zinc-600 rounded-lg text-white text-sm focus:border-emerald-500 focus:outline-none"
                  >
                    {[2, 4, 8, 16, 32, 64].map(n => (
                      <option key={n} value={n}>{n} GB</option>
                    ))}
                  </select>
                </div>
              </div>
            </>
          )}

          {tab === 'graphics' && (
            <>
              <div>
                <label className="block text-xs text-zinc-400 mb-1 font-medium">GPU Preset</label>
                <select
                  onChange={(e) => {
                    const g = GPU_POOL[parseInt(e.target.value)];
                    if (g) setDraft({ ...draft, webgl_vendor: g.vendor, webgl_renderer: g.renderer });
                  }}
                  defaultValue=""
                  className="w-full px-3 py-2 bg-zinc-700 border border-zinc-600 rounded-lg text-white text-sm focus:border-emerald-500 focus:outline-none"
                >
                  <option value="" disabled>— เลือก GPU preset —</option>
                  {GPU_POOL.map((g, i) => (
                    <option key={i} value={i}>{gpuShortLabel(g.renderer)} ({g.vendor.includes('NVIDIA') ? 'NVIDIA' : g.vendor.includes('AMD') ? 'AMD' : 'Intel'})</option>
                  ))}
                </select>
              </div>
              {field('WebGL Vendor', 'webgl_vendor')}
              {field('WebGL Renderer', 'webgl_renderer')}
              <div className="bg-zinc-800 rounded-xl p-4 border border-zinc-700/50">
                <p className="text-xs text-zinc-400 font-medium mb-2">Preview</p>
                <p className="text-xs font-mono text-cyan-300 break-all">{draft.webgl_renderer}</p>
                <p className="text-xs font-mono text-zinc-400 mt-1">{draft.webgl_vendor}</p>
              </div>
            </>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-zinc-700 flex gap-3 justify-end">
          <button
            onClick={onClose}
            className="px-5 py-2.5 bg-zinc-700 hover:bg-zinc-600 rounded-lg text-sm font-medium transition"
          >
            ยกเลิก
          </button>
          <button
            onClick={() => { onSave(draft); onClose(); }}
            className="px-5 py-2.5 bg-emerald-600 hover:bg-emerald-500 rounded-lg text-sm font-bold transition"
          >
            💾 บันทึก
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Profile Card ──────────────────────────────────────────────────────────────

function ProfileCard({
  profile,
  index,
  onEdit,
  onClone,
  onDelete,
}: {
  profile: BrowserProfile;
  index: number;
  onEdit: () => void;
  onClone: () => void;
  onDelete: () => void;
}) {
  const color = BROWSER_COLOR[profile.browser];
  const gpuLabel = gpuShortLabel(profile.webgl_renderer);

  return (
    <div
      className="bg-zinc-900 border border-zinc-800 rounded-2xl overflow-hidden hover:border-zinc-600 transition-all duration-200 hover:shadow-lg hover:shadow-black/40 group"
      style={{ borderTopColor: color, borderTopWidth: 3 }}
    >
      {/* Card header */}
      <div className="px-5 pt-4 pb-3">
        <div className="flex items-start justify-between gap-2 mb-1">
          <div className="flex items-center gap-2 min-w-0">
            <span className="text-base shrink-0">
              {profile.browser === 'chrome' ? '🌐' : profile.browser === 'firefox' ? '🦊' : '🔷'}
            </span>
            <span className="font-semibold text-white text-sm truncate">{profile.name}</span>
          </div>
          <span className="shrink-0 text-xs bg-zinc-800 text-zinc-400 px-2 py-0.5 rounded-full font-mono">
            #{index + 1}
          </span>
        </div>
        <p className="text-zinc-500 text-xs font-mono truncate leading-relaxed">
          {profile.user_agent.slice(0, 72)}…
        </p>
      </div>

      {/* Stats grid */}
      <div className="px-5 pb-4 grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
        <div className="flex items-center gap-1.5 text-zinc-400">
          <span className="text-base">🕒</span>
          <span className="truncate">{profile.timezone.split('/')[1] || profile.timezone}</span>
        </div>
        <div className="flex items-center gap-1.5 text-zinc-400">
          <span className="text-base">💬</span>
          <span className="truncate">{profile.language.split(',')[0]}</span>
        </div>
        <div className="flex items-center gap-1.5 text-zinc-400">
          <span className="text-base">📐</span>
          <span>{profile.viewport_width}×{profile.viewport_height}</span>
        </div>
        <div className="flex items-center gap-1.5 text-zinc-400">
          <span className="text-base">🧠</span>
          <span>{profile.hardware_concurrency}C / {profile.device_memory}GB</span>
        </div>
        <div className="flex items-center gap-1.5 text-zinc-400 col-span-2">
          <span className="text-base">🎮</span>
          <span className="truncate font-mono" title={profile.webgl_renderer}>{gpuLabel}</span>
        </div>
        <div className="flex items-center gap-1.5 text-zinc-400">
          <span className="text-base">{OS_EMOJI[profile.os]}</span>
          <span>{OS_LABEL[profile.os]}</span>
        </div>
        <div className="flex items-center gap-1.5 text-zinc-400">
          <span className="text-base">💻</span>
          <span>{profile.platform}</span>
        </div>
      </div>

      {/* Actions */}
      <div className="border-t border-zinc-800 px-4 py-3 flex gap-2 opacity-70 group-hover:opacity-100 transition-opacity">
        <button
          onClick={onEdit}
          className="flex-1 px-3 py-1.5 bg-zinc-700 hover:bg-zinc-600 rounded-lg text-xs font-medium transition text-white"
        >
          ✏️ แก้ไข
        </button>
        <button
          onClick={onClone}
          className="flex-1 px-3 py-1.5 bg-zinc-700 hover:bg-zinc-600 rounded-lg text-xs font-medium transition text-white"
        >
          📋 โคลน
        </button>
        <button
          onClick={onDelete}
          className="px-3 py-1.5 bg-red-900/50 hover:bg-red-700/60 rounded-lg text-xs font-medium transition text-red-300 hover:text-red-100"
        >
          🗑️
        </button>
      </div>
    </div>
  );
}

// ── Main Component ────────────────────────────────────────────────────────────

interface Props {
  profiles: BrowserProfile[];
  onChange: (profiles: BrowserProfile[]) => void;
}

export default function BrowserProfiles({ profiles, onChange }: Props) {
  const [editTarget, setEditTarget] = useState<BrowserProfile | null>(null);
  const [generating, setGenerating] = useState(false);
  const [genCount, setGenCount] = useState(5);

  const add = (p: BrowserProfile) => onChange([...profiles, p]);
  const update = (updated: BrowserProfile) =>
    onChange(profiles.map((p) => (p.id === updated.id ? updated : p)));
  const clone = (p: BrowserProfile) =>
    add({ ...p, id: genId(), name: p.name + ' (copy)' });
  const remove = (id: string) => onChange(profiles.filter((p) => p.id !== id));

  const generateBatch = async () => {
    setGenerating(true);
    const batch: BrowserProfile[] = [];
    for (let i = 0; i < genCount; i++) {
      batch.push(generateRandomProfile());
      await new Promise((r) => setTimeout(r, 30)); // small delay for effect
    }
    onChange([...profiles, ...batch]);
    setGenerating(false);
  };

  const loadDefaults = () => {
    const existing = new Set(profiles.map((p) => p.id));
    const toAdd = DEFAULT_BROWSER_PROFILES.filter((p) => !existing.has(p.id));
    onChange([...profiles, ...toAdd]);
  };

  const chromeCount = profiles.filter((p) => p.browser === 'chrome').length;
  const edgeCount = profiles.filter((p) => p.browser === 'edge').length;
  const ffCount = profiles.filter((p) => p.browser === 'firefox').length;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-2xl font-semibold text-white">🛡️ Browser Profiles</h2>
          <p className="text-emerald-400 text-xs mt-0.5 font-medium">Advanced Stealth: 40+ deterministic signals (Canvas, Audio, WebGL, Battery, Fonts, Sensors, Behavior telemetry) — auto-generated per proxy</p>
          <p className="text-zinc-400 text-sm mt-1">
            {profiles.length} profiles •&nbsp;
            <span style={{ color: BROWSER_COLOR.chrome }}>Chrome {chromeCount}</span> ·&nbsp;
            <span style={{ color: BROWSER_COLOR.edge }}>Edge {edgeCount}</span> ·&nbsp;
            <span style={{ color: BROWSER_COLOR.firefox }}>Firefox {ffCount}</span>
          </p>
        </div>
        <div className="flex gap-2 flex-wrap">
          <button
            onClick={loadDefaults}
            className="px-4 py-2 bg-zinc-700 hover:bg-zinc-600 rounded-lg text-sm font-medium transition"
          >
            📦 Load Defaults
          </button>
          <button
            onClick={() => add(generateRandomProfile())}
            className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 rounded-lg text-sm font-medium transition"
          >
            🎲 สร้างแบบสุ่ม 1 ตัว
          </button>
        </div>
      </div>

      {/* Informative Alert */}
      <div className="bg-amber-500/10 border border-amber-500/25 rounded-2xl p-5 text-sm text-amber-300 flex items-start gap-4">
        <span className="text-2xl leading-none">⚠️</span>
        <div>
          <p className="font-semibold mb-1 text-sm text-white">ความสำคัญของจำนวน Browser Profile (Fingerprint Uniqueness)</p>
          <p className="text-zinc-400 leading-relaxed text-xs">
            เพื่อความปลอดภัยสูงสุดในการกดบัตร แนะนำให้สร้าง <b>Browser Profiles ให้มีจำนวนครอบคลุมหรือมากกว่าจำนวน Proxy/Worker ทั้งหมดที่ใช้งานจริง</b> (ตัวอย่างเช่น หากระบบมี 8 Workers และแต่ละ Worker ทำงาน 5 Proxies รวมทั้งหมด 40 เซสชัน ควรมีอย่างน้อย 40 Profiles) เพื่อป้องกันการทับซ้อนของลายนิ้วมือเบราว์เซอร์บนต่าง IP ซึ่งเป็นพฤติกรรมผิดสังเกตที่ระบบป้องกัน (Cloudflare/Queue-it) สามารถตรวจจับและบล็อกได้ง่าย
          </p>
        </div>
      </div>

      {/* Batch generate bar */}
      <div className="bg-zinc-800/60 border border-zinc-700/50 rounded-xl p-4 flex items-center gap-4 flex-wrap">
        <span className="text-sm text-zinc-300 font-medium">🎰 สร้างแบบสุ่มหลายตัว</span>
        <div className="flex items-center gap-2">
          {[5, 10, 20, 40, 60, 80, 100].map((n) => (
            <button
              key={n}
              onClick={() => setGenCount(n)}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold transition ${
                genCount === n
                  ? 'bg-indigo-600 text-white'
                  : 'bg-zinc-700 text-zinc-300 hover:bg-zinc-600'
              }`}
            >
              {n}
            </button>
          ))}
        </div>
        <button
          onClick={generateBatch}
          disabled={generating}
          className="px-5 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-60 rounded-lg text-sm font-bold transition flex items-center gap-2"
        >
          {generating ? (
            <>
              <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
              </svg>
              กำลังสร้าง...
            </>
          ) : (
            `🎲 สร้าง ${genCount} profiles`
          )}
        </button>
        <button
          onClick={() => onChange([])}
          className="ml-auto px-4 py-2 bg-red-900/40 hover:bg-red-700/50 rounded-lg text-xs text-red-300 hover:text-red-100 font-medium transition"
        >
          🗑️ ล้างทั้งหมด
        </button>
      </div>

      {/* Cards */}
      {profiles.length === 0 ? (
        <div className="text-center py-16 text-zinc-500">
          <p className="text-5xl mb-4">🛡️</p>
          <p className="text-lg font-semibold text-zinc-400">ยังไม่มี Browser Profile</p>
          <p className="text-sm mt-2">กด "Load Defaults" เพื่อโหลด 5 profiles ตั้งต้น หรือ "สร้างแบบสุ่ม"</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {profiles.map((p, i) => (
            <ProfileCard
              key={p.id}
              profile={p}
              index={i}
              onEdit={() => setEditTarget(p)}
              onClone={() => clone(p)}
              onDelete={() => remove(p.id)}
            />
          ))}
        </div>
      )}

      {/* Export / Import */}
      {profiles.length > 0 && (
        <div className="flex gap-3 pt-2">
          <button
            onClick={() => {
              const blob = new Blob([JSON.stringify(profiles, null, 2)], { type: 'application/json' });
              const url = URL.createObjectURL(blob);
              const a = document.createElement('a');
              a.href = url;
              a.download = 'browser-profiles.json';
              a.click();
              URL.revokeObjectURL(url);
            }}
            className="px-4 py-2 bg-zinc-700 hover:bg-zinc-600 rounded-lg text-xs font-medium transition"
          >
            📤 Export JSON
          </button>
          <label className="px-4 py-2 bg-zinc-700 hover:bg-zinc-600 rounded-lg text-xs font-medium transition cursor-pointer">
            📥 Import JSON
            <input
              type="file"
              accept=".json"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (!file) return;
                file.text().then((text) => {
                  try {
                    const data = JSON.parse(text);
                    if (Array.isArray(data)) onChange([...profiles, ...data]);
                  } catch {}
                });
                e.target.value = '';
              }}
            />
          </label>
        </div>
      )}

      {/* Edit Modal */}
      {editTarget && (
        <EditModal
          profile={editTarget}
          onSave={update}
          onClose={() => setEditTarget(null)}
        />
      )}
    </div>
  );
}
