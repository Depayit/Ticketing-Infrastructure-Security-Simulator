import { useState } from 'react';
import Dashboard from './components/Dashboard';
import Setup from './components/Setup';

function App() {
  const [tab, setTab] = useState<'dashboard' | 'setup'>('dashboard');

  return (
    <div className="min-h-screen bg-zinc-950">
      {/* Navigation */}
      <nav className="sticky top-0 z-50 bg-zinc-900 border-b border-zinc-800">
        <div className="max-w-7xl mx-auto px-8 py-4 flex gap-8">
          <button
            onClick={() => setTab('dashboard')}
            className={`text-lg font-semibold pb-2 border-b-2 transition ${
              tab === 'dashboard'
                ? 'border-emerald-400 text-emerald-400'
                : 'border-transparent text-zinc-400 hover:text-zinc-200'
            }`}
          >
            🎬 Dashboard
          </button>
          <button
            onClick={() => setTab('setup')}
            className={`text-lg font-semibold pb-2 border-b-2 transition ${
              tab === 'setup'
                ? 'border-emerald-400 text-emerald-400'
                : 'border-transparent text-zinc-400 hover:text-zinc-200'
            }`}
          >
            ⚙️ Bot Setup
          </button>
        </div>
      </nav>

      {/* Content */}
      <div className="p-8">
        {tab === 'dashboard' && <Dashboard />}
        {tab === 'setup' && <Setup />}
      </div>
    </div>
  );
}

export default App;
