import { useState } from 'react';
import { feedback as feedbackApi } from '../api/client';

const RATINGS = [
  { value: -1, label: 'Not helpful', icon: '\u{1F44E}' },
  { value: 0, label: 'Neutral', icon: '\u{1F610}' },
  { value: 1, label: 'Helpful', icon: '\u{1F44D}' },
];

interface FeedbackModalProps {
  feature: string;
  resourceId?: string;
  onClose: () => void;
}

export default function FeedbackModal({ feature, resourceId, onClose }: FeedbackModalProps) {
  const [rating, setRating] = useState<number | null>(null);
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
      className="fixed bottom-6 right-6 z-50 w-72 rounded-xl bg-card border border-border shadow-lg"
      role="dialog"
      aria-label="Feedback"
    >
      {submitted ? (
        <div className="px-5 py-4 text-center">
          <p className="text-sm font-medium text-secondary-foreground">Thanks for the feedback!</p>
        </div>
      ) : (
        <div className="px-5 py-4">
          <div className="mb-3 flex items-center justify-between">
            <p className="text-sm font-medium text-foreground">How was this?</p>
            <button
              onClick={onClose}
              aria-label="Dismiss feedback"
              className="text-muted-foreground hover:text-secondary-foreground text-lg leading-none"
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
                    ? 'bg-primary/10 ring-2 ring-ring'
                    : 'bg-muted hover:bg-muted'
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
                className="mb-3 w-full resize-none rounded-lg border border-border bg-muted px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring"
              />
              <button
                onClick={handleSubmit}
                disabled={sending || rating === null}
                aria-label="Submit feedback"
                className="w-full rounded-lg bg-primary py-2 text-sm font-medium text-white hover:bg-primary/90 disabled:opacity-50"
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
