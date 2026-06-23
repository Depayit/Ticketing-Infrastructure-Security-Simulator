import { useState } from 'react';
import Dashboard from './components/Dashboard';
import Setup from './components/Setup';
import Manual from './components/Manual';
import TelegramDashboard from './components/TelegramDashboard';
import AiAssistant from './components/AiAssistant';

function App() {
  const [tab, setTab] = useState<'dashboard' | 'setup' | 'manual' | 'telegram' | 'ai'>('dashboard');

  return (
    <div className="min-h-screen bg-zinc-950">
      {/* Navigation */}
      <nav className="sticky top-0 z-50 bg-zinc-900 border-b border-zinc-800">
        <div className="max-w-7xl mx-auto px-4 sm:px-8 py-4 flex flex-wrap gap-x-6 gap-y-2 justify-center sm:justify-start">
          <button
            onClick={() => setTab('dashboard')}
            className={`text-sm sm:text-lg font-semibold pb-1.5 sm:pb-2 border-b-2 transition ${
              tab === 'dashboard'
                ? 'border-emerald-400 text-emerald-400'
                : 'border-transparent text-zinc-400 hover:text-zinc-200'
            }`}
          >
            🎬 Dashboard
          </button>
          <button
            onClick={() => setTab('ai')}
            className={`text-sm sm:text-lg font-semibold pb-1.5 sm:pb-2 border-b-2 transition ${
              tab === 'ai'
                ? 'border-emerald-400 text-emerald-400'
                : 'border-transparent text-zinc-400 hover:text-zinc-200'
            }`}
          >
            🤖 AI Controller
          </button>
          <button
            onClick={() => setTab('setup')}
            className={`text-sm sm:text-lg font-semibold pb-1.5 sm:pb-2 border-b-2 transition ${
              tab === 'setup'
                ? 'border-emerald-400 text-emerald-400'
                : 'border-transparent text-zinc-400 hover:text-zinc-200'
            }`}
          >
            ⚙️ Bot Setup
          </button>
          <button
            onClick={() => setTab('telegram')}
            className={`text-sm sm:text-lg font-semibold pb-1.5 sm:pb-2 border-b-2 transition ${
              tab === 'telegram'
                ? 'border-emerald-400 text-emerald-400'
                : 'border-transparent text-zinc-400 hover:text-zinc-200'
            }`}
          >
            📱 Telegram Bot
          </button>
          <button
            onClick={() => setTab('manual')}
            className={`text-sm sm:text-lg font-semibold pb-1.5 sm:pb-2 border-b-2 transition ${
              tab === 'manual'
                ? 'border-emerald-400 text-emerald-400'
                : 'border-transparent text-zinc-400 hover:text-zinc-200'
            }`}
          >
            📖 Manual
          </button>
        </div>
      </nav>

      {/* Content */}
      <div className="p-4 sm:p-8">
        {tab === 'dashboard' && <Dashboard onOpenSetup={() => setTab('setup')} />}
        {tab === 'ai' && <AiAssistant />}
        {tab === 'setup' && <Setup />}
        {tab === 'telegram' && <TelegramDashboard />}
        {tab === 'manual' && <Manual />}
      </div>
    </div>
  );
}

export default App;
