import { useState } from 'react';
import { feedback as feedbackApi } from '../api/client';

const RATINGS = [
  { value: -1, label: 'Not helpful', icon: '\u{1F44E}' },
  { value: 0, label: 'Neutral', icon: '\u{1F610}' },
  { value: 1, label: 'Helpful', icon: '\u{1F44D}' },
];

export default function FeedbackModal({ feature, resourceId, onClose }) {
  const [rating, setRating] = useState(null);
  const [comment, setComment] = useState('');
  const [submitted, setSubmitted] = useState(false);
  const [sending, setSending] = useState(false);

  const handleSubmit = async () => {
    if (rating === null) return;
    setSending(true);
    try {
      await feedbackApi.submit({
        feature,
        resource_id: resourceId || undefined,
        rating,
        comment: comment.trim() || undefined,
      });
    } catch {
      // Non-critical — don't block user
    } finally {
      setSending(false);
      setSubmitted(true);
      setTimeout(() => onClose(), 1500);
    }
  };

  return (
    <div
      className="fixed bottom-6 right-6 z-50 w-72 rounded-xl bg-white shadow-lg ring-1 ring-slate-200"
      role="dialog"
      aria-label="Feedback"
    >
      {submitted ? (
        <div className="px-5 py-4 text-center">
          <p className="text-sm font-medium text-slate-700">Thanks for the feedback!</p>
        </div>
      ) : (
        <div className="px-5 py-4">
          <div className="mb-3 flex items-center justify-between">
            <p className="text-sm font-medium text-slate-700">How was this?</p>
            <button
              onClick={onClose}
              aria-label="Dismiss feedback"
              className="text-slate-400 hover:text-slate-600 text-lg leading-none"
            >
              &times;
            </button>
          </div>

          <div className="mb-3 flex justify-center gap-3">
            {RATINGS.map((r) => (
              <button
                key={r.value}
                onClick={() => setRating(r.value)}
                aria-label={r.label}
                aria-pressed={rating === r.value}
                className={`flex h-10 w-10 items-center justify-center rounded-lg text-lg transition ${
                  rating === r.value
                    ? 'bg-amber-100 ring-2 ring-amber-400'
                    : 'bg-slate-100 hover:bg-slate-200'
                }`}
              >
                {r.icon}
              </button>
            ))}
          </div>

          {rating !== null && (
            <>
              <textarea
                value={comment}
                onChange={(e) => setComment(e.target.value)}
                placeholder="Any details? (optional)"
                aria-label="Feedback comment"
                rows={2}
                className="mb-3 w-full resize-none rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500"
              />
              <button
                onClick={handleSubmit}
                disabled={sending}
                className="w-full rounded-lg bg-amber-500 py-2 text-sm font-medium text-white hover:bg-amber-600 disabled:opacity-50"
              >
                {sending ? 'Sending...' : 'Submit'}
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
}
