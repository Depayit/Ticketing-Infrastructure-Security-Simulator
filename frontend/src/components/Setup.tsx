import { useState, useEffect, useRef } from 'react';
import BrowserProfiles, {
  BrowserProfile,
  DEFAULT_BROWSER_PROFILES,
} from './BrowserProfiles';
import ModeSettingsGuide from './ModeSettingsGuide';
import { BOT_MODE_META, MODE_CATEGORIES, normalizeBotMode } from '../modeGuide';

interface Profile {
  fullname: string;
  email: string;
  phone: string;
  id_card: string;
  password?: string;
  card?: { number: string; exp: string; cvv: string };
  ticket_count?: number;
  ticket_buyers?: string[];
}

interface QueueItConfig {
  headless: boolean;
  manual_takeover: boolean;
  hold_seconds: number;
  max_minutes: number;
  stop_on_first: boolean;
  book_selector: string;
  seat_selector: string;
  addtocart_selector: string;
  join_texts: string[];
  stillhere_texts: string[];
}

interface DefenseDemoConfig {
  default_url: string;
  max_poll_attempts: number;
  poll_interval_min: number;
  poll_interval_max: number;
  login_email: string;
  login_password: string;
}

const DEFAULT_DEFENSE_DEMO: DefenseDemoConfig = {
  default_url: 'http://defense-gateway:8090/?demo=1',
  max_poll_attempts: 15,
  poll_interval_min: 4,
  poll_interval_max: 6,
  login_email: '',
  login_password: 'demo123',
};

const DEFAULT_QUEUEIT: QueueItConfig = {
  headless: true,
  manual_takeover: false,
  hold_seconds: 600,
  max_minutes: 120,
  stop_on_first: true,
  book_selector:
    "a:has-text('จอง'), a:has-text('ซื้อบัตร'), button:has-text('จอง'), button:has-text('ซื้อบัตร'), a:has-text('Buy')",
  seat_selector:
    ".seat:not(.sold):not(.unavailable), .seat.available, .seat.open, .seat-available, " +
    ".zone-available, .zone-clickable, .zone-open, [data-zone-status='available'], " +
    "[data-seat-available='true'], [data-status='available'], " +
    "li.available, .seatAvailable, " +
    "svg .seat-circle:not(.sold), svg rect.available, svg .seat-node:not(.unavailable)",
  addtocart_selector:
    "button:has-text('ใส่ตะกร้า'), button:has-text('Add to Cart'), button:has-text('ดำเนินการต่อ'), button:has-text('ยืนยัน')",
  join_texts: ['Join the Queue', 'Join Queue', 'เข้าสู่คิว', 'เข้าคิว'],
  stillhere_texts: ['Yes', "Yes, I'm here", 'ใช่', 'ยังอยู่', 'Continue'],
};

interface Config {
  bot_mode?: string;
  event_id: string;
  target_url?: string;
  proxies_per_worker?: number;
  click_selector?: string;
  refresh_mode?: 'auto_refresh' | 'dom_watch';
  refresh_interval?: number;
  action_after_click?: 'notify' | 'auto_checkout';
  telegram_token: string;
  telegram_chat_id: string;
  redis_url: string;
  proxies: string[];
  profiles: Profile[];
  browser_profiles: BrowserProfile[];
  queueit: QueueItConfig;
  defense_demo?: DefenseDemoConfig;
  ticket_count: number;
  ticket_buyers: string[];
  ticket_priorities?: string[];
  membership_code?: string;
}

function TagListEditor({
  label,
  hint,
  placeholder,
  tags,
  onChange,
  color = 'cyan',
}: {
  label: string;
  hint?: string;
  placeholder: string;
  tags: string[];
  onChange: (tags: string[]) => void;
  color?: 'cyan' | 'amber' | 'violet' | 'emerald';
}) {
  const [draft, setDraft] = useState('');
  const colorMap = {
    cyan: 'text-cyan-300 border-cyan-800/50',
    amber: 'text-amber-300 border-amber-800/50',
    violet: 'text-violet-300 border-violet-800/50',
    emerald: 'text-emerald-300 border-emerald-800/50',
  };

  const add = () => {
    const v = draft.trim();
    if (!v || tags.includes(v)) return;
    onChange([...tags, v]);
    setDraft('');
  };

  return (
    <div className="space-y-2">
      <div>
        <label className="block text-zinc-300 font-medium text-sm">{label}</label>
        {hint && <p className="text-zinc-500 text-xs mt-0.5 leading-relaxed">{hint}</p>}
      </div>
      <div className="flex gap-2">
        <input
          type="text"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), add())}
          placeholder={placeholder}
          className="flex-1 px-3 py-2.5 bg-zinc-800 border border-zinc-700 rounded-lg text-white text-sm focus:border-emerald-500 focus:outline-none"
        />
        <button type="button" onClick={add}
          className="px-4 py-2.5 bg-zinc-700 hover:bg-zinc-600 rounded-lg text-sm font-medium transition">
          เพิ่ม
        </button>
      </div>
      {tags.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {tags.map((tag, idx) => (
            <span key={`${tag}-${idx}`}
              className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-zinc-800 border text-sm ${colorMap[color]}`}>
              {tags.length > 1 && <span className="opacity-50 text-xs">#{idx + 1}</span>}
              {tag}
              <button type="button" onClick={() => onChange(tags.filter((_, i) => i !== idx))}
                className="opacity-60 hover:opacity-100 ml-0.5">✕</button>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function mergeDefenseDemo(raw: Partial<DefenseDemoConfig> | undefined): DefenseDemoConfig {
  return { ...DEFAULT_DEFENSE_DEMO, ...raw };
}

function updateDefenseDemo(config: Config, patch: Partial<DefenseDemoConfig>): Config {
  return { ...config, defense_demo: { ...mergeDefenseDemo(config.defense_demo), ...patch } };
}

function mergeQueueIt(raw: Partial<QueueItConfig> | undefined): QueueItConfig {
  return {
    ...DEFAULT_QUEUEIT,
    ...raw,
    join_texts: raw?.join_texts?.length ? raw.join_texts : DEFAULT_QUEUEIT.join_texts,
    stillhere_texts: raw?.stillhere_texts?.length ? raw.stillhere_texts : DEFAULT_QUEUEIT.stillhere_texts,
  };
}

function updateQueueIt(config: Config, patch: Partial<QueueItConfig>): Config {
  return { ...config, queueit: { ...config.queueit, ...patch } };
}

type SaveState = 'idle' | 'saving' | 'success' | 'error';

function isProfileReady(p: Profile): boolean {
  return !!(p.fullname.trim() && p.email.trim() && p.password?.trim() && p.phone.trim() && p.id_card.trim());
}

function profileMissingFields(p: Profile): string[] {
  const m: string[] = [];
  if (!p.fullname.trim()) m.push('ชื่อ-นามสกุล');
  if (!p.email.trim()) m.push('Email');
  if (!p.password?.trim()) m.push('รหัสผ่าน');
  if (!p.phone.trim()) m.push('เบอร์โทร');
  if (!p.id_card.trim()) m.push('เลขบัตรประชาชน');
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
  type Tab = 'basic' | 'telegram' | 'proxies' | 'profiles' | 'browser' | 'ttm';
  const [setupTab, setSetupTab] = useState<Tab>('basic');
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [showStealthDetails, setShowStealthDetails] = useState(false);
  const [showInfra, setShowInfra] = useState(false);
  const [config, setConfig] = useState<Config>({
    bot_mode: 'queueit',
    event_id: '',
    target_url: '',
    proxies_per_worker: 0,
    click_selector: 'button:has-text("Add to Cart"), button:has-text("ซื้อเลย"), button:has-text("ใส่ตะกร้า")',
    refresh_mode: 'auto_refresh',
    refresh_interval: 1.0,
    action_after_click: 'notify',
    telegram_token: '',
    telegram_chat_id: '',
    redis_url: 'redis://redis:6379/0',
    proxies: [],
    profiles: [],
    browser_profiles: DEFAULT_BROWSER_PROFILES,
    queueit: DEFAULT_QUEUEIT,
    defense_demo: DEFAULT_DEFENSE_DEMO,
    ticket_count: 1,
    ticket_buyers: [''],
    ticket_priorities: ['VIP', 'GA', 'Standing'],
    membership_code: '',
  });
  const [savedConfig, setSavedConfig] = useState('');
  const [newProxy, setNewProxy] = useState('');
  const [newProfile, setNewProfile] = useState<Partial<Profile>>({
    fullname: '', email: '', password: '', phone: '', id_card: '', ticket_count: 1, ticket_buyers: []
  });
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
        data.profiles = data.profiles || [];
        data.queueit = mergeQueueIt(data.queueit);
        data.defense_demo = mergeDefenseDemo(data.defense_demo);
        data.ticket_count = data.ticket_count || 1;
        data.ticket_buyers = data.ticket_buyers || [''];
        data.ticket_priorities = data.ticket_priorities?.length ? data.ticket_priorities : ['VIP', 'GA', 'Standing'];
        data.membership_code = data.membership_code || '';
        // Ensure ticket_buyers array matches ticket_count
        while (data.ticket_buyers.length < data.ticket_count) {
          data.ticket_buyers.push('');
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
  const botMode = normalizeBotMode(config.bot_mode);
  const inputClass =
    'w-full px-4 py-3 bg-zinc-800 border border-zinc-700 rounded-lg text-white focus:border-emerald-500 focus:outline-none';

  const TtmTabLink = ({ label }: { label: string }) => (
    <button
      type="button"
      onClick={() => setSetupTab('ttm')}
      className="inline-flex items-center gap-1.5 text-sm font-medium text-emerald-400 hover:text-emerald-300 transition"
    >
      {label}
      <span aria-hidden>→</span>
    </button>
  );

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
        <TabButton name="proxies" label="🌐 Proxies" />
        <TabButton
          name="profiles"
          label={`👤 Buyers${config.profiles.length > 0 ? ` (${readyBuyers}/${config.profiles.length})` : ''}`}
        />
        <TabButton
          name="browser"
          label={`🛡️ Browser${config.browser_profiles.length > 0 ? ` (${config.browser_profiles.length})` : ''}`}
        />
        <TabButton name="ttm" label="🎫 TTM Purchase" />
      </div>

      {/* Content panel */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-4 sm:p-8 mb-8">

        {/* Basic */}
        {setupTab === 'basic' && (
          <div className="space-y-8">
            <div>
              <h2 className="text-2xl font-semibold text-white">Basic Settings</h2>
              <p className="text-zinc-400 text-sm mt-1">เลือกโหมดบอท แล้วกรอกเฉพาะฟิลด์ที่เกี่ยวข้อง</p>
            </div>

            {/* Mode categories + cards */}
            <div className="space-y-6">
              <p className="text-xs font-semibold uppercase tracking-wider text-zinc-500">โหมดบอท</p>
              {MODE_CATEGORIES.map((cat) => (
                <div key={cat.label} className="space-y-3">
                  <div className="flex items-baseline gap-2">
                    <span className="text-sm font-semibold text-zinc-200">{cat.label}</span>
                    <span className="text-xs text-zinc-500">{cat.hint}</span>
                  </div>
                  <div className="grid grid-cols-1 gap-3">
                    {cat.modes.map((mode) => {
                      const meta = BOT_MODE_META[mode];
                      const selected = botMode === mode;
                      return (
                        <button
                          key={mode}
                          type="button"
                          onClick={() => setConfig({ ...config, bot_mode: mode })}
                          className={`text-left rounded-xl border p-4 transition-all bg-gradient-to-br ${meta.accent} ${
                            selected
                              ? `border-zinc-600 ring-2 ${meta.ring} ring-offset-2 ring-offset-zinc-900`
                              : 'border-zinc-800 hover:border-zinc-600 bg-zinc-900/80'
                          }`}
                        >
                          <div className="flex items-start gap-3">
                            <span className="text-2xl" aria-hidden>{meta.icon}</span>
                            <div className="flex-1 min-w-0">
                              <div className="flex flex-wrap items-center gap-2 mb-1">
                                <span className="font-semibold text-white">{meta.title}</span>
                                {meta.badge && (
                                  <span className="px-2 py-0.5 rounded-md text-[10px] font-bold uppercase tracking-wide bg-zinc-800/80 text-zinc-400 border border-zinc-700">
                                    {meta.badge}
                                  </span>
                                )}
                                <code className="text-[10px] text-zinc-500 font-mono">{meta.short}</code>
                              </div>
                              <p className="text-sm text-zinc-400 leading-relaxed">{meta.description}</p>
                            </div>
                            {selected && (
                              <span className="flex-shrink-0 w-6 h-6 rounded-full bg-emerald-500 flex items-center justify-center text-white text-xs font-bold">
                                ✓
                              </span>
                            )}
                          </div>
                        </button>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>

            <ModeSettingsGuide
              activeMode={botMode}
              config={config}
              showAllModes={false}
              compact
            />

            {/* Mode-specific settings */}
            <div className="bg-zinc-800/40 border border-zinc-700/60 rounded-xl p-6 space-y-5">
              <h3 className="text-lg font-semibold text-zinc-100 flex items-center gap-2">
                <span>{BOT_MODE_META[botMode].icon}</span>
                ตั้งค่า — {BOT_MODE_META[botMode].title}
              </h3>

              {botMode === 'queueit' && (
                <>
                  <div className="flex flex-wrap items-center gap-2 py-2 px-3 rounded-lg bg-emerald-500/10 border border-emerald-500/25">
                    <span className="text-lg" aria-hidden>🎭</span>
                    <span className="text-xs font-semibold text-emerald-300">Playwright Stealth</span>
                    <span className="text-xs text-zinc-400 hidden sm:inline">·</span>
                    <span className="text-xs text-zinc-400">Fingerprint · Human mouse · ~28 stealth overrides</span>
                    <button
                      type="button"
                      onClick={() => setShowStealthDetails((v) => !v)}
                      className="ml-auto text-xs text-emerald-400 hover:text-emerald-300 font-medium"
                    >
                      {showStealthDetails ? 'ซ่อนรายละเอียด' : 'รายละเอียด'}
                    </button>
                  </div>
                  {showStealthDetails && (
                    <p className="text-xs text-zinc-500 leading-relaxed pl-1 border-l-2 border-emerald-800/60 ml-1">
                      ใช้ในโหมด queueit เท่านั้น: deterministic fingerprint ต่อ proxy, Bézier mouse/scroll,
                      stealth script ฉีดผ่าน init script + CDP ก่อนโหลดหน้า Queue-it
                    </p>
                  )}
                  <div>
                    <label className="block text-zinc-300 mb-2 font-medium">Target URL / ลิงก์คอนเสิร์ตหรือหน้าคิว</label>
                    <input
                      type="text"
                      value={config.target_url || ''}
                      onChange={(e) => setConfig({ ...config, target_url: e.target.value })}
                      className={inputClass}
                      placeholder="https://www.thaiticketmajor.com/concert/..."
                    />
                  </div>
                  <div>
                    <label className="block text-zinc-300 mb-2 font-medium">
                      Event ID <span className="text-zinc-500 font-normal">(ไม่บังคับ)</span>
                    </label>
                    <input
                      type="text"
                      value={config.event_id}
                      onChange={(e) => setConfig({ ...config, event_id: e.target.value })}
                      className={inputClass}
                      placeholder="ttm-bkk-blackpink-world-tour-2026"
                    />
                  </div>
                  <div className="rounded-lg bg-emerald-500/10 border border-emerald-500/30 px-4 py-3 text-sm text-zinc-300 space-y-2">
                    <p>
                      <strong className="text-emerald-400">Akamai:</strong> บอทติ๊กช่อง &quot;I&apos;m not a robot&quot; และกด Proceed
                      อัตโนมัติทุกครั้งที่เจอ (รวมหน้า login) — ค้นหาทั้งหน้าหลักและ iframe
                    </p>
                  </div>
                  <div className="rounded-lg bg-cyan-500/10 border border-cyan-500/30 px-4 py-3 text-sm text-zinc-300 space-y-2">
                    <p>
                      <strong className="text-cyan-400">การชำระเงินอัตโนมัติ (QRCode PromptPay):</strong> บอทจะทำการเลือกช่องทาง <strong>PromptPay</strong> ให้เองโดยอัตโนมัติ พร้อมทั้งครอปภาพ QR Code และข้อมูลราคาส่งตรงเข้า Telegram เพื่อให้ลูกค้าสแกนจ่ายได้ทันที โดยไม่ต้องเปิดลิงก์ให้เสียคิว
                    </p>
                  </div>
                  <div className="rounded-lg bg-zinc-900/60 border border-zinc-700/50 px-4 py-3 text-sm text-zinc-400 space-y-2">
                    <p>
                      หลังผ่านคิว บอทจะกดจอง / เลือกที่นั่ง / hold — ตั้งค่า selectors และ hold time ที่แท็บ{' '}
                      <TtmTabLink label="TTM Purchase" />
                    </p>
                    <p className="text-xs text-zinc-500">
                      แนะนำ: ตั้ง Proxies, Buyer Profiles และ Browser Profiles ก่อนเริ่มงาน
                    </p>
                  </div>
                </>
              )}

              {botMode === 'defense_demo' && (
                <>
                  <div>
                    <label className="block text-zinc-300 mb-2 font-medium">Sandbox URL</label>
                    <input
                      type="text"
                      value={config.target_url || ''}
                      onChange={(e) => setConfig({ ...config, target_url: e.target.value })}
                      className={inputClass}
                      placeholder={DEFAULT_DEFENSE_DEMO.default_url}
                    />
                    <p className="text-amber-400 text-xs mt-1.5">
                      ⚠️ บอททำงานใน Docker กรุณาใช้ <code className="text-amber-200">http://defense-gateway:8090/?demo=1</code> ห้ามใช้ localhost
                    </p>
                    <p className="text-zinc-500 text-xs mt-1.5">
                      ว่างเปล่า = ใช้ fallback{' '}
                      <code className="text-violet-300">{mergeDefenseDemo(config.defense_demo).default_url}</code>
                    </p>
                  </div>
                  <div className="rounded-lg bg-violet-500/10 border border-violet-500/30 px-4 py-3 text-sm text-zinc-400">
                    <p>
                      Poll ห้องรอ, Still here?, login sandbox — ตั้งที่แท็บ{' '}
                      <button
                        type="button"
                        onClick={() => setSetupTab('ttm')}
                        className="text-violet-300 hover:text-violet-200 font-medium"
                      >
                        TTM Purchase → Defense Demo
                      </button>
                    </p>
                  </div>
                </>
              )}

              <div className="pt-2 border-t border-zinc-700/50">
                <div className="mb-4 p-4 rounded-xl bg-blue-500/10 border border-blue-500/20">
                  <div className="text-blue-400 font-semibold text-sm mb-2">💡 Proxy Best Practice (โหมดใช้งานจริง)</div>
                  <ul className="text-zinc-400 text-xs space-y-1.5 pl-4 list-disc marker:text-blue-500/50">
                    <li><strong className="text-zinc-300">ใช้ Residential Sticky:</strong> TTM/Queue-it อิงตาม IP Session ห้ามใช้แบบ Rotating ทุก Request ให้ล็อค IP อย่างน้อย 15-30 นาที</li>
                    <li><strong className="text-zinc-300">แนะนำโปรโตคอล SOCKS5:</strong> ปลอดภัยกว่า ไร้ร่องรอย Header และรองรับ WebSockets ของ Queue-it ได้เสถียรที่สุด</li>
                    <li><strong className="text-zinc-300">ตั้งค่า Location TH:</strong> บอทต้องใช้ IP Thailand 🇹🇭 เท่านั้น ป้องกันการโดนบล็อคในขั้นตอน Payment</li>
                  </ul>
                </div>
                <label className="block text-zinc-300 mb-2 font-medium">
                  Proxies per worker <span className="text-zinc-500 font-normal text-sm">(0 = ไม่ rotator)</span>
                </label>
                <input
                  type="number"
                  min={0}
                  max={20}
                  value={config.proxies_per_worker ?? 0}
                  onChange={(e) =>
                    setConfig({ ...config, proxies_per_worker: parseInt(e.target.value, 10) || 0 })
                  }
                  className={inputClass}
                />
              </div>
            </div>

            {/* Infrastructure (collapsed) */}
            <div className="border border-zinc-700/50 rounded-xl overflow-hidden">
              <button
                type="button"
                onClick={() => setShowInfra(!showInfra)}
                className="w-full flex justify-between items-center px-5 py-3.5 bg-zinc-800/60 hover:bg-zinc-800 text-left"
              >
                <span className="text-sm font-medium text-zinc-400">⚙️ โครงสร้างระบบ (Redis)</span>
                <span className="text-zinc-500 text-xs">{showInfra ? '▲' : '▼'}</span>
              </button>
              {showInfra && (
                <div className="p-5 border-t border-zinc-800">
                  <label className="block text-zinc-300 mb-2 font-medium">Redis URL</label>
                  <input
                    type="text"
                    value={config.redis_url}
                    onChange={(e) => setConfig({ ...config, redis_url: e.target.value })}
                    className={inputClass}
                    placeholder="redis://redis:6379/0"
                  />
                </div>
              )}
            </div>
          </div>
        )}

        {/* Telegram */}
        {setupTab === 'telegram' && (
          <div className="space-y-6">
            <h2 className="text-2xl font-semibold mb-4">Telegram Settings</h2>
            <div className="rounded-lg bg-zinc-800/60 border border-zinc-700/50 px-4 py-3 text-sm text-zinc-400 leading-relaxed">
              {botMode === 'queueit' ? (
                <p>
                  โหมด <strong className="text-emerald-400">ThaiTicket</strong>: ส่งลิงก์หน้าชำระเงินอัตโนมัติเมื่อบอท hold
                  ที่นั่งสำเร็จ — ต้องใส่ Bot Token จริง (ไม่ใช่ YOUR_...) และกด Start กับ bot ในแชท
                </p>
              ) : (
                <p>
                  โหมด <strong className="text-violet-400">Defense Demo</strong>: แจ้งเตือนได้ถ้าตั้ง token (ไม่บังคับ)
                </p>
              )}
            </div>
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
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                {(['fullname', 'email', 'password', 'phone', 'id_card'] as const).map((key) => (
                  <input key={key} type={key === 'email' ? 'email' : key === 'password' ? 'password' : 'text'}
                    value={newProfile[key] || ''}
                    onChange={(e) => setNewProfile({ ...newProfile, [key]: e.target.value })}
                    className="px-4 py-2.5 bg-zinc-700 border border-zinc-600 rounded-lg text-white focus:border-emerald-500 focus:outline-none placeholder-zinc-500"
                    placeholder={{ fullname: 'ชื่อ-นามสกุล *', email: 'Email *', password: 'รหัสผ่าน *', phone: 'เบอร์โทร *', id_card: 'เลขบัตรประชาชน *' }[key]} />
                ))}
              </div>
              <button
                onClick={() => {
                  if (newProfile.fullname && newProfile.email && newProfile.password) {
                    setConfig({ ...config, profiles: [...config.profiles, newProfile as Profile] });
                    setNewProfile({ fullname: '', email: '', password: '', phone: '', id_card: '', ticket_count: 1, ticket_buyers: [] });
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
                      <div className="mt-3 pt-3 border-t border-zinc-700/50">
                        <div className="flex items-center gap-3 mb-2">
                          <label className="text-xs text-zinc-300">จำนวนตั๋ว</label>
                          <input type="number" min={1} max={10} value={profile.ticket_count || 1} onChange={(e) => {
                            const count = Math.max(1, Math.min(10, parseInt(e.target.value) || 1));
                            const buyers = [...(profile.ticket_buyers || [])];
                            while(buyers.length < count) buyers.push('');
                            buyers.length = count;
                            if (buyers[0] === '') buyers[0] = profile.fullname;
                            const newProfiles = [...config.profiles];
                            newProfiles[idx] = { ...profile, ticket_count: count, ticket_buyers: buyers };
                            setConfig({ ...config, profiles: newProfiles });
                          }} className="w-16 px-2 py-1 bg-zinc-900 border border-zinc-700 rounded text-sm text-center text-white" />
                        </div>
                        <div className="space-y-1.5">
                          {Array.from({ length: profile.ticket_count || 1 }).map((_, bIdx) => (
                            <div key={bIdx} className="flex items-center gap-2">
                              <span className="text-xs text-zinc-500 w-4">{bIdx + 1}.</span>
                              <input type="text" value={(profile.ticket_buyers || [])[bIdx] || ''} onChange={(e) => {
                                const buyers = [...(profile.ticket_buyers || [])];
                                buyers[bIdx] = e.target.value;
                                const newProfiles = [...config.profiles];
                                newProfiles[idx] = { ...profile, ticket_buyers: buyers };
                                setConfig({ ...config, profiles: newProfiles });
                              }} placeholder="ชื่อ-นามสกุล" className="flex-1 px-2 py-1 bg-zinc-900 border border-zinc-700 rounded text-xs text-white" />
                            </div>
                          ))}
                        </div>
                      </div>
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

        {/* TTM Purchase Flow */}
        {setupTab === 'ttm' && (
          <div className="space-y-8">
            <div>
              <h2 className="text-2xl font-semibold mb-1">TTM Purchase Flow</h2>
              <p className="text-zinc-400 text-sm">ตั้งค่า Queue-it browser flow: คิว → ที่นั่ง → hold</p>
            </div>

            <div className="bg-zinc-800/50 border border-zinc-700/50 rounded-xl p-5 space-y-4">
              <h3 className="font-semibold text-zinc-200">🎟️ ลำดับโซนที่นั่ง / ราคา (Ticket Priorities)</h3>
              <p className="text-sm text-zinc-400 leading-relaxed mb-3">
                กำหนดโซนหรือราคาที่ต้องการเรียงตามลำดับความสำคัญจากซ้ายไปขวา (โซนแรกสำคัญที่สุด) <br/>
                <span className="text-emerald-400 text-xs">🤖 บอทและระบบ AI จะพยายามคลิกเลือกโซนที่ว่างตามลำดับที่คุณระบุไว้นี้</span>
              </p>
              <TagListEditor
                label="ลำดับความสำคัญของโซน"
                placeholder="เช่น VIP, A1, 6500, Standing"
                tags={config.ticket_priorities || []}
                onChange={(tags) => setConfig({ ...config, ticket_priorities: tags })}
                color="emerald"
              />
            </div>

            <div className="bg-zinc-800/50 border border-zinc-700/50 rounded-xl p-5 space-y-4">
              <h3 className="font-semibold text-zinc-200">🔑 รหัสเมมเบอร์ชิพ (Membership Code)</h3>
              <p className="text-sm text-zinc-400 leading-relaxed">
                ใส่รหัสเมมเบอร์ชิพสำหรับการซื้อบัตรรอบ Pre-Sale (หากมี) บอทจะกรอกรหัสให้อัตโนมัติเมื่อผ่านคิวเข้าสู่หน้าใส่รหัสสมาชิก
              </p>
              <div>
                <input
                  type="text"
                  value={config.membership_code || ''}
                  onChange={(e) => setConfig({ ...config, membership_code: e.target.value })}
                  className={inputClass}
                  placeholder="เช่น TTM-MEMBER-9999"
                />
              </div>
            </div>

            <div className="bg-zinc-800/50 border border-zinc-700/50 rounded-xl p-5 space-y-4">
              <h3 className="font-semibold text-zinc-200">⚙️ Queue-it & Hold</h3>
              {config.bot_mode === 'defense_demo' && (
                <div className="bg-violet-500/10 border border-violet-500/30 rounded-lg p-4 space-y-3">
                  <h4 className="text-sm font-semibold text-violet-300">Defense Demo — Waiting Room</h4>
                  <p className="text-xs text-zinc-400 leading-relaxed">
                    Poll ห้องรอสูงสุด 15 ครั้ง ทุก 4–6 วินาที รอ progress bar 100% และตอบ Still here? อัตโนมัติ
                  </p>
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                    <div>
                      <label className="block text-zinc-400 text-xs mb-1">Default URL (fallback)</label>
                      <input type="text" value={mergeDefenseDemo(config.defense_demo).default_url}
                        onChange={(e) => setConfig(updateDefenseDemo(config, { default_url: e.target.value }))}
                        className="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white text-sm font-mono" />
                    </div>
                    <div>
                      <label className="block text-zinc-400 text-xs mb-1">Max poll attempts</label>
                      <input type="number" min={1} max={60}
                        value={mergeDefenseDemo(config.defense_demo).max_poll_attempts}
                        onChange={(e) => setConfig(updateDefenseDemo(config, { max_poll_attempts: parseInt(e.target.value, 10) || 15 }))}
                        className="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white text-sm" />
                    </div>
                    <div>
                      <label className="block text-zinc-400 text-xs mb-1">Poll interval (วินาที min–max)</label>
                      <div className="flex gap-2">
                        <input type="number" step={0.5} min={1}
                          value={mergeDefenseDemo(config.defense_demo).poll_interval_min}
                          onChange={(e) => setConfig(updateDefenseDemo(config, { poll_interval_min: parseFloat(e.target.value) || 4 }))}
                          className="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white text-sm" />
                        <input type="number" step={0.5} min={1}
                          value={mergeDefenseDemo(config.defense_demo).poll_interval_max}
                          onChange={(e) => setConfig(updateDefenseDemo(config, { poll_interval_max: parseFloat(e.target.value) || 6 }))}
                          className="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white text-sm" />
                      </div>
                    </div>
                    <div>
                      <label className="block text-zinc-400 text-xs mb-1">Sandbox login email (ว่าง = ใช้ profile)</label>
                      <input type="text" value={mergeDefenseDemo(config.defense_demo).login_email}
                        onChange={(e) => setConfig(updateDefenseDemo(config, { login_email: e.target.value }))}
                        className="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white text-sm" />
                    </div>
                    <div>
                      <label className="block text-zinc-400 text-xs mb-1">Sandbox login password</label>
                      <input type="text" value={mergeDefenseDemo(config.defense_demo).login_password}
                        onChange={(e) => setConfig(updateDefenseDemo(config, { login_password: e.target.value }))}
                        className="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white text-sm" />
                    </div>
                  </div>
                </div>
              )}
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
                <label className="flex items-center gap-3 px-4 py-3 bg-zinc-900 rounded-lg border border-zinc-700 cursor-pointer">
                  <input type="checkbox" checked={config.queueit.headless}
                    onChange={(e) => setConfig(updateQueueIt(config, { headless: e.target.checked }))}
                    className="w-4 h-4 accent-emerald-500" />
                  <span className="text-sm text-zinc-300">Headless</span>
                </label>
                <label className="flex items-center gap-3 px-4 py-3 bg-zinc-900 rounded-lg border border-zinc-700 cursor-pointer">
                  <input type="checkbox" checked={config.queueit.stop_on_first}
                    onChange={(e) => setConfig(updateQueueIt(config, { stop_on_first: e.target.checked }))}
                    className="w-4 h-4 accent-emerald-500" />
                  <span className="text-sm text-zinc-300">Stop เมื่อได้ที่นั่ง</span>
                </label>
                <label className="flex items-center gap-3 px-4 py-3 bg-zinc-900 rounded-lg border border-zinc-700 cursor-pointer">
                  <input type="checkbox" checked={config.queueit.manual_takeover || false}
                    onChange={(e) => setConfig(updateQueueIt(config, { manual_takeover: e.target.checked }))}
                    className="w-4 h-4 accent-emerald-500" />
                  <span className="text-sm text-zinc-300">Manual Takeover</span>
                </label>
                <div>
                  <label className="block text-zinc-400 text-xs mb-1">Hold (วินาที)</label>
                  <input type="number" min={60} value={config.queueit.hold_seconds}
                    onChange={(e) => setConfig(updateQueueIt(config, { hold_seconds: parseInt(e.target.value) || 600 }))}
                    className="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white text-sm" />
                </div>
                <div>
                  <label className="block text-zinc-400 text-xs mb-1">Timeout (นาที)</label>
                  <input type="number" min={5} value={config.queueit.max_minutes}
                    onChange={(e) => setConfig(updateQueueIt(config, { max_minutes: parseInt(e.target.value) || 120 }))}
                    className="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white text-sm" />
                </div>
              </div>
            </div>

            <div className="border border-zinc-700/50 rounded-xl overflow-hidden">
              <button type="button" onClick={() => setShowAdvanced(!showAdvanced)}
                className="w-full flex justify-between px-5 py-4 bg-zinc-800/80 hover:bg-zinc-800 text-left">
                <span className="font-medium text-zinc-300">🔧 Advanced — Selectors & Queue Texts</span>
                <span className="text-zinc-500">{showAdvanced ? '▲' : '▼'}</span>
              </button>
              {showAdvanced && (
                <div className="p-5 space-y-4 bg-zinc-900/50 border-t border-zinc-800">
                  {([['book_selector', 'ปุ่มซื้อบัตร'], ['seat_selector', 'ที่นั่ง (CSS)'], ['addtocart_selector', 'ใส่ตะกร้า']] as const).map(([key, label]) => (
                    <div key={key}>
                      <label className="block text-zinc-400 text-xs mb-1">{label}</label>
                      <input type="text" value={config.queueit[key]}
                        onChange={(e) => setConfig(updateQueueIt(config, { [key]: e.target.value }))}
                        className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white text-sm font-mono" />
                    </div>
                  ))}
                  <TagListEditor label="Join Queue" placeholder="Join the Queue"
                    tags={config.queueit.join_texts}
                    onChange={(tags) => setConfig(updateQueueIt(config, { join_texts: tags }))} />
                  <TagListEditor label="Still Here" placeholder="Yes, I'm here"
                    tags={config.queueit.stillhere_texts}
                    onChange={(tags) => setConfig(updateQueueIt(config, { stillhere_texts: tags }))} />
                </div>
              )}
            </div>
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
