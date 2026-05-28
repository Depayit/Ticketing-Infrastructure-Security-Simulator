import { useState, useEffect } from 'react';

interface Status {
  active_workers: number;
  success_count: number;
  global_stop: boolean;
  is_running: boolean;
  live_logs: string[];
  active_proxies: number;
  dead_proxies: number;
  total_proxies: number;
  browser_profiles_count: number;
  buyer_profiles_count: number;
  // bot_mode removed (Playwright Stealth is the only mode)
  event_id?: string;
  target_url?: string;
  timestamp: string;
}

export default function Dashboard() {
  const [status, setStatus] = useState<Status>({
    active_workers: 0,
    success_count: 0,
    global_stop: false,
    is_running: false,
    live_logs: [],
    active_proxies: 0,
    dead_proxies: 0,
    total_proxies: 0,
    browser_profiles_count: 0,
    buyer_profiles_count: 0,
    event_id: '',
    target_url: '',
    timestamp: '',
  });
  const [connected, setConnected] = useState(false);

  const refreshStatus = () => {
    fetch('/api/status')
      .then((r) => r.json())
      .then(setStatus)
      .catch(console.error);
  };

  useEffect(() => {
    refreshStatus();
    const timer = setInterval(refreshStatus, 2000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    const ws = new WebSocket(`ws://${window.location.hostname}:8080/ws/logs`);

    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);
    ws.onmessage = (e) => {
      const data = JSON.parse(e.data);
      setStatus((prev) => ({ ...prev, live_logs: data.logs }));
    };

    return () => ws.close();
  }, []);

  const startAll = () => {
    fetch('/api/start', { method: 'POST' })
      .then(() => refreshStatus())
      .catch(console.error);
  };
  const stopAll = () => {
    fetch('/api/stop', { method: 'POST' })
      .then(() => refreshStatus())
      .catch(console.error);
  };


  return (
    <div className="max-w-7xl mx-auto">
      <div className="flex justify-between items-center mb-12">
        <div>
          <h1 className="text-5xl font-bold bg-gradient-to-r from-emerald-400 to-cyan-400 bg-clip-text text-transparent">
            Playwright Stealth Bot
          </h1>
          <div className="flex flex-col gap-1 mt-2">
            <p className="text-sm text-cyan-400 truncate max-w-2xl font-mono">
              🎯 Target: {status.target_url || status.event_id || 'ยังไม่ได้ตั้งค่า'}
            </p>
            <div className="text-[10px] text-emerald-400/70 font-mono">
              Advanced Fingerprint + Human Behavior + Akamai Sensor Emulation (GraphQL removed)
            </div>
            {status.timestamp && (
              <p className="text-xs text-zinc-500">
                Last sync: {new Date(status.timestamp).toLocaleTimeString('th-TH')}
              </p>
            )}
          </div>
        </div>
        <div
          className={`px-5 py-2.5 rounded-full text-sm font-medium flex items-center gap-2 ${
            connected ? 'bg-emerald-500/20 text-emerald-400' : 'bg-red-500/20 text-red-400'
          }`}
        >
          ● {connected ? 'Connected' : 'Disconnected'}
        </div>
      </div>

      {/* Mismatch Warning Alert */}
      {status.active_proxies > 0 && status.browser_profiles_count < status.active_proxies && (
        <div className="bg-amber-500/10 border border-amber-500/25 rounded-3xl p-6 mb-10 flex items-start gap-4">
          <span className="text-3xl leading-none">⚠️</span>
          <div>
            <h3 className="font-bold text-amber-300 text-lg mb-1">ลายนิ้วมือเบราว์เซอร์ไม่เพียงพอ (Fingerprint Mismatch)</h3>
            <p className="text-zinc-400 text-sm leading-relaxed">
              ระบบตรวจพบว่าคุณมี Proxy ที่ทำงานจริง <strong className="text-white font-mono">{status.active_proxies} ตัว</strong> แต่มี Browser Profile เพียง <strong className="text-white font-mono">{status.browser_profiles_count} โปรไฟล์</strong> 
              ในฝั่ง Worker จะทำการเปิดใช้งาน <strong className="text-emerald-400">"ระบบสุ่มนิ้วมือสำรองเฉพาะตัวอัตโนมัติ" (Dynamic Fingerprint Fallback)</strong> ให้แก่ Proxy ส่วนเกินเพื่อความปลอดภัยสูงสุดและป้องกันการแบน
            </p>
          </div>
        </div>
      )}

      {/* 5-Column Grid Layout */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-6 mb-10">
        <div className="bg-zinc-900 border border-zinc-800 rounded-3xl p-6 flex flex-col justify-between">
          <div>
            <p className="text-zinc-500 text-sm font-medium">Active Workers</p>
            <p className="text-5xl font-extrabold text-cyan-400 mt-3 font-mono">{status.active_workers}</p>
          </div>
          <div className="text-[11px] text-zinc-500 mt-2">Active daemon containers</div>
        </div>
        <div className="bg-zinc-900 border border-zinc-800 rounded-3xl p-6 flex flex-col justify-between">
          <div>
            <p className="text-zinc-500 text-sm font-medium">Success Orders</p>
            <p className="text-5xl font-extrabold text-emerald-400 mt-3 font-mono">{status.success_count}</p>
          </div>
          <div className="text-[11px] text-emerald-400/80 mt-2 font-medium">Auto-stopping triggered</div>
        </div>
        <div className="bg-zinc-900 border border-zinc-800 rounded-3xl p-6 flex flex-col justify-between">
          <div>
            <p className="text-zinc-500 text-sm font-medium">Proxies (Active / Total)</p>
            <p className="text-4xl font-extrabold text-emerald-400 mt-3 font-mono">
              {status.active_proxies}{' '}
              <span className="text-lg text-zinc-600 font-medium">/ {status.total_proxies}</span>
            </p>
          </div>
          {status.dead_proxies > 0 ? (
            <p className="text-[11px] text-red-400/90 mt-2 font-semibold">
              ⚠️ {status.dead_proxies} dead proxies filtered
            </p>
          ) : (
            <p className="text-[11px] text-zinc-500 mt-2">All proxies healthy</p>
          )}
        </div>
        <div className="bg-zinc-900 border border-zinc-800 rounded-3xl p-6 flex flex-col justify-between">
          <div>
            <p className="text-zinc-500 text-sm font-medium">Browser & Buyer Profiles</p>
            <div className="mt-3 space-y-1">
              <p className="text-xl font-bold text-indigo-400 font-mono">
                {status.browser_profiles_count} <span className="text-xs text-zinc-500 font-medium">Browsers</span>
              </p>
              <p className="text-xl font-bold text-purple-400 font-mono">
                {status.buyer_profiles_count} <span className="text-xs text-zinc-500 font-medium">Buyers (Cards)</span>
              </p>
            </div>
          </div>
          <div className="text-[11px] text-zinc-500 mt-2">Active configs in Redis</div>
        </div>
        <div className="bg-zinc-900 border border-zinc-800 rounded-3xl p-6 flex flex-col justify-between">
          <div>
            <p className="text-zinc-500 text-sm font-medium">System Status</p>
            {status.is_running ? (
              <p className="text-3xl font-extrabold mt-4 text-emerald-400 animate-pulse flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full bg-emerald-400"></span> RUNNING
              </p>
            ) : status.global_stop ? (
              <p className="text-3xl font-extrabold mt-4 text-red-500 flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full bg-red-500"></span> STOPPED
              </p>
            ) : (
              <p className="text-3xl font-extrabold mt-4 text-amber-400 flex items-center gap-2 animate-pulse">
                <span className="w-2.5 h-2.5 rounded-full bg-amber-400 animate-ping"></span> STANDBY
              </p>
            )}
          </div>
          <div className="text-[11px] text-zinc-500 mt-2">Press START to launch bots</div>
        </div>
      </div>

      <div className="flex gap-6 mb-12">
        <button
          onClick={startAll}
          className="flex-1 bg-emerald-600 hover:bg-emerald-500 py-6 text-xl font-semibold rounded-3xl transition"
        >
          START ALL WORKERS
        </button>
        <button
          onClick={stopAll}
          className="flex-1 bg-red-600 hover:bg-red-500 py-6 text-xl font-semibold rounded-3xl transition"
        >
          STOP ALL WORKERS
        </button>
      </div>

      <div className="bg-zinc-900 border border-zinc-800 rounded-3xl p-8">
        <h2 className="text-2xl font-semibold mb-6">Live Logs</h2>
        <pre className="bg-black p-6 rounded-2xl h-[420px] overflow-auto text-emerald-300 text-sm leading-relaxed font-mono">
          {status.live_logs.length === 0
            ? 'กำลังรอ log...'
            : status.live_logs.map((log, i) => <div key={i}>{log}</div>)}
        </pre>
      </div>
    </div>
  );
}
