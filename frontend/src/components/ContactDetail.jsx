import { useEffect, useState } from 'react';
import { contacts as contactsApi } from '../api/client';
import { getWarmTier, getLikelihood, WARM_TIERS } from '../utils/scores';
import ScoreExplainer from './ScoreExplainer';

const RELATIONSHIP_TYPES = [
  { value: 'current_colleague', label: 'Current colleague' },
  { value: 'former_colleague', label: 'Former colleague' },
  { value: 'manager', label: 'Manager' },
  { value: 'alumni', label: 'Alumni' },
  { value: 'industry_peer', label: 'Industry peer' },
  { value: 'friend', label: 'Friend' },
  { value: 'mentor', label: 'Mentor' },
  { value: 'client', label: 'Client' },
  { value: 'vendor', label: 'Vendor / Supplier' },
  { value: 'investor', label: 'Investor' },
  { value: 'recruiter', label: 'Recruiter' },
];

const REL_BADGE_COLORS = {
  current_colleague: 'bg-blue-500/10 text-blue-400',
  former_colleague: 'bg-indigo-500/10 text-indigo-400',
  manager: 'bg-emerald-500/10 text-emerald-400',
  alumni: 'bg-purple-500/10 text-purple-400',
  industry_peer: 'bg-cyan-500/10 text-cyan-400',
  friend: 'bg-amber-500/10 text-amber-400',
  mentor: 'bg-teal-500/10 text-teal-400',
  client: 'bg-orange-500/10 text-orange-400',
  vendor: 'bg-lime-500/10 text-lime-400',
  investor: 'bg-rose-500/10 text-rose-400',
  recruiter: 'bg-slate-700/50 text-slate-400',
};

function ScoreBar({ score }) {
  const fillColor = score >= 70 ? 'bg-emerald-500' : score >= 40 ? 'bg-amber-500' : 'bg-slate-500';
  return (
    <div className="flex items-center gap-3">
      <div className="flex-1 h-2 rounded-full bg-slate-800 overflow-hidden">
        <div
          className={`h-full rounded-full ${fillColor} transition-all duration-500`}
          style={{ width: `${Math.min(100, Math.max(0, score))}%` }}
        />
      </div>
      <span className="text-2xl font-bold tabular-nums text-slate-50">{score}</span>
    </div>
  );
}

export default function ContactDetail({ contact, onClose, onContactUpdate, onError }) {
  const [detail, setDetail] = useState(contact);
  const [loading, setLoading] = useState(false);
  const [relType, setRelType] = useState(contact.relationship_type || '');
  const [relSaving, setRelSaving] = useState(false);

  // Fetch full detail on mount
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    contactsApi.get(contact.id).then((res) => {
      if (!cancelled) {
        setDetail(res.data || res);
        setRelType((res.data || res).relationship_type || '');
      }
    }).catch(() => {
      // Fall back to list data already in state
    }).finally(() => {
      if (!cancelled) setLoading(false);
    });
    return () => { cancelled = true; };
  }, [contact.id]);

  const handleRelChange = async (e) => {
    const val = e.target.value;
    const prevVal = relType;
    setRelType(val);
    setRelSaving(true);
    onContactUpdate?.(contact.id, { relationship_type: val || null }, true);
    try {
      await contactsApi.patch(contact.id, { relationship_type: val || null });
      setDetail((d) => ({ ...d, relationship_type: val || null }));
    } catch {
      setRelType(prevVal);
      onContactUpdate?.(contact.id, { relationship_type: prevVal || null }, false);
      onError?.('Failed to update relationship type');
    } finally {
      setRelSaving(false);
    }
  };

  const handleWarmOverride = async (value) => {
    const prev = detail.warm_sco[RESEND_KEY_REDACTED];
    setDetail((d) => ({ ...d, warm_sco[RESEND_KEY_REDACTED]: value, warm_score: value ?? d.warm_score }));
    onContactUpdate?.(contact.id, { warm_sco[RESEND_KEY_REDACTED]: value, warm_score: value ?? detail.warm_score }, true);
    try {
      await contactsApi.patch(contact.id, { warm_sco[RESEND_KEY_REDACTED]: value });
    } catch {
      setDetail((d) => ({ ...d, warm_sco[RESEND_KEY_REDACTED]: prev }));
      onContactUpdate?.(contact.id, { warm_sco[RESEND_KEY_REDACTED]: prev }, false);
      onError?.('Failed to update connection strength');
    }
  };

  const score = detail.warm_score ?? 0;
  const warmTier = getWarmTier(score);
  const likelihood = detail.referral_likelihood ? getLikelihood(detail.referral_likelihood) : null;
  const relLabel = RELATIONSHIP_TYPES.find((r) => r.value === detail.relationship_type)?.label;
  const relColor = REL_BADGE_COLORS[detail.relationship_type] || '';

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 space-y-6">
        {/* Header */}
        <div>
          <h3 className="text-lg font-semibold text-slate-50">{detail.full_name}</h3>
          <p className="text-sm text-slate-400">
            {detail.current_title && `${detail.current_title}`}
            {detail.current_title && detail.current_company && ' at '}
            {detail.current_company && detail.current_company}
          </p>
          {relLabel && (
            <span className={`mt-2 inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${relColor}`}>
              {relLabel}
            </span>
          )}
        </div>

        {/* Connection Score */}
        <div className="space-y-2">
          <p className="label-uppercase">
            Connection Score
            <ScoreExplainer
              title="Connection Score"
              body="How likely this person is to respond to your referral request. Based on recency, relationship strength, role relevance, and time at company."
              tiers={WARM_TIERS}
              learnMoreHref="/help/scores#connection-score"
            />
          </p>
          {loading ? (
            <div className="h-2 rounded-full bg-slate-800 animate-pulse" />
          ) : detail.warm_score == null ? (
            <p className="text-xs text-slate-500">Connection Score will appear after we analyze your connection data.</p>
          ) : (
            <>
              <ScoreBar score={score} />
              <div className="flex items-center gap-2">
                <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${warmTier.color}`}>
                  {warmTier.label}
                </span>
                {likelihood && (
                  <>
                    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${likelihood.color}`}>
                      {likelihood.label}
                    </span>
                    <ScoreExplainer
                      title="Referral Likelihood"
                      body="Our estimate of whether this person would actually refer you, based on relationship type, tenure, and past patterns."
                      learnMoreHref="/help/scores#referral-likelihood"
                    />
                  </>
                )}
              </div>
              {warmTier.desc && (
                <p className="text-xs text-slate-500">{warmTier.desc}</p>
              )}
              {/* Score breakdown if available */}
              {detail.sco[RESEND_KEY_REDACTED] && (
                <div className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                  {detail.sco[RESEND_KEY_REDACTED].recency != null && (
                    <div className="flex justify-between"><span className="text-slate-500">Recency (35%)</span><span className="text-slate-300">{detail.sco[RESEND_KEY_REDACTED].recency}</span></div>
                  )}
                  {detail.sco[RESEND_KEY_REDACTED].relationship != null && (
                    <div className="flex justify-between"><span className="text-slate-500">Relationship (30%)</span><span className="text-slate-300">{detail.sco[RESEND_KEY_REDACTED].relationship}</span></div>
                  )}
                  {detail.sco[RESEND_KEY_REDACTED].role_relevance != null && (
                    <div className="flex justify-between"><span className="text-slate-500">Role relevance (20%)</span><span className="text-slate-300">{detail.sco[RESEND_KEY_REDACTED].role_relevance}</span></div>
                  )}
                  {detail.sco[RESEND_KEY_REDACTED].tenure != null && (
                    <div className="flex justify-between"><span className="text-slate-500">Time at company (15%)</span><span className="text-slate-300">{detail.sco[RESEND_KEY_REDACTED].tenure}</span></div>
                  )}
                </div>
              )}
            </>
          )}
        </div>

        {/* Contact Info */}
        <div className="space-y-3">
          <p className="label-uppercase">Contact Info</p>
          <div className="space-y-2.5">
            {detail.current_company && (
              <div>
                <p className="text-xs text-slate-500">Company</p>
                <p className="text-sm text-slate-200">{detail.current_company}</p>
              </div>
            )}
            {detail.current_title && (
              <div>
                <p className="text-xs text-slate-500">Position</p>
                <p className="text-sm text-slate-200">{detail.current_title}</p>
              </div>
            )}
            {detail.location && (
              <div>
                <p className="text-xs text-slate-500">Location</p>
                <p className="text-sm text-slate-200">{detail.location}</p>
              </div>
            )}
            {detail.connected_on && (
              <div>
                <p className="text-xs text-slate-500">Connected since</p>
                <p className="text-sm text-slate-200">
                  {new Date(detail.connected_on).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
                </p>
              </div>
            )}
            {detail.email && (
              <div>
                <p className="text-xs text-slate-500">Email</p>
                <p className="text-sm text-slate-200">{detail.email}</p>
              </div>
            )}
            {detail.how_you_know && (
              <div>
                <p className="text-xs text-slate-500">How you know them</p>
                <p className="text-sm text-slate-200">{detail.how_you_know}</p>
              </div>
            )}
            {detail.source && (
              <div>
                <p className="text-xs text-slate-500">Source</p>
                <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${detail.source === 'manual' ? 'bg-amber-500/10 text-amber-400' : 'bg-slate-700/50 text-slate-400'}`}>
                  {detail.source === 'manual' ? 'Manual' : 'LinkedIn CSV'}
                </span>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Actions (sticky bottom) */}
      <div className="sticky bottom-0 -mx-6 border-t border-slate-700/50 bg-slate-900 px-6 py-4 mt-6 space-y-3">
        {/* Relationship type selector */}
        <div>
          <label htmlFor="slideover-rel-type" className="mb-1 block text-xs text-slate-500">
            {relType ? 'Relationship type' : 'Classify this contact'}
          </label>
          <select
            id="slideover-rel-type"
            value={relType}
            onChange={handleRelChange}
            disabled={relSaving}
            className="w-full rounded-lg border border-slate-700/50 bg-slate-800 px-3 py-2 text-sm text-slate-100 focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500 disabled:opacity-50"
          >
            <option value="">Unclassified</option>
            {RELATIONSHIP_TYPES.map((r) => (
              <option key={r.value} value={r.value}>{r.label}</option>
            ))}
          </select>
        </div>

        {/* Warm score override */}
        <div className="border-t border-slate-700/50 pt-3">
          <label className="mb-2 block text-xs text-slate-500">
            How close are you?
          </label>
          <div className="grid grid-cols-3 gap-1.5">
            {[
              { label: 'Cold', value: 10, color: 'text-slate-400 border-slate-600' },
              { label: 'Lukewarm', value: 30, color: 'text-blue-400 border-blue-500/30' },
              { label: 'Warm', value: 55, color: 'text-amber-400 border-amber-500/30' },
              { label: 'Strong', value: 75, color: 'text-emerald-400 border-emerald-500/30' },
              { label: 'Very Strong', value: 90, color: 'text-emerald-300 border-emerald-400/30' },
              { label: 'Auto', value: null, color: 'text-slate-500 border-slate-700' },
            ].map((opt) => (
              <button
                key={opt.label}
                type="button"
                onClick={() => handleWarmOverride(opt.value)}
                className={`rounded-md border px-2 py-1.5 text-xs font-medium transition ${
                  detail.warm_sco[RESEND_KEY_REDACTED] === opt.value
                    ? `${opt.color} bg-slate-800 ring-1 ring-current`
                    : 'border-slate-700/50 text-slate-500 hover:text-slate-300'
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
          {detail.warm_sco[RESEND_KEY_REDACTED] != null && (
            <p className="mt-1 text-xs text-slate-500">
              You've set this connection strength manually.
            </p>
          )}
        </div>

        <div className="flex gap-2">
          <button className="flex-1 rounded-lg bg-amber-500 py-2.5 text-sm font-medium text-white hover:bg-amber-400 transition-colors">
            Draft Intro Message
          </button>
          <button
            onClick={onClose}
            className="rounded-lg border border-slate-700/50 px-4 py-2.5 text-sm font-medium text-slate-400 hover:bg-slate-800 transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
