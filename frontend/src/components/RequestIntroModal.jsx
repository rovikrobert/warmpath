import { useState } from 'react';
import { marketplace } from '../api/client';
import { trackEvent } from '../utils/analytics';

export default function RequestIntroModal({ listing, creditBalance, onClose, onSuccess }) {
  const [message, setMessage] = useState('');
  const [visibility, setVisibility] = useState('summary');
  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');

  const canAfford = creditBalance >= 20;

  const handleSubmit = async () => {
    setSending(true);
    setError('');
    try {
      await marketplace.requestIntro({
        marketplace_listing_id: listing.listing.id,
        message_to_holder: message || null,
        profile_visibility: visibility,
      });
      trackEvent('intro_requested');
      onSuccess();
    } catch (err) {
      setError(err.message);
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="w-full max-w-md rounded-xl bg-white shadow-xl">
        <div className="flex items-center justify-between border-b border-slate-200 px-6 py-4">
          <h2 className="text-lg font-semibold text-slate-900">Request Introduction</h2>
          <button onClick={onClose} className="text-xl leading-none text-slate-400 hover:text-slate-600">&times;</button>
        </div>

        <div className="space-y-4 px-6 py-5">
          {/* Listing summary */}
          <div className="rounded-lg bg-slate-50 p-3">
            <p className="text-sm font-medium text-slate-900">
              {listing.listing.role_level}
            </p>
            <p className="text-xs text-slate-500">
              {listing.listing.department_category && `${listing.listing.department_category} · `}
              {listing.listing.warm_score_range} connection
            </p>
            {listing.network_holder_reputation && (
              <p className="mt-1 text-xs text-slate-400">
                Holder reputation: {listing.network_holder_reputation.avg_rating?.toFixed(1) ?? '—'}
                {' '}({listing.network_holder_reputation.intros_facilitated} intros facilitated)
              </p>
            )}
          </div>

          {/* Message */}
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">Message to network holder (optional)</label>
            <textarea
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              rows={3}
              placeholder="Brief intro about yourself and why you'd be a good fit..."
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500"
            />
          </div>

          {/* Profile visibility */}
          <div>
            <label className="mb-2 block text-sm font-medium text-slate-700">Profile visibility</label>
            <div className="space-y-2">
              {[
                { value: 'minimal', label: 'Minimal', desc: 'Name and target role only' },
                { value: 'summary', label: 'Summary', desc: 'Name, role, experience summary' },
                { value: 'full', label: 'Full', desc: 'Complete profile and preferences' },
              ].map((opt) => (
                <label key={opt.value} className="flex items-center gap-2 text-sm">
                  <input
                    type="radio"
                    name="visibility"
                    value={opt.value}
                    checked={visibility === opt.value}
                    onChange={() => setVisibility(opt.value)}
                    className="h-4 w-4 border-slate-300 text-amber-500 focus:ring-amber-500"
                  />
                  <span className="text-slate-700">{opt.label}</span>
                  <span className="text-xs text-slate-400">&mdash; {opt.desc}</span>
                </label>
              ))}
            </div>
          </div>

          {/* Balance + warning */}
          <div className="flex items-center justify-between rounded-lg bg-amber-50 p-3">
            <span className="text-sm text-slate-700">Cost: 20 credits</span>
            <span className="text-sm font-medium text-amber-700">Balance: {creditBalance}</span>
          </div>

          {!canAfford && (
            <p className="rounded-md bg-red-50 p-2 text-sm text-red-600">
              Insufficient credits. You need at least 20 credits to request an intro.
            </p>
          )}

          {error && <p className="rounded-md bg-red-50 p-2 text-sm text-red-600">{error}</p>}

          <button
            onClick={handleSubmit}
            disabled={!canAfford || sending}
            className="w-full rounded-lg bg-amber-500 py-2.5 text-sm font-medium text-white hover:bg-amber-600 disabled:opacity-50"
          >
            {sending ? 'Sending...' : 'Request Intro — 20 credits'}
          </button>
        </div>
      </div>
    </div>
  );
}
