import { useState } from 'react';
import {
  BotMode,
  BOT_MODE_META,
  MODE_GUIDE,
  MODE_CATEGORIES,
  SETUP_TAB_LABELS,
  normalizeBotMode,
  evaluateModeReadiness,
  type ReadinessItem,
} from '../modeGuide';

type ConfigSlice = Parameters<typeof evaluateModeReadiness>[1];

interface ModeSettingsGuideProps {
  /** โหมดที่เลือกอยู่ — ไฮไลต์ใน Dashboard */
  activeMode?: string;
  /** ข้อมูล config สำหรับเช็คความพร้อม (Dashboard) */
  config?: ConfigSlice;
  /** แสดงทุกโหมดหรือเฉพาะโหมดที่เลือก */
  showAllModes?: boolean;
  /** กะทัดรัดสำหรับฝังใน Setup */
  compact?: boolean;
  onGoToSetup?: () => void;
}

function ReadinessPills({ items }: { items: ReadinessItem[] }) {
  const required = items.filter((i) => i.required);
  const okCount = required.filter((i) => i.ok).length;
  return (
    <div className="flex flex-wrap items-center gap-2 mb-3">
      <span
        className={`text-xs font-semibold px-2.5 py-1 rounded-full border ${
          okCount === required.length
            ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/40'
            : 'bg-amber-500/15 text-amber-400 border-amber-500/40'
        }`}
      >
        พร้อมเริ่ม {okCount}/{required.length} (บังคับ)
      </span>
      {items.map((item) => (
        <span
          key={item.label}
          title={item.hint}
          className={`text-[11px] px-2 py-0.5 rounded-md border ${
            item.ok
              ? 'bg-emerald-950/50 text-emerald-400/90 border-emerald-800/50'
              : item.required
                ? 'bg-red-950/40 text-red-400/90 border-red-800/50'
                : 'bg-zinc-800/80 text-zinc-500 border-zinc-700'
          }`}
        >
          {item.ok ? '✓' : item.required ? '!' : '○'} {item.label}
        </span>
      ))}
    </div>
  );
}

export default function ModeSettingsGuide({
  activeMode,
  config,
  showAllModes = true,
  compact = false,
  onGoToSetup,
}: ModeSettingsGuideProps) {
  const normalizedActive = normalizeBotMode(activeMode);
  const [expanded, setExpanded] = useState<BotMode | null>(showAllModes ? null : normalizedActive);

  const modesToShow: BotMode[] = showAllModes
    ? MODE_CATEGORIES.flatMap((c) => c.modes)
    : [normalizedActive];

  return (
    <div className={compact ? 'space-y-4' : 'space-y-6'}>
      {!compact && (
        <div>
          <h2 className="text-2xl font-semibold text-white">การตั้งค่าแต่ละโหมด</h2>
          <p className="text-zinc-400 text-sm mt-1 leading-relaxed">
            สรุปฟิลด์ที่ต้องตั้งใน Bot Setup แยกตามโหมด — โหมดปัจจุบัน:{' '}
            <span className="text-emerald-400 font-medium">{BOT_MODE_META[normalizedActive].title}</span>
          </p>
        </div>
      )}

      <div className="space-y-4">
        {modesToShow.map((mode) => {
          const meta = BOT_MODE_META[mode];
          const guide = MODE_GUIDE[mode];
          const isActive = mode === normalizedActive;
          const isOpen = showAllModes ? expanded === mode : true;
          const readiness = config ? evaluateModeReadiness(mode, config) : null;

          return (
            <div
              key={mode}
              className={`rounded-2xl border overflow-hidden transition-colors ${
                isActive
                  ? 'border-emerald-600/50 bg-gradient-to-br from-emerald-500/5 to-zinc-900/80'
                  : 'border-zinc-800 bg-zinc-900/60'
              }`}
            >
              <button
                type="button"
                onClick={() => setExpanded(isOpen && showAllModes ? null : mode)}
                className={`w-full text-left px-5 py-4 flex items-start gap-3 ${
                  showAllModes ? 'hover:bg-zinc-800/50' : 'cursor-default'
                }`}
              >
                <span className="text-2xl" aria-hidden>
                  {meta.icon}
                </span>
                <div className="flex-1 min-w-0">
                  <div className="flex flex-wrap items-center gap-2 mb-1">
                    <span className="font-semibold text-white">{guide.title}</span>
                    <span className="text-[10px] uppercase tracking-wide px-2 py-0.5 rounded bg-zinc-800 text-zinc-400 border border-zinc-700">
                      {guide.badge}
                    </span>
                    <code className="text-[10px] text-zinc-500 font-mono">{guide.short}</code>
                    {isActive && (
                      <span className="text-[10px] font-bold text-emerald-400 uppercase">● โหมดปัจจุบัน</span>
                    )}
                  </div>
                  <p className="text-sm text-zinc-400 leading-relaxed">{guide.summary}</p>
                </div>
                {showAllModes && (
                  <span className="text-zinc-500 text-sm flex-shrink-0 mt-1">{isOpen ? '▲' : '▼'}</span>
                )}
              </button>

              {isOpen && (
                <div className="px-5 pb-5 pt-0 border-t border-zinc-800/80 space-y-4">
                  {readiness && isActive && <ReadinessPills items={readiness} />}

                  <div>
                    <p className="text-xs font-semibold uppercase tracking-wider text-zinc-500 mb-2">
                      ลำดับการทำงาน
                    </p>
                    <ol className="list-decimal list-inside text-sm text-zinc-300 space-y-1">
                      {guide.flow.map((step, i) => (
                        <li key={i} className="leading-relaxed">
                          {step}
                        </li>
                      ))}
                    </ol>
                  </div>

                  <div className="overflow-x-auto rounded-xl border border-zinc-800">
                    <table className="w-full text-sm text-left">
                      <thead>
                        <tr className="bg-zinc-800/80 text-zinc-400 text-xs uppercase tracking-wide">
                          <th className="px-3 py-2.5 font-medium">การตั้งค่า</th>
                          <th className="px-3 py-2.5 font-medium whitespace-nowrap">แท็บ</th>
                          <th className="px-3 py-2.5 font-medium w-16">บังคับ</th>
                          <th className="px-3 py-2.5 font-medium">คำอธิบาย</th>
                        </tr>
                      </thead>
                      <tbody>
                        {guide.settings.map((row) => (
                          <tr key={row.name} className="border-t border-zinc-800/80 hover:bg-zinc-800/30">
                            <td className="px-3 py-2.5 text-zinc-200 font-medium whitespace-nowrap">
                              {row.name}
                            </td>
                            <td className="px-3 py-2.5 text-cyan-400/90 text-xs whitespace-nowrap">
                              {SETUP_TAB_LABELS[row.tab]}
                            </td>
                            <td className="px-3 py-2.5 text-center">
                              {row.required ? (
                                <span className="text-red-400 font-bold">ใช่</span>
                              ) : (
                                <span className="text-zinc-500">—</span>
                              )}
                            </td>
                            <td className="px-3 py-2.5 text-zinc-400 text-xs leading-relaxed">
                              {row.description}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>

                  <p className="text-xs text-zinc-500 border-l-2 border-zinc-700 pl-3 leading-relaxed">
                    {guide.sharedNote}
                  </p>

                  {onGoToSetup && isActive && (
                    <button
                      type="button"
                      onClick={onGoToSetup}
                      className="text-sm font-medium text-emerald-400 hover:text-emerald-300 transition"
                    >
                      ไปตั้งค่าใน Bot Setup →
                    </button>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
