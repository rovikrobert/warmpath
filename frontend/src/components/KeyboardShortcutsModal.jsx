import { useEffect } from 'react';

const SHORTCUTS = [
  { keys: ['\u2318', 'K'], description: 'Command palette' },
  { keys: ['/'], description: 'Focus search' },
  { keys: ['N'], description: 'New (context-dependent)' },
  { keys: ['J'], description: 'Next item in list' },
  { keys: ['K'], description: 'Previous item in list' },
  { keys: ['\u21B5'], description: 'Open detail' },
  { keys: ['Esc'], description: 'Close / back' },
  { keys: ['?'], description: 'Show this help' },
];

export default function KeyboardShortcutsModal({ open, onClose }) {
  useEffect(() => {
    if (!open) return;
    const handler = (e) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50" role="dialog" aria-modal="true" aria-label="Keyboard shortcuts">
      <div className="fixed inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} aria-hidden="true" />
      <div className="relative mx-auto mt-[20vh] max-w-sm rounded-xl border border-slate-700/50 bg-slate-900 p-6 shadow-2xl">
        <h2 className="mb-4 text-base font-semibold text-slate-50">Keyboard Shortcuts</h2>
        <div className="space-y-2.5">
          {SHORTCUTS.map((s) => (
            <div key={s.description} className="flex items-center justify-between">
              <span className="text-sm text-slate-400">{s.description}</span>
              <div className="flex items-center gap-1">
                {s.keys.map((k) => (
                  <kbd key={k} className="rounded bg-slate-800 px-2 py-0.5 text-xs font-medium text-slate-300">
                    {k}
                  </kbd>
                ))}
              </div>
            </div>
          ))}
        </div>
        <button
          onClick={onClose}
          className="mt-5 w-full rounded-lg border border-slate-700/50 py-2 text-sm text-slate-400 hover:bg-slate-800"
        >
          Close
        </button>
      </div>
    </div>
  );
}
