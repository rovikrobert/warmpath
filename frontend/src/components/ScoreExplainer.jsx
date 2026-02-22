import { useState, useRef, useEffect } from 'react';

/**
 * Inline tooltip that explains what a score means.
 *
 * Usage:
 *   <ScoreExplainer title="Match Strength" body="Combines role relevance and warmth." />
 *
 * Renders a small "?" icon. Click to expand a floating tooltip card.
 */
export default function ScoreExplainer({ title, body, tiers, learnMoreHref }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  // Close on click outside
  useEffect(() => {
    if (!open) return;
    const handler = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open]);

  return (
    <span className="relative inline-block" ref={ref}>
      <button
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        aria-label={`What is ${title}?`}
        className="ml-1 inline-flex h-4 w-4 items-center justify-center rounded-full bg-slate-700 text-[10px] font-bold text-slate-400 hover:bg-slate-600"
      >
        ?
      </button>
      {open && (
        <div
          className="absolute left-0 z-20 mt-1 w-64 rounded-lg border border-slate-700/50 bg-slate-800 p-3 shadow-lg"
          role="tooltip"
        >
          <h4 className="mb-1 text-xs font-semibold text-slate-200">{title}</h4>
          <p className="text-xs text-slate-400">{body}</p>
          {tiers && tiers.length > 0 && (
            <div className="mt-2 space-y-1">
              {tiers.map((t) => (
                <div key={t.label} className="flex items-center gap-2">
                  <span className={`shrink-0 rounded-full px-1.5 py-0.5 text-[10px] font-medium ${t.color}`}>
                    {t.min != null ? `${t.min}+` : t.label}
                  </span>
                  <span className="text-[11px] text-slate-400">{t.desc || t.label}</span>
                </div>
              ))}
            </div>
          )}
          <div className="mt-2 flex items-center gap-3">
            <button
              onClick={() => setOpen(false)}
              aria-label={`Close ${title} explanation`}
              className="text-[11px] text-amber-400 hover:text-amber-300"
            >
              Got it
            </button>
            {learnMoreHref && (
              <a href={learnMoreHref} className="text-[11px] text-slate-400 hover:text-slate-300">
                Learn more
              </a>
            )}
          </div>
        </div>
      )}
    </span>
  );
}
