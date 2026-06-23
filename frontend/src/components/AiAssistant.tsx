import { useState, useEffect, useRef } from 'react';

interface WorkerStatus {
  instance_id: string;
  status: string;
  current_url: string;
  last_log: string;
  proxy: string;
  updated_at: string;
}

interface SystemStatus {
  active_workers: number;
  workers?: WorkerStatus[];
  success_count: number;
  global_stop: boolean;
  is_running: boolean;
  active_proxies: number;
  total_proxies: number;
  bot_mode?: string;
  event_id?: string;
  target_url?: string;
  refresh_interval?: number;
}

interface Message {
  role: 'user' | 'model';
  text: string;
  timestamp: Date;
  actions?: string[];
  image_url?: string;
}

export default function AiAssistant() {
  const [messages, setMessages] = useState<Message[]>([
    {
      role: 'model',
      text: 'สวัสดีครับ! ผมคือ AI Assistant ประจำระบบ TTM Stealth Bot คุณสามารถสอบถามสถานการณ์ของบอท หรือสั่งการทำงาน เช่น "เริ่มงานบอท", "หยุดบอท", หรือ "เปลี่ยน Target URL" ได้เลยครับ',
      timestamp: new Date(),
    },
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState<SystemStatus>({
    active_workers: 0,
    success_count: 0,
    global_stop: false,
    is_running: false,
    active_proxies: 0,
    total_proxies: 0,
  });

  const chatEndRef = useRef<HTMLDivElement>(null);

  // Poll system status for the live sidebar
  const fetchStatus = () => {
    fetch('/api/status')
      .then((r) => r.json())
      .then((data) => setStatus(data))
      .catch(console.error);
  };

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 2000);
    return () => clearInterval(interval);
  }, []);

  // Auto-scroll chat
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  const handleSend = async (textToSend?: string) => {
    const text = (textToSend || input).trim();
    if (!text) return;

    if (!textToSend) {
      setInput('');
    }

    const newMsg: Message = {
      role: 'user',
      text,
      timestamp: new Date(),
    };
    setMessages((prev) => [...prev, newMsg]);
    setLoading(true);

    try {
      const historyPayload = messages.map((m) => ({
        role: m.role,
        text: m.text,
      }));

      const res = await fetch('/api/ai/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, history: historyPayload }),
      });
      const data = await res.json();

      if (data.status === 'success') {
        setMessages((prev) => [
          ...prev,
          {
            role: 'model',
            text: data.response,
            timestamp: new Date(),
            actions: data.actions,
            image_url: data.image_url,
          },
        ]);
        // Trigger status refresh immediately to capture any actions taken
        fetchStatus();
      } else {
        setMessages((prev) => [
          ...prev,
          {
            role: 'model',
            text: `❌ เกิดข้อผิดพลาด: ${data.message || 'ไม่สามารถติดต่อ AI ได้'}`,
            timestamp: new Date(),
          },
        ]);
      }
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: 'model',
          text: `❌ ไม่สามารถติดต่อกับ Backend Server ได้: ${(err as Error).message}`,
          timestamp: new Date(),
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const getStatusColor = (statusText: string) => {
    const s = (statusText || '').toUpperCase();
    if (s === 'SUCCESS') return 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30';
    if (s === 'FAILED') return 'bg-rose-500/15 text-rose-400 border-rose-500/30';
    if (s === 'STANDBY') return 'bg-zinc-500/15 text-zinc-400 border-zinc-500/30';
    if (s === 'RUNNING') return 'bg-sky-500/15 text-sky-400 border-sky-500/30';
    if (s === 'QUEUING') return 'bg-amber-500/15 text-amber-400 border-amber-500/30';
    if (s === 'SOLVING_CHALLENGE') return 'bg-purple-500/15 text-purple-400 border-purple-500/30';
    if (s === 'SELECTING_SEAT') return 'bg-pink-500/15 text-pink-400 border-pink-500/30';
    if (s === 'ADDING_TO_CART') return 'bg-indigo-500/15 text-indigo-400 border-indigo-500/30';
    if (s === 'CHECKING_OUT') return 'bg-violet-500/15 text-violet-400 border-violet-500/30';
    return 'bg-cyan-500/15 text-cyan-400 border-cyan-500/30';
  };

  const quickPrompts = [
    { label: '📊 เช็คสถานะบอททั้งหมด', text: 'สรุปสถานการณ์และสถานะของบอททุกตัวในตอนนี้ให้ฟังหน่อย' },
    { label: '▶️ สั่งรันบอท', text: 'สั่งเริ่มทำงานบอททุกตัวเลย' },
    { label: '⏹️ หยุดรันบอท', text: 'สั่งหยุดทำงานบอททั้งหมด' },
    { label: '⚙️ เปลี่ยนเว็บเป้าหมาย', text: 'เปลี่ยน URL เป้าหมายเป็น http://defense-gateway:8090/ และรันบอทเลย' },
  ];

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 lg:gap-8 max-w-7xl mx-auto h-auto lg:h-[calc(100vh-140px)]">
      {/* LEFT PANEL: Chat Interface */}
      <div className="lg:col-span-8 flex flex-col bg-zinc-900/60 border border-zinc-800 rounded-3xl overflow-hidden backdrop-blur-xl h-[550px] sm:h-[650px] lg:h-full shadow-2xl">
        {/* Header */}
        <div className="px-4 sm:px-8 py-4 sm:py-5 border-b border-zinc-800 bg-zinc-900/80 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="text-3xl">🤖</span>
            <div>
              <h2 className="font-bold text-white text-lg">AI Orchestrator</h2>
              <p className="text-xs text-emerald-400 flex items-center gap-1.5 font-mono">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-ping"></span> Gemini 2.5 Flash Online
              </p>
            </div>
          </div>
          <div className="text-xs bg-zinc-800 text-zinc-400 px-3 py-1 rounded-full font-mono border border-zinc-700/50">
            Natural Language Control
          </div>
        </div>

        {/* Message Area */}
        <div className="flex-1 overflow-y-auto px-4 sm:px-8 py-4 sm:py-6 space-y-4 sm:space-y-6 scrollbar-thin">
          {messages.map((m, idx) => (
            <div
              key={idx}
              className={`flex gap-4 ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              {m.role !== 'user' && (
                <div className="w-10 h-10 rounded-2xl bg-gradient-to-tr from-cyan-500 to-indigo-500 flex items-center justify-center text-lg shadow-lg flex-shrink-0">
                  🤖
                </div>
              )}
              <div
                className={`max-w-[80%] rounded-2xl p-4 shadow-md ${
                  m.role === 'user'
                    ? 'bg-gradient-to-r from-emerald-600 to-teal-600 text-white rounded-tr-none'
                    : 'bg-zinc-800/80 border border-zinc-700/60 text-zinc-100 rounded-tl-none'
                }`}
              >
                <p className="text-sm leading-relaxed whitespace-pre-wrap">{m.text}</p>
                
                {m.image_url && (
                  <div className="mt-4 border border-zinc-700/50 rounded-xl overflow-hidden shadow-lg bg-zinc-900/50">
                    <img src={m.image_url} alt="Bot Screenshot" className="w-full h-auto object-contain max-h-[400px]" />
                  </div>
                )}
                
                {/* Visual Action Badge */}
                {m.actions && m.actions.length > 0 && (
                  <div className="mt-3 pt-3 border-t border-zinc-700/40 flex flex-wrap gap-2">
                    {m.actions.map((act, i) => (
                      <span
                        key={i}
                        className="inline-flex items-center gap-1 text-[10px] bg-emerald-400/10 text-emerald-300 px-2 py-0.5 rounded-md font-mono border border-emerald-400/20"
                      >
                        ⚡ Action: {act}
                      </span>
                    ))}
                  </div>
                )}
                
                <span className="block text-[9px] text-zinc-400/70 mt-1.5 text-right font-mono">
                  {m.timestamp.toLocaleTimeString('th-TH', { hour: '2-digit', minute: '2-digit' })}
                </span>
              </div>
              {m.role === 'user' && (
                <div className="w-10 h-10 rounded-2xl bg-zinc-800 border border-zinc-700 flex items-center justify-center text-lg flex-shrink-0">
                  👤
                </div>
              )}
            </div>
          ))}

          {loading && (
            <div className="flex gap-4 justify-start">
              <div className="w-10 h-10 rounded-2xl bg-gradient-to-tr from-cyan-500 to-indigo-500 flex items-center justify-center text-lg shadow-lg flex-shrink-0 animate-pulse">
                🤖
              </div>
              <div className="bg-zinc-800/80 border border-zinc-700/60 text-zinc-100 rounded-2xl rounded-tl-none p-4 w-32 shadow-md">
                <div className="flex space-x-1.5 justify-center items-center h-4">
                  <div className="h-2 w-2 bg-cyan-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></div>
                  <div className="h-2 w-2 bg-cyan-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></div>
                  <div className="h-2 w-2 bg-cyan-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></div>
                </div>
              </div>
            </div>
          )}
          <div ref={chatEndRef} />
        </div>

        {/* Quick Suggestion Chips */}
        <div className="px-6 py-3 border-t border-zinc-800/50 bg-zinc-900/30 flex gap-2 overflow-x-auto scrollbar-none">
          {quickPrompts.map((chip, i) => (
            <button
              key={i}
              onClick={() => handleSend(chip.text)}
              disabled={loading}
              className="text-xs text-zinc-300 bg-zinc-800/70 hover:bg-zinc-700 hover:text-white px-3 py-1.5 rounded-full border border-zinc-700/40 transition flex-shrink-0 font-medium disabled:opacity-50"
            >
              {chip.label}
            </button>
          ))}
        </div>

        {/* Chat input box */}
        <div className="p-4 sm:p-6 border-t border-zinc-800 bg-zinc-900/80">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleSend();
            }}
            className="flex gap-2 sm:gap-3"
          >
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              disabled={loading}
              placeholder="พิมพ์สั่งการบอท เช่น: 'เริ่มรันบอททั้งหมด'..."
              className="flex-1 bg-zinc-950 border border-zinc-800 focus:border-cyan-500 rounded-2xl px-3 sm:px-5 py-2.5 sm:py-4 text-xs sm:text-sm text-white focus:outline-none placeholder-zinc-500 transition shadow-inner font-sans"
            />
            <button
              type="submit"
              disabled={loading || !input.trim()}
              className="bg-cyan-600 hover:bg-cyan-500 text-white px-4 sm:px-6 py-2.5 sm:py-4 rounded-2xl transition text-xs sm:text-sm font-bold shadow-lg disabled:opacity-40 disabled:hover:bg-cyan-600 flex items-center justify-center whitespace-nowrap"
            >
              ส่งคำสั่ง
            </button>
          </form>
        </div>
      </div>

      {/* RIGHT PANEL: Live Status Dashboard */}
      <div className="lg:col-span-4 flex flex-col bg-zinc-900/60 border border-zinc-800 rounded-3xl overflow-hidden backdrop-blur-xl h-auto min-h-[400px] lg:h-full shadow-2xl">
        {/* System Settings Status Widget */}
        <div className="p-6 border-b border-zinc-800 bg-zinc-900/80">
          <h3 className="font-bold text-white text-md mb-4 flex items-center gap-2">
            ⚙️ การตั้งค่าระบบปัจจุบัน
          </h3>
          <div className="space-y-3 text-xs font-mono">
            <div className="flex justify-between py-1.5 border-b border-zinc-800/40">
              <span className="text-zinc-500">โหมดการทำงาน:</span>
              <span className="text-indigo-400 font-semibold uppercase">{status.bot_mode || 'queueit'}</span>
            </div>
            <div className="flex flex-col py-1.5 border-b border-zinc-800/40 gap-1">
              <span className="text-zinc-500">เป้าหมาย URL:</span>
              <span className="text-cyan-400 truncate max-w-full text-right" title={status.target_url}>
                {status.target_url || 'ยังไม่ได้ตั้งค่า'}
              </span>
            </div>
            {status.event_id && (
              <div className="flex justify-between py-1.5 border-b border-zinc-800/40">
                <span className="text-zinc-500">Event ID:</span>
                <span className="text-purple-400">{status.event_id}</span>
              </div>
            )}
            <div className="flex justify-between py-1.5 border-b border-zinc-800/40">
              <span className="text-zinc-500">ความถี่ในการ Refresh:</span>
              <span className="text-amber-400 font-semibold">{status.refresh_interval || 1.0}s</span>
            </div>
            <div className="flex justify-between py-1.5 border-b border-zinc-800/40">
              <span className="text-zinc-500">สถานะระบบ:</span>
              {status.is_running ? (
                <span className="text-emerald-400 font-bold flex items-center gap-1">🟢 RUNNING</span>
              ) : status.global_stop ? (
                <span className="text-rose-500 font-bold flex items-center gap-1">🔴 STOPPED</span>
              ) : (
                <span className="text-amber-400 font-bold flex items-center gap-1 animate-pulse">🟡 STANDBY</span>
              )}
            </div>
            <div className="flex justify-between">
              <span className="text-zinc-500">จำนวนบอทที่รันอยู่:</span>
              <span className="text-white font-bold">{status.active_workers} / 8</span>
            </div>
          </div>
        </div>

        {/* Individual Workers Status List */}
        <div className="flex-1 overflow-y-auto p-6 space-y-4 scrollbar-thin">
          <h3 className="font-bold text-white text-md mb-2 flex items-center gap-2">
            🤖 รายชื่อบอททั้งหมด ({status.active_workers} ตัว)
          </h3>
          
          {(!status.workers || status.workers.length === 0) ? (
            <div className="h-[250px] border border-dashed border-zinc-800 rounded-2xl flex flex-col items-center justify-center text-zinc-500 text-sm gap-2">
              <span>📭 ยังไม่มีบอทใดๆ ทำการเชื่อมต่อเข้ามา</span>
              <span className="text-xs text-zinc-600 font-mono">กรุณารัน docker-compose up หรือเริ่มบอท</span>
            </div>
          ) : (
            status.workers.map((wk) => (
              <div
                key={wk.instance_id}
                className="bg-zinc-950/80 border border-zinc-800 rounded-2xl p-4 shadow-sm hover:border-zinc-700/80 transition"
              >
                <div className="flex justify-between items-start mb-2">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-bold text-white font-mono">{wk.instance_id}</span>
                  </div>
                  <span
                    className={`text-[10px] px-2 py-0.5 rounded-full border font-semibold font-mono ${getStatusColor(
                      wk.status
                    )}`}
                  >
                    {wk.status}
                  </span>
                </div>
                
                <div className="space-y-1.5 text-[11px] font-mono mt-3">
                  <div className="flex justify-between">
                    <span className="text-zinc-500">IP Proxy:</span>
                    <span className="text-zinc-400 truncate max-w-[200px]" title={wk.proxy}>
                      {wk.proxy === 'direct' ? '🌐 Direct (No Proxy)' : wk.proxy.split('@').pop() || wk.proxy}
                    </span>
                  </div>
                  <div className="flex flex-col gap-0.5">
                    <span className="text-zinc-500">ตำแหน่ง URL ปัจจุบัน:</span>
                    <span className="text-cyan-400 truncate max-w-full font-mono text-[10px]" title={wk.current_url}>
                      {wk.current_url || 'N/A'}
                    </span>
                  </div>
                  <div className="flex flex-col gap-0.5 pt-1 border-t border-zinc-900 mt-2">
                    <span className="text-zinc-500">Log ล่าสุด:</span>
                    <span className="text-emerald-400/90 text-[10px] line-clamp-2 leading-relaxed bg-black/40 p-2 rounded-lg mt-1 border border-zinc-900 shadow-inner">
                      {wk.last_log || 'ไม่มีข้อความ log'}
                    </span>
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
