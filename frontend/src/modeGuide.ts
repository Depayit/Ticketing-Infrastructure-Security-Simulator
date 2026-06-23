/** คู่มือการตั้งค่าแต่ละโหมด — ใช้ร่วมกันระหว่าง Dashboard และ Bot Setup */

export type BotMode = 'queueit' | 'defense_demo';

export type SetupTabId = 'basic' | 'telegram' | 'proxies' | 'profiles' | 'browser' | 'ticket';

export interface ModeSettingRow {
  name: string;
  tab: SetupTabId;
  required: boolean;
  description: string;
}

export interface ModeGuideEntry {
  icon: string;
  title: string;
  short: BotMode;
  badge: string;
  summary: string;
  flow: string[];
  settings: ModeSettingRow[];
  sharedNote: string;
}

export const BOT_MODE_META: Record<
  BotMode,
  { icon: string; title: string; short: BotMode; description: string; accent: string; ring: string; badge: string }
> = {
  queueit: {
    icon: '🎫',
    title: 'Ticket Purchase / Queue-it',
    short: 'queueit',
    description: 'คิวจริง → เลือกที่นั่ง → เลือกจ่ายด้วย PromptPay → ส่งรูป QR Code ไป Telegram ทันที',
    accent: 'from-emerald-500/20 to-cyan-500/10',
    ring: 'ring-emerald-500',
    badge: 'โปรดักชัน',
  },
  defense_demo: {
    icon: '🛡️',
    title: 'Defense Demo Sandbox',
    short: 'defense_demo',
    description: 'ทดสอบห้องรอ / anti-bot ใน sandbox ก่อนงานจริง',
    accent: 'from-violet-500/20 to-fuchsia-500/10',
    ring: 'ring-violet-500',
    badge: 'ทดสอบ',
  },
};

export const MODE_CATEGORIES: { label: string; hint: string; modes: BotMode[] }[] = [
  { label: 'จองบัตรจริง', hint: 'Ticket + Queue-it', modes: ['queueit'] },
  { label: 'ทดสอบระบบ', hint: 'Sandbox', modes: ['defense_demo'] },
];

export const SETUP_TAB_LABELS: Record<SetupTabId, string> = {
  basic: '📋 Basic',
  telegram: '📱 Telegram',
  proxies: '🌐 Proxies',
  profiles: '👤 Buyers',
  browser: '🛡️ Browser',
  Ticket: '🎫 Ticket Purchase',
};

export const MODE_GUIDE: Record<BotMode, ModeGuideEntry> = {
  queueit: {
    icon: '🎫',
    title: 'Ticket Purchase / Queue-it',
    short: 'queueit',
    badge: 'โปรดักชัน',
    summary:
      'บอทเปิด Chromium แบบ Stealth ผ่านคิว Queue-it จริง เลือกที่นั่ง ใส่ตะกร้า เข้าสู่หน้าชำระเงินด้วย PromptPay และส่งรูปภาพ QR Code พร้อมลิงก์ไป Telegram ทันทีเพื่อความรวดเร็วสูงสุด',
    flow: [
      'เปิด Target URL (หน้าคอนเสิร์ต)',
      'ผ่าน Akamai: ติ๊ก "I\'m not a robot" → กด Proceed (อัตโนมัติ)',
      'กดจอง / Join Queue / ตอบ Still here?',
      'ทะลุคิว → เลือกที่นั่ง → ใส่ตะกร้า',
      'ตรวจจับหน้าชำระเงิน → เลือก PromptPay (QR Code) อัตโนมัติ → ส่งรูป QR Code + ลิงก์ไป Telegram',
      'ถ้า stop_on_first: หยุด worker ทุกตัวเมื่อตัวแรกสำเร็จ',
    ],
    settings: [
      { name: 'Target URL', tab: 'basic', required: true, description: 'ลิงก์หน้าคอนเสิร์ตหรือหน้าเริ่มคิวบน Ticket Platform.com' },
      { name: 'Event ID', tab: 'basic', required: false, description: 'ใช้อ้างอิง / log (ไม่บังคับ)' },
      { name: 'Ticket Priorities', tab: 'ticket', required: false, description: 'ลำดับการเลือกโซน/ราคา (เช่น VIP > GA) ให้ AI ช่วยวิเคราะห์' },
      { name: 'Hold (วินาที)', tab: 'ticket', required: true, description: 'เวลาคงเบราว์เซอร์ไว้ให้คุณเข้าจ่าย (ค่าเริ่มต้น 600 = 10 นาที)' },
      { name: 'Timeout (นาที)', tab: 'ticket', required: true, description: 'หมดเวลาแล้ว worker จะออกจาก flow' },
      { name: 'Stop เมื่อได้ที่นั่ง', tab: 'ticket', required: false, description: 'เปิด = หยุดทุก worker เมื่อตัวใดตัวหนึ่ง hold สำเร็จ' },
      { name: 'Headless', tab: 'ticket', required: false, description: 'รันเบราว์เซอร์แบบไม่มี UI (แนะนำเปิดบน server)' },
      { name: 'Selectors (จอง/ที่นั่ง/ตะกร้า)', tab: 'ticket', required: false, description: 'ปรับเมื่อ Ticket เปลี่ยน DOM — อยู่ใน Advanced' },
      { name: 'Join Queue / Still here? texts', tab: 'ticket', required: false, description: 'ข้อความปุ่มในห้องรอ Queue-it' },
      { name: 'Proxies', tab: 'proxies', required: true, description: 'Residential ไทย — แนะนำ 1 proxy ต่อ 1–2 worker' },
      { name: 'Browser Profiles', tab: 'browser', required: true, description: 'Fingerprint ต่อ proxy — ควรมีจำนวน ≥ proxy ที่ใช้งาน' },
      { name: 'Bot Token + Chat ID', tab: 'telegram', required: true, description: 'ส่งภาพ QR Code และลิงก์ชำระเงินเมื่อ hold สำเร็จ (ต้องไม่ใช่ placeholder)' },
      { name: 'Buyer Profiles', tab: 'profiles', required: false, description: 'ไม่จำเป็นในโหมด hold-only (ใช้เมื่อต้องการกรอกฟอร์มเองภายหลัง)' },
      { name: 'Proxies per worker', tab: 'basic', required: false, description: '0 = ไม่ใช้ rotator, >0 = เช่า proxy จาก rotator' },
    ],
    sharedNote: 'แท็บ Telegram ใช้ร่วมทุกโหมด แต่โหมดนี้ส่งลิงก์ชำระเงินอัตโนมัติเมื่อถึงหน้าจ่าย',
  },
  defense_demo: {
    icon: '🛡️',
    title: 'Defense Demo Sandbox',
    short: 'defense_demo',
    badge: 'ทดสอบ',
    summary:
      'จำลอง funnel ห้องรอ / anti-bot ใน defense-gateway ก่อนลงงาน Ticket จริง — ใช้ทดสอบ stealth, proxy และการตอบ Still here?',
    flow: [
      'เปิด Sandbox URL (defense-gateway)',
      'ผ่าน Akamai Challenge (ติ๊กช่อง / Complete Challenge)',
      'Poll ห้องรอตาม max_poll_attempts',
      'ตอบ Still here? / login sandbox (ถ้าตั้ง)',
      'ผ่าน progress → หน้าซื้อ/ชำระใน sandbox',
    ],
    settings: [
      { name: 'Target URL', tab: 'basic', required: false, description: 'ถ้าว่าง ใช้ defense_demo.default_url' },
      { name: 'Default URL (fallback)', tab: 'ticket', required: true, description: 'เช่น http://defense-gateway:8090/?demo=1' },
      { name: 'Max poll attempts', tab: 'ticket', required: true, description: 'จำนวนครั้งสูงสุดที่ poll ห้องรอ' },
      { name: 'Poll interval (min–max วินาที)', tab: 'ticket', required: true, description: 'ช่วงหน่วงระหว่างแต่ละ poll' },
      { name: 'Sandbox login email/password', tab: 'ticket', required: false, description: 'ว่าง = ใช้ buyer profile แรก' },
      { name: 'Queue-it Hold / Timeout', tab: 'ticket', required: false, description: 'ใช้ค่า queueit เดียวกับโหมด Ticket (hold_seconds, max_minutes)' },
      { name: 'Proxies + Browser Profiles', tab: 'proxies', required: false, description: 'แนะนำเหมือนโหมดจริงเพื่อทดสอบ fingerprint' },
      { name: 'Telegram', tab: 'telegram', required: false, description: 'แจ้งเตือนเมื่อทดสอบสำเร็จ (ถ้าตั้ง token)' },
    ],
    sharedNote: 'ต้องรัน defense-demo stack (gateway, queue, payment) พร้อม worker',
  },
};

export function normalizeBotMode(raw: string | undefined): BotMode {
  if (raw === 'defense_demo') return raw;
  if (raw === 'ticket') return 'queueit';
  return 'queueit';
}

export interface ReadinessItem {
  label: string;
  ok: boolean;
  required: boolean;
  tab: SetupTabId;
  hint?: string;
}

export function evaluateModeReadiness(
  mode: BotMode,
  cfg: {
    target_url?: string;
    telegram_token?: string;
    telegram_chat_id?: string;
    proxies?: string[];
    profiles?: unknown[];
    browser_profiles?: unknown[];
    defense_demo?: { default_url?: string };
  }
): ReadinessItem[] {
  const tokenOk =
    !!cfg.telegram_token?.trim() &&
    !cfg.telegram_token.startsWith('YOUR_');
  const chatOk = !!cfg.telegram_chat_id?.trim();
  const tgOk = tokenOk && chatOk;
  const urlOk = !!cfg.target_url?.trim();
  const proxiesOk = (cfg.proxies?.length ?? 0) > 0;
  const browsersOk = (cfg.browser_profiles?.length ?? 0) > 0;
  const buyersOk = (cfg.profiles?.length ?? 0) > 0;
  const defenseUrlOk = !!cfg.defense_demo?.default_url?.trim();

  if (mode === 'defense_demo') {
    return [
      { label: 'Target URL หรือ Default URL', ok: urlOk || defenseUrlOk, required: true, tab: 'basic' },
      { label: 'Telegram', ok: tgOk, required: false, tab: 'telegram' },
      { label: 'Proxies', ok: proxiesOk, required: false, tab: 'proxies' },
    ];
  }
  return [
    { label: 'Target URL', ok: urlOk, required: true, tab: 'basic' },
    { label: 'Telegram Bot Token', ok: tokenOk, required: true, tab: 'telegram', hint: 'จาก @BotFather' },
    { label: 'Telegram Chat ID', ok: chatOk, required: true, tab: 'telegram' },
    { label: 'Proxies', ok: proxiesOk, required: true, tab: 'proxies', hint: 'แนะนำ residential ไทย' },
    { label: 'Browser Profiles', ok: browsersOk, required: true, tab: 'browser' },
    { label: 'Buyer Profiles', ok: buyersOk, required: false, tab: 'profiles' },
  ];
}
