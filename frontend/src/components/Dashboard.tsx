import { useState, useEffect } from 'react';
import ModeSettingsGuide from './ModeSettingsGuide';
import { BOT_MODE_META, normalizeBotMode } from '../modeGuide';

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
  bot_mode?: string;
  event_id?: string;
  target_url?: string;
  timestamp: string;
  workers: Array<{
    instance_id: string;
    status: string;
    current_url: string;
  }>;
}

function LiveViewModal({ instanceId, onClose }: { instanceId: string; onClose: () => void }) {
  const [inputText, setInputText] = useState('');

  useEffect(() => {
    // Start stream
    fetch(`/api/live/${instanceId}/start`, { method: 'POST' });
    const timer = setInterval(() => {
      fetch(`/api/live/${instanceId}/start`, { method: 'POST' });
    }, 10000);
    
    return () => {
      clearInterval(timer);
      fetch(`/api/live/${instanceId}/stop`, { method: 'POST' });
    };
  }, [instanceId]);

  const handleImageClick = (e: React.MouseEvent<HTMLImageElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const clickX = e.clientX - rect.left;
    const clickY = e.clientY - rect.top;
    
    const elemWidth = rect.width;
    const elemHeight = rect.height;
    
    const naturalWidth = e.currentTarget.naturalWidth || 1920;
    const naturalHeight = e.currentTarget.naturalHeight || 1080;
    
    const scaleX = naturalWidth / elemWidth;
    const scaleY = naturalHeight / elemHeight;
    
    const mappedX = clickX * scaleX;
    const mappedY = clickY * scaleY;
    
    fetch(`/api/live/${instanceId}/control`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ type: 'click', x: mappedX, y: mappedY }),
    }).catch(console.error);
  };

  const sendType = () => {
    if (!inputText) return;
    fetch(`/api/live/${instanceId}/control`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ type: 'type', text: inputText }),
    }).catch(console.error);
    setInputText('');
  };

  const sendKeyPress = (key: string) => {
    fetch(`/api/live/${instanceId}/control`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ type: 'keypress', key }),
    }).catch(console.error);
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/90 flex items-center justify-center p-2 sm:p-4">
      <div className="bg-zinc-900 border border-zinc-700 rounded-2xl w-full max-w-[95vw] h-[95vh] overflow-hidden shadow-2xl relative flex flex-col">
        <div className="flex justify-between items-center p-3 sm:p-4 border-b border-zinc-800 bg-zinc-950 flex-none">
          <h3 className="font-semibold text-zinc-200 flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse"></span>
            Live View & Takeover (Worker: {instanceId})
          </h3>
          <div className="flex items-center gap-2">
            <span className="text-zinc-500 text-xs hidden md:inline">คลิกบนหน้าจอเพื่อควบคุมเมาส์บอท</span>
            <button onClick={onClose} className="text-zinc-400 hover:text-white px-3 py-1 rounded-lg bg-zinc-800 hover:bg-red-500 transition">ปิด (Close)</button>
          </div>
        </div>
        <div className="bg-black flex-1 flex items-center justify-center relative overflow-hidden p-2">
          <img 
            src={`/api/live/${instanceId}/stream`} 
            className="max-w-full max-h-[70vh] cursor-crosshair border border-zinc-800 rounded-lg shadow-lg select-none"
            alt="Live Stream"
            onClick={handleImageClick}
            onError={(e) => {
              (e.target as HTMLImageElement).style.display = 'none';
            }}
          />
          <div className="absolute inset-0 flex items-center justify-center -z-10 text-zinc-700 font-mono text-sm">
            Waiting for frames...
          </div>
        </div>
        <div className="p-3 sm:p-4 border-t border-zinc-800 bg-zinc-950 flex-none flex flex-col md:flex-row gap-3 items-center justify-between">
          <div className="flex items-center gap-2 w-full md:max-w-md">
            <input 
              type="text" 
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && sendType()}
              placeholder="พิมพ์ข้อความส่งให้บอท..."
              className="flex-1 px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white text-sm focus:border-emerald-500 focus:outline-none placeholder-zinc-500"
            />
            <button 
              onClick={sendType}
              className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-sm font-semibold transition"
            >
              ส่ง (Send)
            </button>
          </div>
          <div className="flex flex-wrap items-center gap-2 self-start md:self-auto">
            <span className="text-zinc-500 text-xs mr-1">ส่งคีย์บอร์ด:</span>
            <button 
              onClick={() => sendKeyPress('Enter')}
              className="px-3 py-2 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 rounded-lg text-xs font-semibold font-mono border border-zinc-700 transition"
            >
              ↵ Enter
            </button>
            <button 
              onClick={() => sendKeyPress('Tab')}
              className="px-3 py-2 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 rounded-lg text-xs font-semibold font-mono border border-zinc-700 transition"
            >
              ⇥ Tab
            </button>
            <button 
              onClick={() => sendKeyPress('Backspace')}
              className="px-3 py-2 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 rounded-lg text-xs font-semibold font-mono border border-zinc-700 transition"
            >
              ⌫ Backspace
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

interface ConfigSnapshot {
  bot_mode?: string;
  target_url?: string;
  telegram_token?: string;
  telegram_chat_id?: string;
  click_selector?: string;
  proxies?: string[];
  profiles?: unknown[];
  browser_profiles?: unknown[];
  defense_demo?: { default_url?: string };
}

export default function Dashboard({ onOpenSetup }: { onOpenSetup?: () => void }) {
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
    workers: [],
  });
  const [connected, setConnected] = useState(false);
  const [configSnap, setConfigSnap] = useState<ConfigSnapshot>({});
  const [liveViewInstance, setLiveViewInstance] = useState<string | null>(null);

  const refreshStatus = () => {
    fetch('/api/status')
      .then((r) => r.json())
      .then(setStatus)
      .catch(console.error);
    fetch('/api/config')
      .then((r) => r.json())
      .then(setConfigSnap)
      .catch(() => {});
  };

  const botMode = normalizeBotMode(status.bot_mode ?? configSnap.bot_mode);
  const modeMeta = BOT_MODE_META[botMode];

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

  useEffect(() => {
    if (liveViewInstance) {
      const worker = status.workers.find((w) => w.instance_id === liveViewInstance);
      if (!worker || worker.status === 'STOPPED') {
        setLiveViewInstance(null);
      }
    }
  }, [status.workers, liveViewInstance]);

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

  const toggleWorker = (instanceId: string, currentStatus: string) => {
    const isStopped = currentStatus === 'STOPPED';
    const endpoint = isStopped ? `/api/worker/${instanceId}/start` : `/api/worker/${instanceId}/stop`;
    fetch(endpoint, { method: 'POST' })
      .then(() => refreshStatus())
      .catch(console.error);
  };


  return (
    <div className="max-w-7xl mx-auto">
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-6 mb-8 md:mb-12">
        <div>
          <h1 className="text-3xl sm:text-5xl font-bold bg-gradient-to-r from-emerald-400 to-cyan-400 bg-clip-text text-transparent break-words">
            Playwright Stealth Bot
          </h1>
          <div className="flex flex-col gap-1 mt-2">
            <div className="flex flex-wrap items-center gap-2">
              <span
                className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold border ${
                  botMode === 'queueit'
                    ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/40'
                    : botMode === 'defense_demo'
                      ? 'bg-violet-500/15 text-violet-400 border-violet-500/40'
                      : 'bg-amber-500/15 text-amber-400 border-amber-500/40'
                }`}
              >
                {modeMeta.icon} โหมด: {modeMeta.title}
              </span>
              <code className="text-[10px] text-zinc-500 font-mono">{modeMeta.short}</code>
            </div>
            <p className="text-sm text-cyan-400 break-all max-w-full font-mono">
              🎯 Target: {status.target_url || status.event_id || 'ยังไม่ได้ตั้งค่า'}
            </p>
            <div className="text-[10px] text-emerald-400/70 font-mono">
              Advanced Fingerprint + Human Behavior (browser-only)
            </div>
            {status.timestamp && (
              <p className="text-xs text-zinc-500">
                Last sync: {new Date(status.timestamp).toLocaleTimeString('th-TH')}
              </p>
            )}
          </div>
        </div>
        <div
          className={`px-5 py-2.5 rounded-full text-sm font-medium flex items-center gap-2 self-start md:self-center ${
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
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4 sm:gap-6 mb-8 md:mb-10">
        <div className="bg-zinc-900 border border-zinc-800 rounded-3xl p-4 sm:p-6 flex flex-col justify-between">
          <div>
            <p className="text-zinc-500 text-xs sm:text-sm font-medium">Active Workers</p>
            <p className="text-3xl sm:text-5xl font-extrabold text-cyan-400 mt-2 sm:mt-3 font-mono">{status.active_workers}</p>
          </div>
          <div className="text-[10px] sm:text-[11px] text-zinc-500 mt-2">Active daemon containers</div>
        </div>
        <div className="bg-zinc-900 border border-zinc-800 rounded-3xl p-4 sm:p-6 flex flex-col justify-between">
          <div>
            <p className="text-zinc-500 text-xs sm:text-sm font-medium">Success Orders</p>
            <p className="text-3xl sm:text-5xl font-extrabold text-emerald-400 mt-2 sm:mt-3 font-mono">{status.success_count}</p>
          </div>
          <div className="text-[10px] sm:text-[11px] text-emerald-400/80 mt-2 font-medium">Auto-stopping triggered</div>
        </div>
        <div className="bg-zinc-900 border border-zinc-800 rounded-3xl p-4 sm:p-6 flex flex-col justify-between">
          <div>
            <p className="text-zinc-500 text-xs sm:text-sm font-medium">Proxies (Active / Total)</p>
            <p className="text-2xl sm:text-4xl font-extrabold text-emerald-400 mt-2 sm:mt-3 font-mono">
              {status.active_proxies}{' '}
              <span className="text-sm sm:text-lg text-zinc-600 font-medium">/ {status.total_proxies}</span>
            </p>
          </div>
          {status.dead_proxies > 0 ? (
            <p className="text-[10px] sm:text-[11px] text-red-400/90 mt-2 font-semibold">
              ⚠️ {status.dead_proxies} dead proxies
            </p>
          ) : (
            <p className="text-[10px] sm:text-[11px] text-zinc-500 mt-2">All proxies healthy</p>
          )}
        </div>
        <div className="bg-zinc-900 border border-zinc-800 rounded-3xl p-4 sm:p-6 flex flex-col justify-between">
          <div>
            <p className="text-zinc-500 text-xs sm:text-sm font-medium">Browser & Buyer Profiles</p>
            <div className="mt-2 sm:mt-3 space-y-1">
              <p className="text-lg sm:text-xl font-bold text-indigo-400 font-mono">
                {status.browser_profiles_count} <span className="text-[10px] sm:text-xs text-zinc-500 font-medium">Browsers</span>
              </p>
              <p className="text-lg sm:text-xl font-bold text-purple-400 font-mono">
                {status.buyer_profiles_count} <span className="text-[10px] sm:text-xs text-zinc-500 font-medium">Buyers (Cards)</span>
              </p>
            </div>
          </div>
          <div className="text-[10px] sm:text-[11px] text-zinc-500 mt-2">Active configs in Redis</div>
        </div>
        <div className="bg-zinc-900 border border-zinc-800 rounded-3xl p-4 sm:p-6 flex flex-col justify-between">
          <div>
            <p className="text-zinc-500 text-xs sm:text-sm font-medium">System Status</p>
            {status.is_running ? (
              <p className="text-xl sm:text-3xl font-extrabold mt-2 sm:mt-4 text-emerald-400 animate-pulse flex items-center gap-1.5">
                <span className="w-2 sm:w-2.5 h-2 sm:h-2.5 rounded-full bg-emerald-400"></span> RUNNING
              </p>
            ) : status.global_stop ? (
              <p className="text-xl sm:text-3xl font-extrabold mt-2 sm:mt-4 text-red-500 flex items-center gap-1.5">
                <span className="w-2 sm:w-2.5 h-2 sm:h-2.5 rounded-full bg-red-500"></span> STOPPED
              </p>
            ) : (
              <p className="text-xl sm:text-3xl font-extrabold mt-2 sm:mt-4 text-amber-400 flex items-center gap-1.5 animate-pulse">
                <span className="w-2 sm:w-2.5 h-2 sm:h-2.5 rounded-full bg-amber-400 animate-ping"></span> STANDBY
              </p>
            )}
          </div>
          <div className="text-[10px] sm:text-[11px] text-zinc-500 mt-2">Press START to launch bots</div>
        </div>
      </div>

      <div className="flex flex-col sm:flex-row gap-4 sm:gap-6 mb-8 md:mb-12">
        <button
          onClick={startAll}
          className="flex-1 bg-emerald-600 hover:bg-emerald-500 py-4 sm:py-6 text-lg sm:text-xl font-semibold rounded-3xl transition active:scale-[0.98]"
        >
          START ALL WORKERS
        </button>
        <button
          onClick={stopAll}
          className="flex-1 bg-red-600 hover:bg-red-500 py-4 sm:py-6 text-lg sm:text-xl font-semibold rounded-3xl transition active:scale-[0.98]"
        >
          STOP ALL WORKERS
        </button>
      </div>

      <div className="bg-zinc-900 border border-zinc-800 rounded-3xl p-4 sm:p-8 mb-8 md:mb-10">
        <ModeSettingsGuide
          activeMode={botMode}
          config={configSnap}
          showAllModes
          onGoToSetup={onOpenSetup}
        />
      </div>

      {status.workers && status.workers.length > 0 && (
        <div className="bg-zinc-900 border border-zinc-800 rounded-3xl p-4 sm:p-8 mb-8 md:mb-10">
          <h2 className="text-xl sm:text-2xl font-semibold mb-4 sm:mb-6">Active Workers</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
            {status.workers.map((w, idx) => (
              <div key={idx} className="bg-zinc-950 border border-zinc-800 rounded-2xl p-4 flex flex-col justify-between">
                <div>
                  <div className="flex justify-between items-center mb-2">
                    <span className="text-xs font-mono text-zinc-400">ID: {w.instance_id.substring(0, 8)}</span>
                    <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-400 font-semibold">{w.status}</span>
                  </div>
                  <div className="text-xs text-zinc-500 font-mono truncate mb-4" title={w.current_url}>{w.current_url || '-'}</div>
                </div>
                <div className="flex gap-2 mt-2">
                  <button 
                    onClick={() => toggleWorker(w.instance_id, w.status)}
                    className={`flex-1 py-2 text-xs font-medium rounded-lg transition text-white ${w.status === 'STOPPED' ? 'bg-emerald-600 hover:bg-emerald-500' : 'bg-red-600 hover:bg-red-500'}`}
                  >
                    {w.status === 'STOPPED' ? '▶ Start' : '⏹ Stop'}
                  </button>
                  <button 
                    onClick={() => setLiveViewInstance(w.instance_id)}
                    className="flex-1 py-2 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 hover:text-white rounded-lg text-xs font-medium transition flex items-center justify-center gap-1"
                  >
                    <span className="text-red-400">●</span> View
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="bg-zinc-900 border border-zinc-800 rounded-3xl p-4 sm:p-8">
        <h2 className="text-xl sm:text-2xl font-semibold mb-4 sm:mb-6">Live Logs</h2>
        <pre className="bg-black p-4 sm:p-6 rounded-2xl h-[350px] sm:h-[420px] overflow-auto text-emerald-300 text-xs sm:text-sm leading-relaxed font-mono">
          {status.live_logs.length === 0
            ? 'กำลังรอ log...'
            : status.live_logs.map((log, i) => <div key={i}>{log}</div>)}
        </pre>
      </div>

      {liveViewInstance && (
        <LiveViewModal instanceId={liveViewInstance} onClose={() => setLiveViewInstance(null)} />
      )}
    </div>
  );
}
