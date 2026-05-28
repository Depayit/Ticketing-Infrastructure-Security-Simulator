import { useState, useEffect, useRef } from 'react';
import BrowserProfiles, {
  BrowserProfile,
  DEFAULT_BROWSER_PROFILES,
} from './BrowserProfiles';

interface Profile {
  fullname: string;
  email: string;
  phone: string;
  id_card: string;
  card: { number: string; exp: string; cvv: string };
}

interface Config {
  // bot_mode removed — Playwright Stealth is the only supported mode now
  event_id: string;
  target_url?: string;
  click_selector?: string;
  refresh_mode?: 'auto_refresh' | 'dom_watch';
  refresh_interval?: number;
  action_after_click?: 'notify' | 'auto_checkout';
  telegram_token: string;
  telegram_chat_id: string;
  captcha_key: string;
  redis_url: string;
  proxies: string[];
  profiles: Profile[];
  ticket_priorities: string[];
  browser_profiles: BrowserProfile[];
}

type SaveState = 'idle' | 'saving' | 'success' | 'error';

function isProfileReady(p: Profile): boolean {
  return !!(
    p.fullname.trim() && p.email.trim() && p.phone.trim() &&
    p.id_card.trim() && p.card.number.trim() && p.card.exp.trim() && p.card.cvv.trim()
  );
}

function profileMissingFields(p: Profile): string[] {
  const m: string[] = [];
  if (!p.fullname.trim()) m.push('ชื่อ-นามสกุล');
  if (!p.email.trim()) m.push('Email');
  if (!p.phone.trim()) m.push('เบอร์โทร');
  if (!p.id_card.trim()) m.push('เลขบัตรประชาชน');
  if (!p.card.number.trim()) m.push('หมายเลขบัตร');
  if (!p.card.exp.trim()) m.push('วันหมดอายุ');
  if (!p.card.cvv.trim()) m.push('CVV');
  return m;
}

function ProfileReadinessBadge({ profile }: { profile: Profile }) {
  const ready = isProfileReady(profile);
  const missing = profileMissingFields(profile);
  return ready ? (
    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
      <svg className="w-3 h-3" viewBox="0 0 12 12" fill="none">
        <circle cx="6" cy="6" r="5.5" fill="#22c55e" fillOpacity="0.2" stroke="#22c55e" />
        <path d="M3.5 6 L5.2 7.8 L8.5 4.5" stroke="#22c55e" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      พร้อมใช้งาน
    </span>
  ) : (
    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-amber-500/15 text-amber-400 border border-amber-500/30 cursor-help"
      title={`ยังขาด: ${missing.join(', ')}`}>
      <svg className="w-3 h-3" viewBox="0 0 12 12" fill="none">
        <circle cx="6" cy="6" r="5.5" fill="#f59e0b" fillOpacity="0.2" stroke="#f59e0b" />
        <path d="M6 3.5 V6.5" stroke="#f59e0b" strokeWidth="1.5" strokeLinecap="round" />
        <circle cx="6" cy="8.5" r="0.75" fill="#f59e0b" />
      </svg>
      ไม่ครบ ({missing.length})
    </span>
  );
}

function ReadinessOverview({ profiles }: { profiles: Profile[] }) {
  if (profiles.length === 0) return null;
  const ready = profiles.filter(isProfileReady).length;
  const pct = Math.round((ready / profiles.length) * 100);
  return (
    <div className="bg-zinc-800/60 border border-zinc-700/50 rounded-xl p-4 flex items-center gap-4">
      <div className="relative flex-shrink-0 w-14 h-14">
        <svg className="w-14 h-14 -rotate-90" viewBox="0 0 56 56">
          <circle cx="28" cy="28" r="22" strokeWidth="5" stroke="#3f3f46" fill="none" />
          <circle cx="28" cy="28" r="22" strokeWidth="5" fill="none"
            stroke={pct === 100 ? '#22c55e' : '#f59e0b'} strokeLinecap="round"
            strokeDasharray={`${(pct / 100) * 138.2} 138.2`}
            style={{ transition: 'stroke-dasharray 0.5s ease' }} />
        </svg>
        <span className="absolute inset-0 flex items-center justify-center text-sm font-bold text-white">{pct}%</span>
      </div>
      <div>
        <p className="text-sm text-zinc-400">โปรไฟล์ผู้ซื้อพร้อม</p>
        <p className="text-lg font-bold text-white">
          {ready} / {profiles.length}{' '}
          {ready === profiles.length
            ? <span className="text-emerald-400 text-sm">✓ ทั้งหมดพร้อม</span>
            : <span className="text-amber-400 text-sm">⚠ บางตัวไม่ครบ</span>}
        </p>
      </div>
    </div>
  );
}

export default function Setup() {
  type Tab = 'basic' | 'telegram' | 'captcha' | 'proxies' | 'profiles' | 'browser' | 'priorities';
  const [setupTab, setSetupTab] = useState<Tab>('basic');
  const [config, setConfig] = useState<Config>({
    event_id: '',
    target_url: '',
    click_selector: 'button:has-text("Add to Cart"), button:has-text("ซื้อเลย"), button:has-text("ใส่ตะกร้า")',
    refresh_mode: 'auto_refresh',
    refresh_interval: 1.0,
    action_after_click: 'notify',
    telegram_token: '',
    telegram_chat_id: '',
    captcha_key: '',
    redis_url: 'redis://redis:6379/0',
    proxies: [],
    profiles: [],
    ticket_priorities: ['VIP', 'GA', 'Standing'],
    browser_profiles: DEFAULT_BROWSER_PROFILES,
  });
  const [savedConfig, setSavedConfig] = useState('');
  const [newProxy, setNewProxy] = useState('');
  const [newProfile, setNewProfile] = useState<Profile>({
    fullname: '', email: '', phone: '', id_card: '',
    card: { number: '', exp: '', cvv: '' },
  });
  const [newPriority, setNewPriority] = useState('');
  const [saveState, setSaveState] = useState<SaveState>('idle');
  const [saveError, setSaveError] = useState('');
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const hasUnsavedChanges = JSON.stringify(config) !== savedConfig && savedConfig !== '';

  useEffect(() => {
    fetch('/api/config')
      .then((r) => r.json())
      .then((data) => {
        if (!data.browser_profiles || data.browser_profiles.length === 0) {
          data.browser_profiles = DEFAULT_BROWSER_PROFILES;
        }
        setConfig(data);
        setSavedConfig(JSON.stringify(data));
      })
      .catch(() => {});
  }, []);

  const saveConfig = async () => {
    if (saveState === 'saving') return;
    setSaveState('saving');
    setSaveError('');
    try {
      const res = await fetch('/api/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config),
      });
      if (res.ok) {
        setSavedConfig(JSON.stringify(config));
        setSaveState('success');
      } else {
        throw new Error(await res.text() || `HTTP ${res.status}`);
      }
    } catch (e: unknown) {
      setSaveError(e instanceof Error ? e.message : 'เกิดข้อผิดพลาด');
      setSaveState('error');
    }
    if (toastTimer.current) clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setSaveState('idle'), 4000);
  };

  const TabButton = ({ name, label }: { name: Tab; label: string }) => (
    <button
      onClick={() => setSetupTab(name)}
      className={`px-4 py-2 rounded-lg font-medium transition text-sm ${
        setupTab === name ? 'bg-emerald-600 text-white' : 'bg-zinc-800 text-zinc-300 hover:bg-zinc-700'
      }`}
    >
      {label}
    </button>
  );

  const SaveButton = () => {
    const base = 'relative flex-1 px-6 py-4 rounded-xl font-bold text-lg transition-all duration-200 flex items-center justify-center gap-3 disabled:opacity-60 disabled:cursor-not-allowed';
    if (saveState === 'saving') return (
      <button disabled className={`${base} bg-emerald-700 text-emerald-100`}>
        <svg className="w-5 h-5 animate-spin" fill="none" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
        </svg>
        กำลังบันทึก...
      </button>
    );
    if (saveState === 'success') return (
      <button disabled className={`${base} bg-emerald-600/70 text-emerald-200`}>
        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
        </svg>
        บันทึกสำเร็จ!
      </button>
    );
    if (saveState === 'error') return (
      <button onClick={saveConfig} className={`${base} bg-red-600 hover:bg-red-500 text-white`}>
        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v4m0 4h.01M12 2a10 10 0 100 20A10 10 0 0012 2z" />
        </svg>
        ลองอีกครั้ง
      </button>
    );
    return (
      <button onClick={saveConfig} className={`${base} bg-emerald-600 hover:bg-emerald-500 active:scale-[0.98] text-white shadow-lg shadow-emerald-900/40`}>
        💾 บันทึกการตั้งค่า
      </button>
    );
  };

  const readyBuyers = config.profiles.filter(isProfileReady).length;

  return (
    <div className="max-w-6xl mx-auto">
      {/* Header */}
      <div className="flex items-start justify-between mb-8 gap-4 flex-wrap">
        <h1 className="text-4xl font-bold bg-gradient-to-r from-emerald-400 to-cyan-400 bg-clip-text text-transparent">
          Bot Configuration
        </h1>
        {hasUnsavedChanges && saveState === 'idle' && (
          <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold bg-amber-500/15 text-amber-400 border border-amber-500/30 animate-pulse self-center">
            ● มีการเปลี่ยนแปลงที่ยังไม่ได้บันทึก
          </span>
        )}
      </div>

      {/* Tabs */}
      <div className="flex flex-wrap gap-2 mb-8">
        <TabButton name="basic" label="📋 Basic" />
        <TabButton name="telegram" label="📱 Telegram" />
        <TabButton name="captcha" label="🔐 CAPTCHA" />
        <TabButton name="proxies" label="🌐 Proxies" />
        <TabButton
          name="profiles"
          label={`👤 Buyers${config.profiles.length > 0 ? ` (${readyBuyers}/${config.profiles.length})` : ''}`}
        />
        <TabButton
          name="browser"
          label={`🛡️ Browser${config.browser_profiles.length > 0 ? ` (${config.browser_profiles.length})` : ''}`}
        />
        <TabButton name="priorities" label="⭐ Priorities" />
      </div>

      {/* Content panel */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-8 mb-8">

        {/* Basic */}
        {setupTab === 'basic' && (
          <div className="space-y-6">
            <h2 className="text-2xl font-semibold mb-4">Basic Settings</h2>
            
            {/* Playwright Stealth Mode — Honest status (reflects what is ACTUALLY implemented in worker/akamai.py today) */}
            <div className="bg-zinc-950 border-2 border-emerald-500/70 rounded-2xl p-6 mb-4 shadow-inner">
              <div className="flex items-start gap-4">
                <div className="text-4xl mt-1">🎭</div>
                <div className="flex-1 space-y-2">
                  <div>
                    <div className="font-bold text-emerald-400 text-xl tracking-tight">Playwright Stealth Mode — โหมดเดียวที่ระบบรองรับ (GraphQL ลบออกหมดแล้ว)</div>
                    <div className="text-red-400/90 text-xs font-medium mt-0.5">⚠️ GraphQL / Direct API / ttm mode ถูกนำออกจากโค้ดและ UI แล้ว เพราะ Fraud Engine ให้ Risk Score 0.9–0.95 ตลอด</div>
                  </div>

                  <div className="text-sm text-zinc-300 leading-relaxed">
                    แผน 6 ข้อ <strong className="text-emerald-300">ทำครบแล้วทั้งหมด</strong> — โค้ดจริงอยู่ใน <code className="text-emerald-300/90">worker/stealth.py</code> + <code className="text-emerald-300/90">worker/akamai.py</code> + <code className="text-emerald-300/90">worker/bot.py</code>:
                  </div>

                  <ul className="text-xs space-y-1.5 pl-1 font-light">
                    <li className="text-emerald-200/90">
                      ✅ <strong className="text-emerald-300">1. Advanced Fingerprint</strong> — <code>build_fingerprint()</code> สร้าง <strong>63 signals</strong> แบบ deterministic ต่อ proxy (Canvas/Audio seed, WebGL, Fonts, Battery, Connection, Speech, WebRTC, Navigator ลึก, UA-CH, hashes) · signal_count ≥140
                    </li>
                    <li className="text-emerald-200/90">
                      ✅ <strong className="text-emerald-300">2. Human Behavior Simulation</strong> — <code>HumanBehavior</code>: Bézier mouse + ease-in-out velocity, natural scroll + reversal, hover dwell, thinking pauses, click pressure — บันทึกทุก gesture เป็น telemetry event
                    </li>
                    <li className="text-emerald-200/90">
                      ✅ <strong className="text-emerald-300">3. Sensor Data Capture + Emulator</strong> — warmup จับ <code>sensor_data</code> POST จริง (capture) ไม่เจอก็ <code>build_sensor_payload()</code> synthesize · เก็บคู่ telemetry + fingerprint_id ลง <strong>Redis</strong> ผ่าน <code>AkamaiCookieJar</code>
                    </li>
                    <li className="text-emerald-200/90">
                      ✅ <strong className="text-emerald-300">4. Stealth Injection</strong> — <code>build_stealth_script()</code> <strong>28 overrides</strong> (~8.4KB) ฉีดผ่าน <code>add_init_script</code> + <strong>CDP</strong> <code>Page.addScriptToEvaluateOnNewDocument</code>
                    </li>
                    <li className="text-emerald-200/90">
                      ✅ <strong className="text-emerald-300">5. Fraud Rule Alignment</strong> — <code>_submit_session_signals()</code> ยิง telemetry (mousemove/scroll/hover) + sensor ก่อนล็อกที่นั่ง → <code>api_only_ratio=0</code>, mouse entropy=1.0, token_to_lock_ms &gt; 2s, x-session-id เดียวทั้ง funnel
                    </li>
                    <li className="text-emerald-200/90">
                      ✅ <strong className="text-emerald-300">6. Queue-it Browser Warmup</strong> — <code>_akamai_warmup_loop</code> รัน Chromium จริง (Playwright) สร้าง sensor+telemetry แล้ว token warmup/purchase consume สัญญาณที่ warm จากเบราว์เซอร์
                    </li>
                  </ul>

                  <div className="text-[11px] text-zinc-400 leading-relaxed mt-2 pt-2 border-t border-zinc-700">
                    <strong className="text-zinc-300">สรุป:</strong> ครบทั้ง pipeline — Fingerprint → Stealth inject → Human behavior → Sensor capture/synthesize → Redis bind → Fraud-aligned telemetry submit → Token warmup. ทุกอย่าง deterministic ต่อ proxy และผ่าน smoke test แล้ว
                  </div>

                  <div className="pt-1 text-[10px] text-emerald-400/70 font-mono">
                    63 signals ✓ · 28 stealth overrides + CDP ✓ · Bézier behavior ✓ · Sensor↔Redis ✓ · api_only_ratio=0 ✓ · Browser-warmed tokens ✓
                  </div>
                </div>
              </div>
            </div>

            {/* Unified Playwright Configuration (works for TTM concerts and general sites) */}
            <div className="space-y-4 pt-2">
              <div>
                <label className="block text-zinc-300 mb-2 font-medium">Event ID (optional สำหรับ TTM Concert)</label>
                <input type="text" value={config.event_id}
                  onChange={(e) => setConfig({ ...config, event_id: e.target.value })}
                  className="w-full px-4 py-3 bg-zinc-800 border border-zinc-700 rounded-lg text-white focus:border-emerald-500 focus:outline-none"
                  placeholder="ttm-bkk-blackpink-world-tour-2026" />
              </div>

              <div>
                <label className="block text-zinc-300 mb-2 font-medium">Target URL / ลิงก์หน้าสินค้าเป้าหมาย</label>
                <input type="text" value={config.target_url || ''}
                  onChange={(e) => setConfig({ ...config, target_url: e.target.value })}
                  className="w-full px-4 py-3 bg-zinc-800 border border-zinc-700 rounded-lg text-white focus:border-emerald-500 focus:outline-none"
                  placeholder="https://www.thaiticketmajor.com/concert/... หรือเว็บทั่วไป" />
              </div>

              <div>
                <label className="block text-zinc-300 mb-2 font-medium">Button Selector / ปุ่มสั่งซื้อ (CSS Selector หรือ Text)</label>
                <input type="text" value={config.click_selector || ''}
                  onChange={(e) => setConfig({ ...config, click_selector: e.target.value })}
                  className="w-full px-4 py-3 bg-zinc-800 border border-zinc-700 rounded-lg text-white focus:border-emerald-500 focus:outline-none"
                  placeholder='button:has-text("ซื้อเลย"), button:has-text("Add to Cart")' />
                <p className="text-zinc-500 text-xs mt-1.5 leading-relaxed">
                  💡 ใช้ได้ทั้ง TTM และเว็บ E-commerce ทั่วไป (Popmart, Brandname ฯลฯ)
                </p>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-zinc-300 mb-2 font-medium">Refresh Mode / รูปแบบการหาปุ่ม</label>
                  <select value={config.refresh_mode || 'auto_refresh'}
                    onChange={(e) => setConfig({ ...config, refresh_mode: e.target.value as 'auto_refresh' | 'dom_watch' })}
                    className="w-full px-4 py-3 bg-zinc-800 border border-zinc-700 rounded-lg text-white focus:border-emerald-500 focus:outline-none">
                    <option value="auto_refresh">Auto Refresh (โหลดหน้าใหม่จนกว่าปุ่มจะกดได้)</option>
                    <option value="dom_watch">DOM Watch (เฝ้าดูหน้าเดิม)</option>
                  </select>
                </div>
                <div>
                  <label className="block text-zinc-300 mb-2 font-medium">Refresh Interval / ความเร็วตรวจสอบ (วินาที)</label>
                  <input type="number" step="0.1" min="0.1" value={config.refresh_interval || 1.0}
                    onChange={(e) => setConfig({ ...config, refresh_interval: parseFloat(e.target.value) || 1.0 })}
                    className="w-full px-4 py-3 bg-zinc-800 border border-zinc-700 rounded-lg text-white focus:border-emerald-500 focus:outline-none"
                    placeholder="1.0" />
                </div>
              </div>

              <div>
                <label className="block text-zinc-300 mb-2 font-medium">Action After Click / หลังกดปุ่มสำเร็จ</label>
                <select value={config.action_after_click || 'notify'}
                  onChange={(e) => setConfig({ ...config, action_after_click: e.target.value as 'notify' | 'auto_checkout' })}
                  className="w-full px-4 py-3 bg-zinc-800 border border-zinc-700 rounded-lg text-white focus:border-emerald-500 focus:outline-none">
                  <option value="notify">Notify & Takeover (แจ้ง Telegram แล้วให้คนดำเนินการต่อ) [แนะนำ]</option>
                  <option value="auto_checkout">Auto Checkout (พยายามกรอกข้อมูล + ชำระเงินอัตโนมัติ)</option>
                </select>
              </div>
            </div>

            <div className="border-t border-zinc-800/80 pt-6">
              <label className="block text-zinc-300 mb-2 font-medium">Redis URL</label>
              <input type="text" value={config.redis_url}
                onChange={(e) => setConfig({ ...config, redis_url: e.target.value })}
                className="w-full px-4 py-3 bg-zinc-800 border border-zinc-700 rounded-lg text-white focus:border-emerald-500 focus:outline-none"
                placeholder="redis://redis:6379/0" />
            </div>
          </div>
        )}

        {/* Telegram */}
        {setupTab === 'telegram' && (
          <div className="space-y-6">
            <h2 className="text-2xl font-semibold mb-4">Telegram Settings</h2>
            <div>
              <label className="block text-zinc-300 mb-2">Bot Token</label>
              <input type="password" value={config.telegram_token}
                onChange={(e) => setConfig({ ...config, telegram_token: e.target.value })}
                className="w-full px-4 py-3 bg-zinc-800 border border-zinc-700 rounded-lg text-white focus:border-emerald-500 focus:outline-none"
                placeholder="YOUR_TELEGRAM_BOT_TOKEN_HERE" />
            </div>
            <div>
              <label className="block text-zinc-300 mb-2">Chat ID</label>
              <input type="text" value={config.telegram_chat_id}
                onChange={(e) => setConfig({ ...config, telegram_chat_id: e.target.value })}
                className="w-full px-4 py-3 bg-zinc-800 border border-zinc-700 rounded-lg text-white focus:border-emerald-500 focus:outline-none"
                placeholder="YOUR_CHAT_ID_HERE" />
            </div>
          </div>
        )}

        {/* CAPTCHA */}
        {setupTab === 'captcha' && (
          <div className="space-y-6">
            <h2 className="text-2xl font-semibold mb-4">CAPTCHA Settings</h2>
            <div>
              <label className="block text-zinc-300 mb-2">2Captcha/CapMonster API Key</label>
              <input type="password" value={config.captcha_key}
                onChange={(e) => setConfig({ ...config, captcha_key: e.target.value })}
                className="w-full px-4 py-3 bg-zinc-800 border border-zinc-700 rounded-lg text-white focus:border-emerald-500 focus:outline-none"
                placeholder="YOUR_2CAPTCHA_OR_CAPMONSTER_KEY_HERE" />
            </div>
            <p className="text-zinc-400 text-sm">⚠️ แนะนำ CapMonster สำหรับ Turnstile CAPTCHA ที่เร็วกว่า</p>
          </div>
        )}

        {/* Proxies */}
        {setupTab === 'proxies' && (
          <div className="space-y-6">
            <h2 className="text-2xl font-semibold mb-4">Proxy Management</h2>
            <div className="flex gap-2">
              <input type="text" value={newProxy}
                onChange={(e) => setNewProxy(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && newProxy.trim()) {
                    setConfig({ ...config, proxies: [...config.proxies, newProxy.trim()] });
                    setNewProxy('');
                  }
                }}
                className="flex-1 px-4 py-3 bg-zinc-800 border border-zinc-700 rounded-lg text-white focus:border-emerald-500 focus:outline-none"
                placeholder="http://user:pass@proxy:8000" />
              <button
                onClick={() => { if (newProxy.trim()) { setConfig({ ...config, proxies: [...config.proxies, newProxy.trim()] }); setNewProxy(''); } }}
                className="px-6 py-3 bg-emerald-600 hover:bg-emerald-500 rounded-lg font-medium transition">
                Add
              </button>
            </div>
            <div className="space-y-2">
              {config.proxies.map((proxy, idx) => (
                <div key={idx} className="flex justify-between items-center bg-zinc-800 p-3 rounded-lg">
                  <code className="text-cyan-400 text-sm">{proxy}</code>
                  <button onClick={() => setConfig({ ...config, proxies: config.proxies.filter((_, i) => i !== idx) })}
                    className="px-3 py-1 bg-red-600 hover:bg-red-500 rounded text-white text-sm transition">Remove</button>
                </div>
              ))}
            </div>
            <p className="text-zinc-400 text-sm">
              📌 {config.proxies.length} proxy(ies) • แนะนำ: 20–50 proxies สำหรับ production
            </p>
          </div>
        )}

        {/* Buyer Profiles */}
        {setupTab === 'profiles' && (
          <div className="space-y-6">
            <div className="flex items-center justify-between flex-wrap gap-3">
              <h2 className="text-2xl font-semibold">Buyer Profiles</h2>
            </div>
            <ReadinessOverview profiles={config.profiles} />
            <div className="bg-zinc-800 p-6 rounded-xl space-y-4 border border-zinc-700/50">
              <h3 className="font-semibold text-zinc-200">➕ เพิ่มโปรไฟล์ใหม่</h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {(['fullname', 'email', 'phone', 'id_card'] as const).map((key) => (
                  <input key={key} type={key === 'email' ? 'email' : 'text'}
                    value={newProfile[key]}
                    onChange={(e) => setNewProfile({ ...newProfile, [key]: e.target.value })}
                    className="px-4 py-2.5 bg-zinc-700 border border-zinc-600 rounded-lg text-white focus:border-emerald-500 focus:outline-none placeholder-zinc-500"
                    placeholder={{ fullname: 'ชื่อ-นามสกุล *', email: 'Email *', phone: 'เบอร์โทร *', id_card: 'เลขบัตรประชาชน *' }[key]} />
                ))}
              </div>
              <div className="grid grid-cols-3 gap-3">
                {(['number', 'exp', 'cvv'] as const).map((key) => (
                  <input key={key} type="text"
                    value={newProfile.card[key]}
                    onChange={(e) => setNewProfile({ ...newProfile, card: { ...newProfile.card, [key]: e.target.value } })}
                    className="px-4 py-2.5 bg-zinc-700 border border-zinc-600 rounded-lg text-white focus:border-emerald-500 focus:outline-none placeholder-zinc-500"
                    placeholder={{ number: 'หมายเลขบัตร *', exp: 'MM/YY *', cvv: 'CVV *' }[key]} />
                ))}
              </div>
              <button
                onClick={() => {
                  if (newProfile.fullname && newProfile.email) {
                    setConfig({ ...config, profiles: [...config.profiles, newProfile] });
                    setNewProfile({ fullname: '', email: '', phone: '', id_card: '', card: { number: '', exp: '', cvv: '' } });
                  }
                }}
                className="w-full px-4 py-2.5 bg-emerald-600 hover:bg-emerald-500 active:scale-[0.99] rounded-lg font-medium transition">
                Add Profile
              </button>
            </div>
            <div className="space-y-3">
              {config.profiles.map((profile, idx) => {
                const ready = isProfileReady(profile);
                const missing = profileMissingFields(profile);
                return (
                  <div key={idx} className={`bg-zinc-800 p-4 rounded-xl flex justify-between items-start gap-3 border ${ready ? 'border-emerald-800/40' : 'border-amber-700/40'}`}>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap mb-1">
                        <p className="font-semibold text-white truncate">{profile.fullname || '—'}</p>
                        <ProfileReadinessBadge profile={profile} />
                      </div>
                      <p className="text-zinc-400 text-sm">{profile.email}</p>
                      {!ready && <p className="text-amber-400/80 text-xs mt-1">ขาด: {missing.join(' • ')}</p>}
                    </div>
                    <button
                      onClick={() => setConfig({ ...config, profiles: config.profiles.filter((_, i) => i !== idx) })}
                      className="flex-shrink-0 px-3 py-1.5 bg-red-600 hover:bg-red-500 rounded-lg text-white text-sm transition">
                      ลบ
                    </button>
                  </div>
                );
              })}
              {config.profiles.length === 0 && (
                <p className="text-zinc-500 text-sm text-center py-6">ยังไม่มีโปรไฟล์ — กรอกแบบฟอร์มด้านบนเพื่อเพิ่ม</p>
              )}
            </div>
          </div>
        )}

        {/* Browser Profiles */}
        {setupTab === 'browser' && (
          <BrowserProfiles
            profiles={config.browser_profiles}
            onChange={(bp) => setConfig({ ...config, browser_profiles: bp })}
          />
        )}

        {/* Priorities */}
        {setupTab === 'priorities' && (
          <div className="space-y-6">
            <h2 className="text-2xl font-semibold mb-4">Ticket Priorities</h2>
            <div className="flex gap-2">
              <input type="text" value={newPriority}
                onChange={(e) => setNewPriority(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && newPriority.trim()) {
                    setConfig({ ...config, ticket_priorities: [...config.ticket_priorities, newPriority.trim()] });
                    setNewPriority('');
                  }
                }}
                className="flex-1 px-4 py-3 bg-zinc-800 border border-zinc-700 rounded-lg text-white focus:border-emerald-500 focus:outline-none"
                placeholder="e.g. VIP, GA, Standing, Premium" />
              <button
                onClick={() => { if (newPriority.trim()) { setConfig({ ...config, ticket_priorities: [...config.ticket_priorities, newPriority.trim()] }); setNewPriority(''); } }}
                className="px-6 py-3 bg-emerald-600 hover:bg-emerald-500 rounded-lg font-medium transition">
                Add
              </button>
            </div>
            <div className="flex flex-wrap gap-2">
              {config.ticket_priorities.map((priority, idx) => (
                <div key={idx} className="bg-zinc-800 px-4 py-2 rounded-lg flex items-center gap-2">
                  <span className="text-cyan-300 font-medium">#{idx + 1}</span>
                  <span className="text-white">{priority}</span>
                  <button
                    onClick={() => setConfig({ ...config, ticket_priorities: config.ticket_priorities.filter((_, i) => i !== idx) })}
                    className="text-red-400 hover:text-red-300 transition ml-1">✕</button>
                </div>
              ))}
            </div>
            <p className="text-zinc-400 text-sm">🎯 บอทจะลองซื้อตามลำดับ priority ที่กำหนด</p>
          </div>
        )}
      </div>

      {/* Save bar */}
      <div className="flex gap-4 items-center">
        <SaveButton />
        {saveState === 'success' && (
          <div className="flex items-center gap-2 px-4 py-3 bg-emerald-500/15 border border-emerald-500/40 rounded-xl text-emerald-400 font-medium text-sm whitespace-nowrap">
            ✓ Config ถูกส่งไปยัง Redis แล้ว — บอทจะใช้ค่าใหม่ในรอบถัดไป
          </div>
        )}
        {saveState === 'error' && (
          <div className="flex items-center gap-2 px-4 py-3 bg-red-500/15 border border-red-500/40 rounded-xl text-red-400 font-medium text-sm whitespace-nowrap">
            ✗ {saveError}
          </div>
        )}
      </div>
    </div>
  );
}
