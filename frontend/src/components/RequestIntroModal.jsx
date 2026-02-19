import { useState } from 'react';
import { marketplace } from '../api/client';
import { trackEvent } from '../utils/analytics';
import Modal from './ui/Modal';
import Button from './ui/Button';

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
    <Modal open onClose={onClose} title="Request Introduction" maxWidth="max-w-md">
      <div className="space-y-4">
        {/* Listing summary */}
        <div className="rounded-lg bg-slate-800/50 p-3">
          <p className="text-sm font-medium text-slate-50">
            {listing.listing.role_level}
          </p>
          <p className="text-xs text-slate-400">
            {listing.listing.department_category && `${listing.listing.department_category} · `}
            {listing.listing.warm_sco[RESEND_KEY_REDACTED]} connection
          </p>
          {listing.network_holder_reputation && (
            <p className="mt-1 text-xs text-slate-500">
              Holder reputation: {listing.network_holder_reputation.avg_rating?.toFixed(1) ?? '—'}
              {' '}({listing.network_holder_reputation.intros_facilitated} intros facilitated)
            </p>
          )}
        </div>

        {/* Message */}
        <div>
          <label className="mb-1 block text-sm font-medium text-slate-300">Message to connection owner (optional)</label>
          <textarea
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            rows={3}
            placeholder="Brief intro about yourself and why you'd be a good fit..."
            className="w-full rounded-lg border border-slate-700/50 bg-slate-800 px-3 py-2 text-sm text-slate-100 placeholder-slate-500 focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500"
          />
        </div>

        {/* Profile visibility */}
        <div>
          <label className="mb-2 block text-sm font-medium text-slate-300">Profile visibility</label>
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
                  className="h-4 w-4 border-slate-600 text-amber-500 focus:ring-amber-500"
                />
                <span className="text-slate-200">{opt.label}</span>
                <span className="text-xs text-slate-500">&mdash; {opt.desc}</span>
              </label>
            ))}
          </div>
        </div>

        {/* Balance + warning */}
        <div className="flex items-center justify-between rounded-lg bg-amber-500/10 p-3">
          <span className="text-sm text-slate-300">Cost: 20 credits</span>
          <span className="text-sm font-medium text-amber-400">Balance: {creditBalance}</span>
        </div>

        {!canAfford && (
          <p className="rounded-md bg-red-500/10 p-2 text-sm text-red-400">
            Insufficient credits. You need at least 20 credits to request an intro.
          </p>
        )}

        {error && <p className="rounded-md bg-red-500/10 p-2 text-sm text-red-400">{error}</p>}

        <Button
          onClick={handleSubmit}
          disabled={!canAfford || sending}
          loading={sending}
          className="w-full"
        >
          Request Intro — 20 credits
        </Button>
      </div>
    </Modal>
  );
}
