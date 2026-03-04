import { useState } from 'react';
import { useLocation } from 'react-router-dom';
import { feedback as feedbackApi } from '../api/client';

const ACTIONS = [
  { value: 1, label: 'This works well', icon: '\u{1F44D}', color: 'bg-success/10 text-success hover:bg-success/20' },
  { value: -1, label: 'Something is broken', icon: '\u{1F41B}', color: 'bg-destructive/10 text-destructive hover:bg-destructive/20' },
  { value: 0, label: 'Suggestion', icon: '\u{1F4A1}', color: 'bg-info/10 text-info hover:bg-info/20' },
];

export default function BetaFeedbackButton() {
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const [rating, setRating] = useState<number | null>(null);
  const [comment, setComment] = useState('');
  const [sending, setSending] = useState(false);
  const [done, setDone] = useState(false);

  const handleSubmit = async () => {
    if (rating === null) return;
    setSending(true);
    try {
      await feedbackApi.submit({
        feature: `beta_feedback:${location.pathname}`,
        rating,
        comment: [
          comment.trim(),
          `[page: ${location.pathname}]`,
          `[viewport: ${window.innerWidth}x${window.innerHeight}]`,
          `[ua: ${navigator.userAgent}]`,
          `[ts: ${new Date().toISOString()}]`,
        ].filter(Boolean).join('\n'),
      });
    } catch {
      // Non-critical
    } finally {
      setSending(false);
      setDone(true);
      setTimeout(() => {
        setOpen(false);
        setDone(false);
        setRating(null);
        setComment('');
      }, 1500);
    }
  };

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        aria-label="Give feedback"
        className="fixed bottom-20 right-6 z-50 flex h-12 w-12 items-center justify-center rounded-full bg-primary text-white shadow-lg hover:bg-primary/90 transition-colors lg:bottom-6"
      >
        <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth="2" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" d="M7.5 8.25h9m-9 3H12m-9.75 1.51c0 1.6 1.123 2.994 2.707 3.227 1.129.166 2.27.293 3.423.379.35.026.67.21.865.501L12 21l2.755-4.133a1.14 1.14 0 0 1 .865-.501 48.172 48.172 0 0 0 3.423-.379c1.584-.233 2.707-1.626 2.707-3.228V6.741c0-1.602-1.123-2.995-2.707-3.228A48.394 48.394 0 0 0 12 3c-2.392 0-4.744.175-7.043.513C3.373 3.746 2.25 5.14 2.25 6.741v6.018Z" />
        </svg>
      </button>
    );
  }

  return (
    <div
      className="fixed bottom-20 right-6 z-50 w-80 rounded-xl bg-card border border-border shadow-lg lg:bottom-6"
      role="dialog"
      aria-label="Beta feedback"
    >
      {done ? (
        <div className="px-5 py-4 text-center">
          <p className="text-sm font-medium text-secondary-foreground">Thanks for the feedback!</p>
        </div>
      ) : (
        <div className="px-5 py-4">
          <div className="mb-3 flex items-center justify-between">
            <div>
              <p className="text-sm font-semibold text-foreground">Beta Feedback</p>
              <p className="text-xs text-muted-foreground">on {location.pathname}</p>
            </div>
            <button
              onClick={() => setOpen(false)}
              aria-label="Close feedback"
              className="text-muted-foreground hover:text-secondary-foreground text-lg leading-none"
            >
              &times;
            </button>
          </div>

          <div className="mb-3 flex gap-2">
            {ACTIONS.map((a) => (
              <button
                key={a.value}
                onClick={() => setRating(a.value)}
                aria-label={a.label}
                aria-pressed={rating === a.value}
                className={`flex flex-1 flex-col items-center gap-1 rounded-lg px-2 py-2.5 text-xs font-medium transition ${
                  rating === a.value
                    ? `${a.color} ring-2 ring-offset-1 ring-offset-card ring-ring`
                    : `${a.color} opacity-70`
                }`}
              >
                <span className="text-lg">{a.icon}</span>
                {a.label}
              </button>
            ))}
          </div>

          {rating !== null && (
            <>
              <textarea
                value={comment}
                onChange={(e) => setComment(e.target.value)}
                placeholder="Tell us more... (optional)"
                aria-label="Feedback details"
                rows={3}
                className="mb-3 w-full resize-none rounded-lg border border-border bg-muted px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring"
              />
              <button
                onClick={handleSubmit}
                disabled={sending || rating === null}
                aria-label="Submit feedback"
                className="w-full rounded-lg bg-primary py-2 text-sm font-medium text-white hover:bg-primary/90 disabled:opacity-50"
              >
                {sending ? 'Sending...' : 'Submit Feedback'}
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
}
