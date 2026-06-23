import { useState, useEffect, useRef } from 'react';

interface TelegramBot {
  id: string;
  name: string;
  token: string;
  chat_id: string;
  enabled: boolean;
}

interface BotStatus {
  name: string;
  status: 'running' | 'disabled' | 'error';
  message: string;
}

interface Config {
  telegram_token: string;
  telegram_chat_id: string;
  telegram_bots?: TelegramBot[];
  [key: string]: any;
}

export default function TelegramDashboard() {
  const [config, setConfig] = useState<Config>({
    telegram_token: '',
    telegram_chat_id: '',
    telegram_bots: [],
  });
  const [statuses, setStatuses] = useState<Record<string, BotStatus>>({});
  const [isLoading, setIsLoading] = useState(true);
  const [saveState, setSaveState] = useState<'idle' | 'saving' | 'success' | 'error'>('idle');
  const [saveError, setSaveError] = useState('');
  
  // Form State
  const [newBotName, setNewBotName] = useState('');
  const [newBotToken, setNewBotToken] = useState('');
  const [newBotChatId, setNewBotChatId] = useState('');
  const [formError, setFormError] = useState('');

  // Editing State
  const [editingBotId, setEditingBotId] = useState<string | null>(null);
  const [editBotName, setEditBotName] = useState('');
  const [editBotToken, setEditBotToken] = useState('');
  const [editBotChatId, setEditBotChatId] = useState('');

  // Testing Connection State
  const [testingBotId, setTestingBotId] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<{ botId: string; success: boolean; message: string } | null>(null);

  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const fetchConfigAndStatus = async () => {
    try {
      const [configRes, statusRes] = await Promise.all([
        fetch('/api/config'),
        fetch('/api/telegram/status')
      ]);
      if (configRes.ok) {
        const data = await configRes.json();
        // Fallback migration to telegram_bots list if empty
        if (!data.telegram_bots || data.telegram_bots.length === 0) {
          if (data.telegram_token && data.telegram_chat_id && !data.telegram_token.startsWith('YOUR_')) {
            data.telegram_bots = [{
              id: 'default',
              name: 'Default Bot',
              token: data.telegram_token,
              chat_id: data.telegram_chat_id,
              enabled: true
            }];
          } else {
            data.telegram_bots = [];
          }
        }
        setConfig(data);
      }
      if (statusRes.ok) {
        setStatuses(await statusRes.json());
      }
    } catch (e) {
      console.error('Error fetching configuration', e);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchConfigAndStatus();
    const interval = setInterval(async () => {
      try {
        const res = await fetch('/api/telegram/status');
        if (res.ok) {
          setStatuses(await res.json());
        }
      } catch (e) {}
    }, 4000);
    return () => clearInterval(interval);
  }, []);

  const saveConfigData = async (updatedConfig: Config) => {
    setSaveState('saving');
    setSaveError('');
    try {
      const res = await fetch('/api/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updatedConfig),
      });
      if (res.ok) {
        setConfig(updatedConfig);
        setSaveState('success');
        if (toastTimer.current) clearTimeout(toastTimer.current);
        toastTimer.current = setTimeout(() => setSaveState('idle'), 3000);
      } else {
        throw new Error(await res.text() || `HTTP ${res.status}`);
      }
    } catch (e: any) {
      setSaveError(e.message || 'เกิดข้อผิดพลาดในการบันทึกข้อมูล');
      setSaveState('error');
    }
  };

  const handleAddBot = (e: React.FormEvent) => {
    e.preventDefault();
    setFormError('');
    
    const token = newBotToken.trim();
    const chatId = newBotChatId.trim();
    const name = newBotName.trim() || 'Telegram Bot';

    if (!token || !chatId) {
      setFormError('กรุณากรอก Bot Token และ Chat ID ให้ครบถ้วน');
      return;
    }

    const newBot: TelegramBot = {
      id: `bot-${Date.now()}`,
      name,
      token,
      chat_id: chatId,
      enabled: true
    };

    const updatedConfig = {
      ...config,
      telegram_bots: [...(config.telegram_bots || []), newBot]
    };

    saveConfigData(updatedConfig);
    
    // Clear inputs
    setNewBotName('');
    setNewBotToken('');
    setNewBotChatId('');
  };

  const handleDeleteBot = (botId: string) => {
    if (!window.confirm('คุณต้องการลบบอทตัวนี้ใช่หรือไม่?')) return;

    const updatedConfig = {
      ...config,
      telegram_bots: (config.telegram_bots || []).filter(b => b.id !== botId)
    };

    saveConfigData(updatedConfig);
  };

  const handleToggleBot = (botId: string) => {
    const updatedConfig = {
      ...config,
      telegram_bots: (config.telegram_bots || []).map(b => 
        b.id === botId ? { ...b, enabled: !b.enabled } : b
      )
    };

    saveConfigData(updatedConfig);
  };

  const startEditBot = (bot: TelegramBot) => {
    setEditingBotId(bot.id);
    setEditBotName(bot.name);
    setEditBotToken(bot.token);
    setEditBotChatId(bot.chat_id);
  };

  const handleSaveEditBot = () => {
    if (!editBotToken.trim() || !editBotChatId.trim()) {
      alert('กรุณากรอก Bot Token และ Chat ID ให้ครบถ้วน');
      return;
    }

    const updatedConfig = {
      ...config,
      telegram_bots: (config.telegram_bots || []).map(b => 
        b.id === editingBotId 
          ? { ...b, name: editBotName.trim() || 'Telegram Bot', token: editBotToken.trim(), chat_id: editBotChatId.trim() } 
          : b
      )
    };

    saveConfigData(updatedConfig);
    setEditingBotId(null);
  };

  const testBotConnection = async (bot: TelegramBot) => {
    setTestingBotId(bot.id);
    setTestResult(null);
    try {
      const res = await fetch('/api/telegram/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token: bot.token, chat_id: bot.chat_id }),
      });
      const data = await res.json();
      if (res.ok && data.status === 'success') {
        setTestResult({
          botId: bot.id,
          success: true,
          message: 'ส่งข้อความทดสอบสำเร็จ! โปรดตรวจสอบในแอป Telegram ของคุณ'
        });
      } else {
        setTestResult({
          botId: bot.id,
          success: false,
          message: data.message || 'ส่งข้อความทดสอบไม่สำเร็จ โปรดตรวจสอบความถูกต้องของ Token/Chat ID'
        });
      }
    } catch (e: any) {
      setTestResult({
        botId: bot.id,
        success: false,
        message: e.message || 'เกิดข้อผิดพลาดในการเชื่อมต่อเครือข่าย'
      });
    } finally {
      setTestingBotId(null);
    }
  };

  const maskToken = (token: string) => {
    if (token.length <= 15) return token;
    return `${token.substring(0, 8)}...${token.substring(token.length - 8)}`;
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[300px]">
        <svg className="w-10 h-10 animate-spin text-emerald-400" fill="none" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
        </svg>
      </div>
    );
  }

  const bots = config.telegram_bots || [];

  return (
    <div className="max-w-6xl mx-auto">
      {/* Header */}
      <div className="flex items-start justify-between mb-8 gap-4 flex-wrap">
        <div>
          <h1 className="text-4xl font-bold bg-gradient-to-r from-emerald-400 to-cyan-400 bg-clip-text text-transparent">
            Telegram Dashboard
          </h1>
          <p className="text-zinc-400 text-sm mt-1">ควบคุมและจัดการบอทส่งแจ้งเตือน Telegram คอนโซล</p>
        </div>
        
        {/* Global Save Indicator */}
        {saveState !== 'idle' && (
          <div className="self-center">
            {saveState === 'saving' && (
              <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                <svg className="w-3 h-3 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
                </svg>
                กำลังอัปเดตระบบ...
              </span>
            )}
            {saveState === 'success' && (
              <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
                ● บันทึกและซิงก์สำเร็จ!
              </span>
            )}
            {saveState === 'error' && (
              <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold bg-red-500/15 text-red-400 border border-red-500/30">
                ⚠ ข้อผิดพลาด: {saveError}
              </span>
            )}
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        
        {/* Left 2 Columns: Bot List & Forms */}
        <div className="lg:col-span-2 space-y-8">
          
          {/* Active Bots List */}
          <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-4 sm:p-6">
            <h2 className="text-xl font-bold text-white mb-6 flex items-center gap-2">
              <span>🤖</span> บอทที่กำลังใช้งาน ({bots.length})
            </h2>

            {bots.length === 0 ? (
              <div className="text-center py-12 border border-dashed border-zinc-800 rounded-xl bg-zinc-950/40">
                <p className="text-zinc-500 text-sm">ยังไม่มีการตั้งค่า Telegram Bot</p>
                <p className="text-zinc-600 text-xs mt-1">กรอกข้อมูลที่แบบฟอร์มด้านล่างเพื่อเพิ่มบอทแจ้งเตือนตัวแรก</p>
              </div>
            ) : (
              <div className="space-y-4">
                {bots.map((bot) => {
                  const isEditing = editingBotId === bot.id;
                  const statusInfo = statuses[bot.id] || {
                    status: bot.enabled ? 'running' : 'disabled',
                    message: bot.enabled ? 'กำลังซิงก์...' : 'ปิดใช้งาน'
                  };

                  return (
                    <div key={bot.id} 
                      className={`border rounded-xl p-5 bg-zinc-950/40 transition duration-200 ${
                        isEditing ? 'border-emerald-500 bg-zinc-900' : 'border-zinc-800/80 hover:border-zinc-700'
                      }`}>
                      
                      {isEditing ? (
                        /* Editing Mode Form */
                        <div className="space-y-4">
                          <h3 className="text-sm font-semibold text-emerald-400">แก้ไขข้อมูลบอท</h3>
                          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                            <div>
                              <label className="block text-zinc-500 text-xs mb-1">ชื่อบอท</label>
                              <input type="text" value={editBotName}
                                onChange={(e) => setEditBotName(e.target.value)}
                                className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white text-sm focus:border-emerald-500 focus:outline-none" />
                            </div>
                            <div>
                              <label className="block text-zinc-500 text-xs mb-1">Bot Token</label>
                              <input type="password" value={editBotToken}
                                onChange={(e) => setEditBotToken(e.target.value)}
                                className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white text-sm focus:border-emerald-500 focus:outline-none" />
                            </div>
                            <div>
                              <label className="block text-zinc-500 text-xs mb-1">Chat ID</label>
                              <input type="text" value={editBotChatId}
                                onChange={(e) => setEditBotChatId(e.target.value)}
                                className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white text-sm focus:border-emerald-500 focus:outline-none" />
                            </div>
                          </div>
                          <div className="flex gap-2 justify-end">
                            <button onClick={() => setEditingBotId(null)}
                              className="px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 rounded-lg text-xs transition font-medium">
                              ยกเลิก
                            </button>
                            <button onClick={handleSaveEditBot}
                              className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-xs transition font-medium">
                              บันทึก
                            </button>
                          </div>
                        </div>
                      ) : (
                        /* Read-only Mode Card */
                        <div>
                          <div className="flex justify-between items-start gap-3 flex-wrap">
                            <div>
                              <div className="flex items-center gap-2">
                                <h3 className="font-bold text-white text-lg">{bot.name}</h3>
                                
                                {/* Status badge */}
                                {statusInfo.status === 'running' && (
                                  <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
                                    {statusInfo.message}
                                  </span>
                                )}
                                {statusInfo.status === 'error' && (
                                  <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-medium bg-red-500/10 text-red-400 border border-red-500/20 cursor-help"
                                    title={statusInfo.message}>
                                    <span className="w-1.5 h-1.5 rounded-full bg-red-500"></span>
                                    ข้อผิดพลาด
                                  </span>
                                )}
                                {statusInfo.status === 'disabled' && (
                                  <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-medium bg-zinc-800 text-zinc-400 border border-zinc-700">
                                    <span className="w-1.5 h-1.5 rounded-full bg-zinc-500"></span>
                                    ปิดใช้งาน
                                  </span>
                                )}
                              </div>
                              
                              {statusInfo.status === 'error' && (
                                <p className="text-red-400 text-xs mt-1 font-medium">{statusInfo.message}</p>
                              )}

                              <div className="mt-2.5 grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-1 text-xs font-mono">
                                <div className="text-zinc-500">
                                  Token: <span className="text-zinc-300">{maskToken(bot.token)}</span>
                                </div>
                                <div className="text-zinc-500">
                                  Chat ID: <span className="text-zinc-300">{bot.chat_id}</span>
                                </div>
                              </div>
                            </div>

                            {/* Bot Actions */}
                            <div className="flex items-center gap-2">
                              {/* Enable/Disable Toggle */}
                              <button onClick={() => handleToggleBot(bot.id)}
                                className={`px-2.5 py-1 rounded-lg text-xs font-medium transition ${
                                  bot.enabled 
                                    ? 'bg-zinc-800 hover:bg-zinc-700 text-emerald-400' 
                                    : 'bg-emerald-950/30 hover:bg-emerald-900/30 text-emerald-500'
                                }`}>
                                {bot.enabled ? '⏸ พักบอท' : '▶ เปิดบอท'}
                              </button>

                              {/* Edit Bot */}
                              <button onClick={() => startEditBot(bot)}
                                className="p-1.5 bg-zinc-800 hover:bg-zinc-700 rounded-lg text-zinc-400 hover:text-white transition"
                                title="แก้ไขข้อมูลบอท">
                                ✏️
                              </button>

                              {/* Delete Bot */}
                              <button onClick={() => handleDeleteBot(bot.id)}
                                className="p-1.5 bg-red-950/20 hover:bg-red-900/30 rounded-lg text-red-400 transition"
                                title="ลบบอท">
                                🗑️
                              </button>
                            </div>
                          </div>

                          {/* Test connection & results */}
                          <div className="mt-4 pt-3 border-t border-zinc-900/60 flex items-center gap-4 flex-wrap">
                            <button
                              disabled={testingBotId === bot.id}
                              onClick={() => testBotConnection(bot)}
                              className="px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 rounded-lg text-xs font-medium transition flex items-center gap-1.5 disabled:opacity-50">
                              {testingBotId === bot.id ? (
                                <>
                                  <svg className="w-3 h-3 animate-spin text-white" fill="none" viewBox="0 0 24 24">
                                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
                                  </svg>
                                  กำลังส่ง...
                                </>
                              ) : (
                                <>🔔 ทดสอบบอท (Test)</>
                              )}
                            </button>

                            {testResult && testResult.botId === bot.id && (
                              <span className={`text-xs ${testResult.success ? 'text-emerald-400' : 'text-red-400'}`}>
                                {testResult.success ? '✓' : '✗'} {testResult.message}
                              </span>
                            )}
                          </div>
                        </div>
                      )}

                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Add Bot Form */}
          <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-4 sm:p-6">
            <h2 className="text-xl font-bold text-white mb-4 flex items-center gap-2">
              <span>➕</span> เพิ่มบอทส่งแจ้งเตือนใหม่
            </h2>
            <form onSubmit={handleAddBot} className="space-y-4">
              {formError && (
                <div className="text-xs font-semibold text-red-400 bg-red-500/10 border border-red-500/25 p-3 rounded-lg">
                  ⚠ {formError}
                </div>
              )}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <div>
                  <label className="block text-zinc-400 text-xs mb-1 font-medium">ชื่อบอท (เช่น กลุ่มจองบัตร VIP)</label>
                  <input type="text" value={newBotName}
                    onChange={(e) => setNewBotName(e.target.value)}
                    placeholder="VIP Alerts"
                    className="w-full px-4 py-2.5 bg-zinc-800 border border-zinc-700 rounded-lg text-white text-sm focus:border-emerald-500 focus:outline-none" />
                </div>
                <div>
                  <label className="block text-zinc-400 text-xs mb-1 font-medium">Bot Token *</label>
                  <input type="password" value={newBotToken}
                    onChange={(e) => setNewBotToken(e.target.value)}
                    placeholder="123456789:ABCdef..."
                    className="w-full px-4 py-2.5 bg-zinc-800 border border-zinc-700 rounded-lg text-white text-sm focus:border-emerald-500 focus:outline-none" />
                </div>
                <div>
                  <label className="block text-zinc-400 text-xs mb-1 font-medium">Chat ID *</label>
                  <input type="text" value={newBotChatId}
                    onChange={(e) => setNewBotChatId(e.target.value)}
                    placeholder="-100123456789"
                    className="w-full px-4 py-2.5 bg-zinc-800 border border-zinc-700 rounded-lg text-white text-sm focus:border-emerald-500 focus:outline-none" />
                </div>
              </div>
              <div className="flex justify-end">
                <button type="submit"
                  className="px-6 py-2.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-sm font-semibold transition active:scale-[0.98]">
                  บันทึกและเปิดใช้งาน
                </button>
              </div>
            </form>
          </div>

        </div>

        {/* Right 1 Column: Setup Instructions */}
        <div className="space-y-8">
          
          <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-4 sm:p-6 space-y-6">
            <h2 className="text-xl font-bold text-white flex items-center gap-2">
              <span>📖</span> คู่มือสร้างบอท & การใช้งาน
            </h2>
            
            <div className="space-y-4 text-sm leading-relaxed text-zinc-400">
              <div>
                <h3 className="font-bold text-zinc-200 flex items-center gap-1.5">
                  <span className="w-5 h-5 rounded-full bg-zinc-800 text-zinc-300 text-xs flex items-center justify-center font-bold">1</span>
                  สร้าง Telegram Bot
                </h3>
                <p className="mt-1 pl-6">
                  เปิดแอป Telegram ค้นหาและเข้าไปคุยกับ <a href="https://t.me/BotFather" target="_blank" rel="noreferrer" className="text-emerald-400 hover:underline">@BotFather</a> จากนั้นพิมพ์คำสั่ง <code className="text-violet-300 font-mono bg-zinc-950 px-1 py-0.5 rounded">/newbot</code> เพื่อสร้างบอทของคุณ เมื่อสร้างเสร็จจะได้ <strong>HTTP API Token</strong>
                </p>
              </div>

              <div>
                <h3 className="font-bold text-zinc-200 flex items-center gap-1.5">
                  <span className="w-5 h-5 rounded-full bg-zinc-800 text-zinc-300 text-xs flex items-center justify-center font-bold">2</span>
                  ค้นหา Chat ID ของคุณ
                </h3>
                <p className="mt-1 pl-6">
                  กด Start คุยกับบอทตัวใหม่ของคุณ จากนั้นค้นหาแชท <a href="https://t.me/userinfobot" target="_blank" rel="noreferrer" className="text-emerald-400 hover:underline">@userinfobot</a> หรือส่งข้อความเข้าไปแล้วดึงไอดีผ่านบอท เพื่อรับรหัส <strong>Id</strong> (ซึ่งก็คือ Chat ID ของคุณ เป็นตัวเลข)
                </p>
              </div>

              <div>
                <h3 className="font-bold text-zinc-200 flex items-center gap-1.5">
                  <span className="w-5 h-5 rounded-full bg-zinc-800 text-zinc-300 text-xs flex items-center justify-center font-bold">3</span>
                  ใช้งานในกลุ่ม (Group Chat)
                </h3>
                <p className="mt-1 pl-6">
                  เชิญบอทของคุณเข้าไปยังกลุ่ม หรือแชลแนลของคุณ แล้วรับ <strong>Chat ID ของกลุ่ม</strong> (ไอดีกลุ่มมักจะมีเครื่องหมายติดลบ เช่น <code className="text-violet-300 font-mono bg-zinc-950 px-1.5 py-0.5 rounded">-100xxxxxxxxx</code>)
                </p>
              </div>

              <div>
                <h3 className="font-bold text-zinc-200 flex items-center gap-1.5">
                  <span className="w-5 h-5 rounded-full bg-zinc-800 text-zinc-300 text-xs flex items-center justify-center font-bold">4</span>
                  สิทธิ์การควบคุมระบบบอท
                </h3>
                <p className="mt-1 pl-6">
                  คุณสามารถควบคุมเปิดปิดการจองบัตร (Start/Stop Workers) ผ่านบอทได้ โดยการส่งข้อความ <code className="text-violet-300 font-mono bg-zinc-950 px-1 py-0.5 rounded">/start</code> หาตัวบอทในแชทที่มีการกรอก Chat ID ไว้เท่านั้น (จะบล็อกแชทอื่นที่ไม่ได้รับอนุญาต)
                </p>
              </div>
            </div>
            
            <div className="pt-4 border-t border-zinc-800/80 bg-zinc-950/20 p-4 rounded-xl text-xs text-zinc-500 leading-normal">
              📌 <strong>Tips:</strong> บอททำงานประสานงานบนระบบคิว Redis หากคุณเปลี่ยนหรือแก้ไข Token ระบบหลังบ้านจะเชื่อมต่อและรีสตาร์ทตัวรับข้อมูล (Long Polling Listener) ของบอทตัวนั้นแบบเรียลไทม์ภายใน 3 วินาทีทันที
            </div>
          </div>
          
        </div>

      </div>
    </div>
  );
}
