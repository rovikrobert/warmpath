import { useEffect, useState } from 'react';
import { contacts as contactsApi, matches as matchesApi } from '../api/client';
import { getWarmTier, getLikelihood, WARM_TIERS } from '../utils/scores';
import ScoreExplainer from './ScoreExplainer';
import Modal from './ui/Modal';

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
  friend: 'bg-primary/10 text-primary',
  mentor: 'bg-teal-500/10 text-teal-400',
  client: 'bg-orange-500/10 text-orange-400',
  vendor: 'bg-lime-500/10 text-lime-400',
  investor: 'bg-rose-500/10 text-rose-400',
  recruiter: 'bg-muted/50 text-muted-foreground',
};

interface Contact {
  id: string;
  full_name: string;
  current_title?: string;
  current_company?: string;
  location?: string;
  connected_on?: string;
  email?: string;
  linkedin_url?: string;
  how_you_know?: string;
  source?: string;
  warm_score?: number | null;
  warm_score_override?: number | null;
  referral_likelihood?: string;
  relationship_type?: string;
  score_breakdown?: Record<string, number>;
}

function ScoreBar({ score }: { score: number }) {
  const fillColor = score >= 70 ? 'bg-emerald-500' : score >= 40 ? 'bg-primary' : 'bg-muted-foreground';
  return (
    <div className="flex items-center gap-3">
      <div className="flex-1 h-2 rounded-full bg-muted overflow-hidden">
        <div
          className={`h-full rounded-full ${fillColor} transition-all duration-500`}
          style={{ width: `${Math.min(100, Math.max(0, score))}%` }}
        />
      </div>
      <span className="text-2xl font-bold tabular-nums text-foreground">{score}</span>
    </div>
  );
}

const STEP_LABELS: Record<string, string> = {
  reconnect: 'Reconnect',
  explore: 'Feel it out',
  referral_ask: 'The Ask',
};

function ContactIntroModal({ intro, onClose, contactName, linkedinUrl }) {
  const [copiedId, setCopiedId] = useState<string | null>(null);

  if (!intro) return null;
  const messages = intro.messages || [];
  const totalSteps = messages.length;

  const copyMessage = (msg: any) => {
    navigator.clipboard.writeText(msg.message_body || '');
    setCopiedId(msg.id);
    setTimeout(() => setCopiedId(null), 2000);
    window.dispatchEvent(new Event('journey-updated'));
  };

  const copyAndOpenLinkedIn = (msg: any) => {
    copyMessage(msg);
    if (linkedinUrl) {
      window.open(linkedinUrl, '_blank', 'noopener,noreferrer');
    }
  };

  return (
    <Modal open={!!intro} onClose={onClose} title="Your Intro Messages" maxWidth="max-w-xl">
      <div className="space-y-4">
        {contactName && (
          <p className="text-sm text-muted-foreground">
            Messages for <span className="font-medium text-foreground">{contactName}</span>
          </p>
        )}
        {messages.map((msg: any, idx: number) => {
          const isCopied = copiedId === msg.id;
          const fallbackVariant = msg.variant_label === 'only' ? null : msg.variant_label;
          const label = STEP_LABELS[msg.step_label] || msg.step_label || fallbackVariant || 'Message';
          return (
            <div key={msg.id} className="rounded-lg border border-border p-4">
              <div className="mb-2 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  {totalSteps > 1 && (
                    <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] font-medium text-secondary-foreground">
                      Step {idx + 1}/{totalSteps}
                    </span>
                  )}
                  <span className="rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-secondary-foreground">
                    {label}
                  </span>
                </div>
                {msg.send_after_days > 0 && (
                  <span className="text-xs text-muted-foreground">Come back in {msg.send_after_days} days</span>
                )}
              </div>
              {msg.coaching_notes && (
                <p className="mb-2 rounded bg-muted/50 px-3 py-1.5 text-xs text-muted-foreground">
                  <span className="font-medium">Keevs suggests:</span> {msg.coaching_notes}
                </p>
              )}
              {msg.subject_line && (
                <p className="mb-1 text-xs text-muted-foreground">
                  Subject: <span className="font-medium text-secondary-foreground">{msg.subject_line}</span>
                </p>
              )}
              <p className="mb-3 whitespace-pre-wrap text-sm text-secondary-foreground">{msg.message_body}</p>
              <div className="flex gap-2">
                {linkedinUrl ? (
                  <button
                    onClick={() => copyAndOpenLinkedIn(msg)}
                    className="rounded-lg bg-primary px-3 py-1.5 text-xs font-medium text-white hover:bg-primary/90 transition-colors"
                    aria-label={`Copy message and open LinkedIn profile for ${contactName || 'contact'}`}
                  >
                    {isCopied ? 'Copied! Opening LinkedIn...' : 'Copy & Open LinkedIn'}
                  </button>
                ) : (
                  <button
                    onClick={() => copyMessage(msg)}
                    className="rounded-lg bg-primary px-3 py-1.5 text-xs font-medium text-white hover:bg-primary/90 transition-colors"
                    aria-label="Copy message to clipboard"
                  >
                    {isCopied ? 'Copied!' : 'Copy Message'}
                  </button>
                )}
                {linkedinUrl && (
                  <button
                    onClick={() => copyMessage(msg)}
                    className="rounded-lg border border-border px-3 py-1.5 text-xs font-medium text-muted-foreground hover:bg-muted transition-colors"
                    aria-label="Copy message to clipboard"
                  >
                    {isCopied ? 'Copied!' : 'Copy Only'}
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </Modal>
  );
}

interface ContactDetailProps {
  contact: Contact;
  onClose: () => void;
  onContactUpdate?: (id: string, updates: Partial<Contact>, optimistic: boolean) => void;
  onError?: (message: string) => void;
}

export default function ContactDetail({ contact, onClose, onContactUpdate, onError }: ContactDetailProps) {
  const [detail, setDetail] = useState<Contact>(contact);
  const [loading, setLoading] = useState(false);
  const [relType, setRelType] = useState(contact.relationship_type || '');
  const [relSaving, setRelSaving] = useState(false);
  const [introLoading, setIntroLoading] = useState(false);
  const [introModal, setIntroModal] = useState<any>(null);
  const [introError, setIntroError] = useState('');

  const handleDraftIntro = async () => {
    setIntroLoading(true);
    setIntroError('');
    try {
      const res = await matchesApi.createIntro({
        contact_id: detail.id,
        tone: 'professional',
        channel: 'linkedin',
      });
      setIntroModal(res.data);
    } catch (err: any) {
      setIntroError(err.message || 'Failed to draft intro');
    } finally {
      setIntroLoading(false);
    }
  };

  // Fetch full detail on mount
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    contactsApi.get(contact.id).then((res) => {
      if (!cancelled) {
        setDetail(res.data || res);
        setRelType((res.data || res).relationship_type || '');
      }
    }).catch((err) => {
      console.error('ContactDetail: failed to fetch contact detail', err);
      // Fall back to list data already in state
    }).finally(() => {
      if (!cancelled) setLoading(false);
    });
    return () => { cancelled = true; };
  }, [contact.id]);

  const handleRelChange = async (e: React.ChangeEvent<HTMLSelectElement>) => {
    const val = e.target.value;
    const prevVal = relType;
    setRelType(val);
    setRelSaving(true);
    onContactUpdate?.(contact.id, { relationship_type: val || null }, true);
    try {
      await contactsApi.patch(contact.id, { relationship_type: val || null });
      setDetail((d) => ({ ...d, relationship_type: val || null }));
    } catch (err) {
      console.error('ContactDetail: failed to update relationship type', err);
      setRelType(prevVal);
      onContactUpdate?.(contact.id, { relationship_type: prevVal || null }, false);
      onError?.('Failed to update relationship type');
    } finally {
      setRelSaving(false);
    }
  };

  const handleWarmOverride = async (value: number | null) => {
    const prev = detail.warm_score_override;
    setDetail((d) => ({ ...d, warm_score_override: value, warm_score: value ?? d.warm_score }));
    onContactUpdate?.(contact.id, { warm_score_override: value, warm_score: value ?? detail.warm_score }, true);
    try {
      await contactsApi.patch(contact.id, { warm_score_override: value });
    } catch (err) {
      console.error('ContactDetail: failed to update warm score override', err);
      setDetail((d) => ({ ...d, warm_score_override: prev }));
      onContactUpdate?.(contact.id, { warm_score_override: prev }, false);
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
          <h3 className="text-lg font-semibold text-foreground">{detail.full_name}</h3>
          <p className="text-sm text-muted-foreground">
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
            <div className="h-2 rounded-full bg-muted animate-pulse" />
          ) : detail.warm_score == null ? (
            <p className="text-xs text-muted-foreground">Connection Score will appear after we analyze your connection data.</p>
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
                <p className="text-xs text-muted-foreground">{warmTier.desc}</p>
              )}
              {/* Score breakdown if available */}
              {detail.score_breakdown && (
                <div className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                  {detail.score_breakdown.recency != null && (
                    <div className="flex justify-between"><span className="text-muted-foreground">Recency (35%)</span><span className="text-secondary-foreground">{detail.score_breakdown.recency}</span></div>
                  )}
                  {detail.score_breakdown.relationship != null && (
                    <div className="flex justify-between"><span className="text-muted-foreground">Relationship (30%)</span><span className="text-secondary-foreground">{detail.score_breakdown.relationship}</span></div>
                  )}
                  {detail.score_breakdown.role_relevance != null && (
                    <div className="flex justify-between"><span className="text-muted-foreground">Role relevance (20%)</span><span className="text-secondary-foreground">{detail.score_breakdown.role_relevance}</span></div>
                  )}
                  {detail.score_breakdown.tenure != null && (
                    <div className="flex justify-between"><span className="text-muted-foreground">Time at company (15%)</span><span className="text-secondary-foreground">{detail.score_breakdown.tenure}</span></div>
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
                <p className="text-xs text-muted-foreground">Company</p>
                <p className="text-sm text-foreground">{detail.current_company}</p>
              </div>
            )}
            {detail.current_title && (
              <div>
                <p className="text-xs text-muted-foreground">Position</p>
                <p className="text-sm text-foreground">{detail.current_title}</p>
              </div>
            )}
            {detail.location && (
              <div>
                <p className="text-xs text-muted-foreground">Location</p>
                <p className="text-sm text-foreground">{detail.location}</p>
              </div>
            )}
            {detail.connected_on && (
              <div>
                <p className="text-xs text-muted-foreground">Connected since</p>
                <p className="text-sm text-foreground">
                  {new Date(detail.connected_on).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
                </p>
              </div>
            )}
            {detail.email && (
              <div>
                <p className="text-xs text-muted-foreground">Email</p>
                <p className="text-sm text-foreground">{detail.email}</p>
              </div>
            )}
            {detail.how_you_know && (
              <div>
                <p className="text-xs text-muted-foreground">How you know them</p>
                <p className="text-sm text-foreground">{detail.how_you_know}</p>
              </div>
            )}
            {detail.source && (
              <div>
                <p className="text-xs text-muted-foreground">Source</p>
                <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${detail.source === 'manual' ? 'bg-primary/10 text-primary' : 'bg-muted/50 text-muted-foreground'}`}>
                  {detail.source === 'manual' ? 'Manual' : 'LinkedIn CSV'}
                </span>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Actions (sticky bottom) */}
      <div className="sticky bottom-0 -mx-6 border-t border-border bg-card px-6 py-4 mt-6 space-y-3">
        {/* Relationship type selector */}
        <div>
          <label htmlFor="slideover-rel-type" className="mb-1 block text-xs text-muted-foreground">
            {relType ? 'Relationship type' : 'Classify this contact'}
          </label>
          <select
            id="slideover-rel-type"
            value={relType}
            onChange={handleRelChange}
            disabled={relSaving}
            className="w-full rounded-lg border border-border bg-muted px-3 py-2 text-sm text-foreground focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring disabled:opacity-50"
          >
            <option value="">Unclassified</option>
            {RELATIONSHIP_TYPES.map((r) => (
              <option key={r.value} value={r.value}>{r.label}</option>
            ))}
          </select>
        </div>

        {/* Warm score override */}
        <div className="border-t border-border pt-3">
          <label className="mb-2 block text-xs text-muted-foreground">
            How close are you?
          </label>
          <div className="grid grid-cols-3 gap-1.5">
            {[
              { label: 'Cold', value: 10, color: 'text-muted-foreground border-border' },
              { label: 'Lukewarm', value: 30, color: 'text-blue-400 border-blue-500/30' },
              { label: 'Warm', value: 55, color: 'text-primary border-primary/30' },
              { label: 'Strong', value: 75, color: 'text-emerald-400 border-emerald-500/30' },
              { label: 'Very Strong', value: 90, color: 'text-emerald-300 border-emerald-400/30' },
              { label: 'Auto', value: null, color: 'text-muted-foreground border-border' },
            ].map((opt) => (
              <button
                key={opt.label}
                type="button"
                onClick={() => handleWarmOverride(opt.value)}
                className={`rounded-md border px-2 py-1.5 text-xs font-medium transition ${
                  detail.warm_score_override === opt.value
                    ? `${opt.color} bg-muted ring-1 ring-current`
                    : 'border-border text-muted-foreground hover:text-secondary-foreground'
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
          {detail.warm_score_override != null && (
            <p className="mt-1 text-xs text-muted-foreground">
              You've set this connection strength manually.
            </p>
          )}
        </div>

        {introError && (
          <p className="text-sm text-red-400">{introError}</p>
        )}

        <div className="flex gap-2">
          <button
            onClick={handleDraftIntro}
            disabled={introLoading}
            className="flex-1 rounded-lg bg-primary py-2.5 text-sm font-medium text-white hover:bg-primary/90 transition-colors disabled:opacity-50"
          >
            {introLoading ? 'Drafting...' : 'Draft Intro Message'}
          </button>
          <button
            onClick={onClose}
            className="rounded-lg border border-border px-4 py-2.5 text-sm font-medium text-muted-foreground hover:bg-muted transition-colors"
          >
            Close
          </button>
        </div>
      </div>

      {introModal && (
        <ContactIntroModal
          intro={introModal}
          onClose={() => setIntroModal(null)}
          contactName={detail.full_name}
          linkedinUrl={detail.linkedin_url}
        />
      )}
    </div>
  );
}
