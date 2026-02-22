import { useEffect, useState } from 'react';
import { marketplace, auth as authApi } from '../api/client';
import { useAuth } from '../context/AuthContext';
import { trackEvent } from '../utils/analytics';
import { MarketplaceBadge } from '../utils/marketplace';
import Modal from './ui/Modal';
import Button from './ui/Button';

const inputClass = 'w-full rounded-lg border border-slate-700/50 bg-slate-800 text-slate-100 placeholder-slate-500 px-3 py-2 text-sm focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500';

export default function RequestIntroModal({ listing, creditBalance, onClose, onSuccess }) {
  const { user } = useAuth();
  const [profile, setProfile] = useState(null);
  const [requestType, setRequestType] = useState('specific_role');
  const [jobTitle, setJobTitle] = useState('');
  const [jobDescription, setJobDescription] = useState('');
  const [explorationContext, setExplorationContext] = useState('');
  const [message, setMessage] = useState('');
  const [visibility, setVisibility] = useState('summary');
  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');

  const canAfford = creditBalance >= 20;
  const completeness = user?.profile_completeness ?? 100;

  // Load profile data for preview
  useEffect(() => {
    authApi.upsertProfile({}).then((res) => {
      setProfile(res.data);
    }).catch(() => {});
  }, []);

  const handleSubmit = async () => {
    setSending(true);
    setError('');
    try {
      await marketplace.requestIntro({
        marketplace_listing_id: listing.listing.id,
        profile_visibility: visibility,
        request_type: requestType,
        ...(requestType === 'specific_role' && {
          job_title: jobTitle || undefined,
          job_description: jobDescription || undefined,
        }),
        ...(requestType === 'general_networking' && {
          exploration_context: explorationContext || undefined,
        }),
        message_to_holder: message || undefined,
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
    <Modal open onClose={onClose} title="Request Introduction" maxWidth="max-w-lg">
      <div className="space-y-5">

        {/* 1. Profile Preview */}
        <section aria-label="Your profile preview">
          <p className="mb-2 text-xs font-medium uppercase tracking-wider text-slate-400">What the connection owner will see</p>
          <div className="rounded-lg border border-slate-700/50 bg-slate-800/50 p-3">
            <p className="text-sm font-medium text-slate-50">{user?.full_name || 'Your name'}</p>
            {profile?.current_title && (
              <p className="text-sm text-slate-400">
                {profile.current_title}{profile.current_company ? ` at ${profile.current_company}` : ''}
              </p>
            )}
            {profile?.work_history?.length > 0 && (
              <div className="mt-2">
                <p className="text-xs text-slate-500">Previously at</p>
                <p className="text-xs text-slate-400">
                  {profile.work_history.slice(0, 3).map((w) => w.company).join(', ')}
                </p>
              </div>
            )}
            {profile?.github_url && (
              <a href={profile.github_url} target="_blank" rel="noopener noreferrer" className="mt-1 inline-block text-xs text-amber-400 hover:text-amber-300">
                GitHub
              </a>
            )}
            {completeness < 70 && (
              <div className="mt-2 rounded-md bg-amber-500/10 px-2 py-1.5">
                <p className="text-xs text-amber-400">
                  Your profile is {completeness}% complete. A more complete profile increases your chances of approval.
                </p>
              </div>
            )}
          </div>
        </section>

        {/* Listing summary */}
        <div className="rounded-lg bg-slate-800/50 p-3">
          <div className="flex items-center gap-2 text-sm font-medium text-slate-50">
            <MarketplaceBadge value={listing.listing.role_level} type="role" />
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-slate-400">
            {listing.listing.department_category && <span>{listing.listing.department_category}</span>}
            {listing.listing.department_category && <span>&middot;</span>}
            <MarketplaceBadge value={listing.listing.warm_score_range} type="strength" />
          </div>
          {listing.network_holder_reputation && (
            <p className="mt-1 text-xs text-slate-500">
              Holder reputation: {listing.network_holder_reputation.avg_rating?.toFixed(1) ?? '—'}
              {' '}({listing.network_holder_reputation.intros_facilitated} intros facilitated)
            </p>
          )}
        </div>

        {/* 2. Request Type Selector */}
        <section aria-label="Request type">
          <label className="mb-2 block text-sm font-medium text-slate-300">What are you looking for?</label>
          <div className="space-y-2">
            <label className="flex items-center gap-2 rounded-lg border border-slate-700/50 p-3 text-sm cursor-pointer hover:bg-slate-800/50">
              <input
                type="radio"
                name="requestType"
                value="specific_role"
                checked={requestType === 'specific_role'}
                onChange={() => setRequestType('specific_role')}
                className="h-4 w-4 border-slate-600 text-amber-500 focus:ring-amber-500"
              />
              <div>
                <span className="text-slate-200">Referral for a specific role</span>
                <p className="text-xs text-slate-500">You have a specific job posting in mind</p>
              </div>
            </label>
            <label className="flex items-center gap-2 rounded-lg border border-slate-700/50 p-3 text-sm cursor-pointer hover:bg-slate-800/50">
              <input
                type="radio"
                name="requestType"
                value="general_networking"
                checked={requestType === 'general_networking'}
                onChange={() => setRequestType('general_networking')}
                className="h-4 w-4 border-slate-600 text-amber-500 focus:ring-amber-500"
              />
              <div>
                <span className="text-slate-200">General networking</span>
                <p className="text-xs text-slate-500">Exploring opportunities at this company</p>
              </div>
            </label>
          </div>
        </section>

        {/* 3. Conditional Fields */}
        {requestType === 'specific_role' && (
          <section className="space-y-3" aria-label="Role details">
            <div>
              <label htmlFor="intro-job-title" className="mb-1 block text-sm font-medium text-slate-300">Job title</label>
              <input
                id="intro-job-title"
                type="text"
                value={jobTitle}
                onChange={(e) => setJobTitle(e.target.value)}
                placeholder="e.g. Senior Software Engineer"
                className={inputClass}
              />
            </div>
            <div>
              <label htmlFor="intro-job-desc" className="mb-1 block text-sm font-medium text-slate-300">
                Job description or link <span className="text-slate-500">(optional)</span>
              </label>
              <textarea
                id="intro-job-desc"
                value={jobDescription}
                onChange={(e) => setJobDescription(e.target.value)}
                rows={2}
                placeholder="Paste the job description or a link to the posting..."
                className={inputClass}
              />
            </div>
          </section>
        )}

        {requestType === 'general_networking' && (
          <section aria-label="Exploration context">
            <div>
              <label htmlFor="intro-explore-context" className="mb-1 block text-sm font-medium text-slate-300">
                What are you exploring? <span className="text-slate-500">(optional)</span>
              </label>
              <textarea
                id="intro-explore-context"
                value={explorationContext}
                onChange={(e) => setExplorationContext(e.target.value)}
                rows={2}
                placeholder="e.g. Interested in learning about the engineering culture..."
                className={inputClass}
              />
            </div>
          </section>
        )}

        {/* Profile visibility */}
        <section aria-label="Profile visibility">
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
        </section>

        {/* 4. Personal Note + Submit */}
        <div>
          <label htmlFor="intro-message" className="mb-1 block text-sm font-medium text-slate-300">
            Personal note <span className="text-slate-500">(optional)</span>
          </label>
          <textarea
            id="intro-message"
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            rows={3}
            placeholder="Brief intro about yourself and why you'd be a good fit..."
            className={inputClass}
          />
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
