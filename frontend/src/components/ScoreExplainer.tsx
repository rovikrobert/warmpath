import { useState, useRef, useEffect } from 'react';

/**
 * Inline tooltip that explains what a score means.
 *
 * Usage:
 *   <ScoreExplainer title="Match Strength" body="Combines role relevance and warmth." />
 *
 * Renders a small "?" icon. Click to expand a floating tooltip card.
 */
interface ScoreTier {
  label: string;
  color: string;
  min?: number;
  desc?: string;
}

interface ScoreExplainerProps {
  title: string;
  body: string;
  tiers?: ScoreTier[];
  learnMoreHref?: string;
}

export default function ScoreExplainer({ title, body, tiers, learnMoreHref }: ScoreExplainerProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLSpanElement>(null);

  // Close on click outside
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
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
        className="ml-1 inline-flex h-4 w-4 items-center justify-center rounded-full bg-muted text-[10px] font-bold text-muted-foreground hover:bg-muted/80"
      >
        ?
      </button>
      {open && (
        <div
          className="absolute left-0 z-20 mt-1 w-64 rounded-lg border border-border bg-muted p-3 shadow-lg"
          role="tooltip"
        >
          <h4 className="mb-1 text-xs font-semibold text-foreground">{title}</h4>
          <p className="text-xs text-muted-foreground">{body}</p>
          {tiers && tiers.length > 0 && (
            <div className="mt-2 space-y-1">
              {tiers.map((t) => (
                <div key={t.label} className="flex items-center gap-2">
                  <span className={`shrink-0 rounded-full px-1.5 py-0.5 text-[10px] font-medium ${t.color}`}>
                    {t.min != null ? `${t.min}+` : t.label}
                  </span>
                  <span className="text-[11px] text-muted-foreground">{t.desc || t.label}</span>
                </div>
              ))}
            </div>
          )}
          <div className="mt-2 flex items-center gap-3">
            <button
              onClick={() => setOpen(false)}
              aria-label={`Close ${title} explanation`}
              className="text-[11px] text-primary hover:text-primary"
            >
              Got it
            </button>
            {learnMoreHref && (
              <a href={learnMoreHref} className="text-[11px] text-muted-foreground hover:text-secondary-foreground">
                Learn more
              </a>
            )}
          </div>
        </div>
      )}
    </span>
  );
}
