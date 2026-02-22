import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { marketplace as mpApi, credits as creditsApi } from '../api/client';
import { trackEvent } from '../utils/analytics';
import { SOURCES } from '../utils/sources';
import { MarketplaceBadge } from '../utils/marketplace';
import EmptyState from '../components/ui/EmptyState';
import SourceTag from '../components/ui/SourceTag';
import DashboardSkeleton from '../components/skeletons/DashboardSkeleton';
import IntroRelayModal from '../components/IntroRelayModal';
import useDocumentTitle from '../hooks/useDocumentTitle';

function StatusBadge({ status }) {
  const labels = { requested: 'Pending', reviewing: 'Reviewing', approved: 'Approved', declined: 'Declined', completed: 'Completed' };
  const colors = {
    requested: 'bg-amber-500/10 text-amber-400',
    reviewing: 'bg-blue-500/10 text-blue-400',
    approved: 'bg-emerald-500/10 text-emerald-400',
    declined: 'bg-red-500/10 text-red-400',
    completed: 'bg-slate-700/50 text-slate-400',
  };
  return (
    <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${colors[status] || colors.requested}`}>
      {labels[status] || status}
    </span>
  );
}

export default function MarketplaceOverview() {
  useDocumentTitle('Marketplace');
  const [listings, setListings] = useState([]);
  const [incoming, setIncoming] = useState([]);
  const [balance, setBalance] = useState(0);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(null);
  const [approvedCoaching, setApprovedCoaching] = useState(null); // id of request showing coaching
  const [sharingPrefs, setSharingPrefs] = useState(null);
  const [excludedIds, setExcludedIds] = useState([]);
  const [toggleLoading, setToggleLoading] = useState(null);
  const [decliningId, setDecliningId] = useState(null);
  const [statsAnimating, setStatsAnimating] = useState(false);
  const [relayModal, setRelayModal] = useState(null); // { id, contactName, linkedinUrl, draftedMessage }

  const load = async () => {
    try {
      const [listingsRes, incomingRes, balRes, prefsRes] = await Promise.all([
        mpApi.myListings().catch(() => ({ data: [] })),
        mpApi.incomingRequests().catch(() => ({ data: [] })),
        creditsApi.balance().catch(() => ({ data: { balance: 0 } })),
        mpApi.getSharingPrefs().catch(() => ({ data: {} })),
      ]);
      setListings(listingsRes.data || []);
      setIncoming(incomingRes.data || []);
      setBalance(balRes.data?.balance ?? 0);
      setSharingPrefs(prefsRes.data || {});
      setExcludedIds(prefsRes.data?.excluded_contact_ids || []);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const handleAction = async (id, action) => {
    setActionLoading(id);
    const prevIncoming = [...incoming];

    // Trigger stat animation
    setStatsAnimating(true);
    setTimeout(() => setStatsAnimating(false), 300);

    if (action === 'approve') {
      trackEvent('intro_approved');
      setApprovedCoaching(id);
      // Optimistic: move to approved state immediately
      setIncoming((prev) => prev.map((r) => r.id === id ? { ...r, status: 'approved' } : r));
    } else if (action === 'decline') {
      // Animate out, then remove after animation completes
      setDecliningId(id);
      setTimeout(() => {
        setIncoming((prev) => prev.filter((r) => r.id !== id));
        setDecliningId(null);
      }, 300);
    }

    try {
      const res = await mpApi.updateRequest(id, { action });
      const data = res.data;

      if (action === 'approve' && data) {
        // Update the request in state with delivery info from response
        setIncoming((prev) => prev.map((r) =>
          r.id === id ? { ...r, status: 'approved', delivery_method: data.delivery_method, delivery_status: data.delivery_status } : r
        ));

        if (data.delivery_method === 'email_relay') {
          // Email sent automatically — no further action needed
        } else if (!data.delivery_method) {
          // No email on file — open LinkedIn fallback modal
          const req = prevIncoming.find((r) => r.id === id);
          setRelayModal({
            id,
            contactName: req?.contact_name || data.contact_name || 'your contact',
            linkedinUrl: data.linkedin_url || null,
            draftedMessage: data.drafted_message || '',
          });
        }
      }
    } catch (err) {
      console.error(err);
      // Revert on failure
      setIncoming(prevIncoming);
      setDecliningId(null);
    } finally {
      setActionLoading(null);
    }
  };

  const handleConfirmSent = async (facilitationId) => {
    await mpApi.confirmSent(facilitationId);
    // Update local state to reflect manual send confirmation
    setIncoming((prev) => prev.map((r) =>
      r.id === facilitationId ? { ...r, delivery_method: 'linkedin_manual', delivery_status: 'delivered' } : r
    ));
    // Refresh balance since 50 credits were awarded
    try {
      const balRes = await creditsApi.balance();
      setBalance(balRes.data?.balance ?? balance);
    } catch (_err) {
      // Non-critical — balance will refresh on next load
    }
  };

  const toggleContactVisibility = async (contactId) => {
    if (toggleLoading) return;
    setToggleLoading(contactId);
    const prevExcluded = [...excludedIds];
    // Optimistic update
    const newExcluded = excludedIds.includes(contactId)
      ? excludedIds.filter((id) => id !== contactId)
      : [...excludedIds, contactId];
    setExcludedIds(newExcluded);

    try {
      const body = {
        opt_in_marketplace: sharingPrefs?.opt_in_marketplace ?? true,
        is_paused: sharingPrefs?.is_paused ?? false,
        category_filters: sharingPrefs?.category_filters || null,
        excluded_contact_ids: newExcluded.length > 0 ? newExcluded : null,
      };
      const res = await mpApi.updateSharingPrefs(body);
      setSharingPrefs(res.data);
    } catch (err) {
      console.error('Failed to update visibility:', err);
      setExcludedIds(prevExcluded); // Revert on error
    } finally {
      setToggleLoading(null);
    }
  };

  if (loading) {
    return <DashboardSkeleton />;
  }

  const pendingRequests = incoming.filter((r) => r.status === 'requested');
  const pastRequests = incoming.filter((r) => r.status !== 'requested');
  const approvedCount = incoming.filter((r) => r.status === 'approved').length;
  const totalResponded = incoming.filter((r) => ['approved', 'declined'].includes(r.status)).length;
  const responseRate = totalResponded > 0 ? Math.round((approvedCount / totalResponded) * 100) : 0;

  return (
    <div className="space-y-6" role="main">
      <div className="flex items-center justify-between">
        <h1 className="page-title">Marketplace Overview</h1>
        <Link to="/settings?tab=sharing" className="rounded-md border border-slate-700/50 px-3 py-1.5 text-sm text-slate-400 hover:bg-slate-800">
          Sharing Settings
        </Link>
      </div>

      {/* Quick navigation */}
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <Link to="/marketplace/browse" className="rounded-lg border border-amber-500/30 px-3 py-1.5 text-amber-400 hover:bg-amber-500/10">
          Browse Marketplace
        </Link>
        <Link to="/marketplace/requests" className="rounded-lg border border-slate-700/50 px-3 py-1.5 text-slate-400 hover:bg-slate-800">
          My Requests {pendingRequests.length > 0 && <span className="ml-1 rounded-full bg-amber-500/10 px-1.5 py-0.5 text-xs font-medium text-amber-400">{pendingRequests.length}</span>}
        </Link>
        <Link to="/contacts" className="text-slate-400 hover:text-slate-300">Manage Contacts</Link>
        <Link to="/credits" className="text-slate-400 hover:text-slate-300">View Credits</Link>
      </div>

      {/* Referral bonus callout */}
      {approvedCount === 0 && (
        <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-4">
          <div className="flex items-start gap-3">
            <svg className="mt-0.5 h-5 w-5 shrink-0 text-emerald-400" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v12m-3-2.818.879.659c1.171.879 3.07.879 4.242 0 1.172-.879 1.172-2.303 0-3.182C13.536 12.219 12.768 12 12 12c-.725 0-1.45-.22-2.003-.659-1.106-.879-1.106-2.303 0-3.182s2.9-.879 4.006 0l.415.33M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
            </svg>
            <div>
              <p className="text-sm font-semibold text-emerald-400">Your employer pays {SOURCES.REFERRAL_BONUS_RANGE.claim} per referral hire</p>
              <p className="mt-0.5 text-sm text-emerald-400/80">
                When you approve an intro and your contact hires the candidate, the referral bonus goes directly to you.
                WarmPath sends you pre-qualified candidates so you don't have to find them yourself.{' '}
                <SourceTag source={SOURCES.REFERRAL_BONUS_RANGE.source} label={SOURCES.REFERRAL_BONUS_RANGE.label} />
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Reputation + Stats */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        <div className="surface-raised p-4">
          <p className="stat-label">Active Listings</p>
          <p className="stat-number">{listings.length}</p>
        </div>
        <div className="surface-raised p-4">
          <p className="stat-label">Pending Requests</p>
          <p className={`stat-number text-amber-400 ${statsAnimating ? 'animate-count-change' : ''}`}>{pendingRequests.length}</p>
        </div>
        <div className="surface-raised p-4">
          <p className="stat-label">Intros Facilitated</p>
          <p className={`stat-number ${statsAnimating ? 'animate-count-change' : ''}`}>{approvedCount}</p>
        </div>
        <div className="surface-raised p-4">
          <p className="stat-label">Response Rate</p>
          <p className="stat-number">{responseRate}%</p>
        </div>
        <div className="surface-raised p-4">
          <p className="stat-label">Credits</p>
          <p className="stat-number text-amber-400">{balance}</p>
        </div>
      </div>

      {/* Incoming Requests (Pending) */}
      <div className="surface-raised">
        <div className="border-b border-slate-700/50 px-5 py-4">
          <h2 className="section-title">
            Incoming Requests
            {pendingRequests.length > 0 && (
              <span className="ml-2 rounded-full bg-amber-500/10 px-2 py-0.5 text-xs font-medium text-amber-400">
                {pendingRequests.length} pending
              </span>
            )}
          </h2>
        </div>

        {pendingRequests.length === 0 && pastRequests.length === 0 ? (
          <EmptyState
            icon={
              <svg className="h-12 w-12" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 13.5h3.86a2.25 2.25 0 0 1 2.012 1.244l.256.512a2.25 2.25 0 0 0 2.013 1.244h3.218a2.25 2.25 0 0 0 2.013-1.244l.256-.512a2.25 2.25 0 0 1 2.013-1.244h3.859m-19.5.338V18a2.25 2.25 0 0 0 2.25 2.25h15A2.25 2.25 0 0 0 21.75 18v-4.162c0-.224-.034-.447-.1-.661L19.24 5.338a2.25 2.25 0 0 0-2.15-1.588H6.911a2.25 2.25 0 0 0-2.15 1.588L2.35 13.177a2.25 2.25 0 0 0-.1.661Z" />
              </svg>
            }
            title="Requests will appear here"
            description="When job seekers find your contacts on the marketplace, you'll review their profile and decide whether to make an intro. You earn referral bonuses from your employer for successful hires."
            stats={[{ value: '$2-10K', label: 'avg referral bonus' }]}
            statsSource={SOURCES.REFERRAL_BONUS_RANGE.source}
          />
        ) : (
          <div className="divide-y divide-slate-700/50">
            {/* Pending first */}
            {pendingRequests.map((req) => (
              <div key={req.id} className={`px-5 py-4 transition-all duration-150 ${decliningId === req.id ? 'animate-fade-out-up' : ''}`}>
                <div className="flex flex-col gap-4 sm:flex-row sm:items-start">
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <StatusBadge status={req.status} />
                      <span className="text-xs text-slate-400">
                        {new Date(req.requested_at).toLocaleDateString()}
                      </span>
                    </div>

                    {/* Job seeker profile snapshot */}
                    <div className="mt-2 rounded-lg bg-blue-500/10 p-3">
                      <p className="text-xs font-medium uppercase tracking-wider text-blue-400">Candidate</p>
                      <p className="mt-1 text-sm font-medium text-slate-50">
                        {req.job_seeker_profile_snapshot?.full_name || 'Anonymous'}
                      </p>
                      {req.job_seeker_profile_snapshot?.email && (
                        <p className="text-xs text-slate-400">{req.job_seeker_profile_snapshot.email}</p>
                      )}
                      {req.job_seeker_profile_snapshot?.message && (
                        <p className="mt-2 text-sm italic text-slate-400">
                          "{req.job_seeker_profile_snapshot.message}"
                        </p>
                      )}
                    </div>

                    {/* Listing + your contact info */}
                    <div className="mt-2 rounded-lg bg-slate-800/50 p-3">
                      <p className="text-xs font-medium uppercase tracking-wider text-slate-400">Your Contact</p>
                      <p className="mt-1 text-sm font-medium text-slate-50">
                        {req.contact_name || 'Unknown'}
                        {req.contact_title && <span className="font-normal text-slate-400">, {req.contact_title}</span>}
                      </p>
                      {req.contact_company && (
                        <p className="text-xs text-slate-400">at {req.contact_company}</p>
                      )}
                      {req.contact_email && (
                        <p className="text-xs text-slate-500">{req.contact_email}</p>
                      )}
                    </div>
                  </div>

                  <div className="flex shrink-0 flex-col gap-2">
                    <button
                      onClick={() => handleAction(req.id, 'approve')}
                      disabled={actionLoading === req.id}
                      aria-label={`Approve intro request from ${req.job_seeker_profile_snapshot?.full_name || 'candidate'}`}
                      className="rounded-md bg-emerald-500 px-4 py-2.5 text-sm font-medium text-white hover:bg-emerald-400 disabled:opacity-50"
                    >
                      Approve
                    </button>
                    <button
                      onClick={() => handleAction(req.id, 'decline')}
                      disabled={actionLoading === req.id}
                      aria-label={`Decline intro request from ${req.job_seeker_profile_snapshot?.full_name || 'candidate'}`}
                      className="rounded-md border border-red-500/30 px-4 py-2.5 text-sm font-medium text-red-400 hover:bg-red-500/10 disabled:opacity-50"
                    >
                      Decline
                    </button>
                  </div>
                </div>
              </div>
            ))}

            {/* Past requests */}
            {pastRequests.map((req) => (
              <div key={req.id} className="px-5 py-4 transition-all duration-150">
                <div className="flex items-center gap-2">
                  <StatusBadge status={req.status} />
                  <span className="text-sm text-slate-300">
                    {req.job_seeker_profile_snapshot?.full_name || 'Anonymous'}
                  </span>
                  <span className="text-xs text-slate-400">
                    &rarr; {req.contact_name || 'Unknown'}
                    {req.contact_company && ` at ${req.contact_company}`}
                  </span>
                  <span className="ml-auto text-xs text-slate-400">
                    {new Date(req.requested_at).toLocaleDateString()}
                  </span>
                </div>

                {/* Coaching text after approval — dynamic based on delivery status */}
                {req.status === 'approved' && (req.id === approvedCoaching || !approvedCoaching) && (
                  <div className="mt-3 rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-4" aria-live="polite">
                    {req.delivery_method === 'email_relay' && req.delivery_status === 'delivered' ? (
                      <>
                        <p className="text-sm font-semibold text-emerald-400">
                          Email delivered! 50 credits earned.
                        </p>
                        <p className="mt-1 text-xs text-emerald-400/70">
                          The intro to {req.contact_name || 'your contact'} for {req.job_seeker_profile_snapshot?.full_name || 'this candidate'} was delivered successfully.
                        </p>
                      </>
                    ) : req.delivery_method === 'email_relay' ? (
                      <>
                        <p className="text-sm font-semibold text-emerald-400">
                          Introduction sent to {req.contact_name || 'your contact'} via email!
                        </p>
                        <p className="mt-1 text-xs text-emerald-400/70">
                          You'll earn 50 credits when delivery is confirmed.
                        </p>
                      </>
                    ) : req.delivery_method === 'linkedin_manual' ? (
                      <>
                        <p className="text-sm font-semibold text-emerald-400">
                          You confirmed sending the intro. 50 credits earned!
                        </p>
                        <p className="mt-1 text-xs text-emerald-400/70">
                          Thank you for connecting {req.job_seeker_profile_snapshot?.full_name || 'the candidate'} with {req.contact_name || 'your contact'}.
                        </p>
                      </>
                    ) : (
                      /* No delivery method yet — approved but needs manual send */
                      <>
                        <p className="mb-2 text-sm font-semibold text-emerald-400">
                          Now introduce {req.job_seeker_profile_snapshot?.full_name || 'this candidate'} to {req.contact_name || 'your contact'}
                        </p>
                        <p className="text-sm text-emerald-400/80">
                          We don't have an email for {req.contact_name || 'your contact'}, so you'll need to send the intro yourself.
                        </p>
                        <button
                          type="button"
                          onClick={() => setRelayModal({
                            id: req.id,
                            contactName: req.contact_name || 'your contact',
                            linkedinUrl: req.linkedin_url || null,
                            draftedMessage: req.drafted_message || `Hey ${req.contact_name?.split(' ')[0] || 'there'}, I'd like to introduce you to ${req.job_seeker_profile_snapshot?.full_name || 'someone'} who's interested in opportunities at ${req.contact_company || 'your company'}. They came through WarmPath and I thought you two should connect.`,
                          })}
                          className="mt-2 rounded-md bg-emerald-500 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-400"
                          aria-label="Send the introduction manually"
                        >
                          Send the Introduction
                        </button>
                      </>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Marketplace Visibility */}
      {listings.length > 0 ? (
        <div className="space-y-4">
          {/* Section header */}
          <h2 className="section-title">
            Marketplace Visibility
            <span className="ml-2 text-sm font-normal text-slate-400">
              {listings.length} contact{listings.length !== 1 ? 's' : ''} shared
            </span>
          </h2>

          {/* Privacy explainer */}
          <div className="rounded-lg border border-blue-500/30 bg-blue-500/10 p-4">
            <p className="text-sm text-blue-400">
              Job seekers searching the marketplace see anonymized listings only — role level, department, and connection strength.
              They never see names, titles, emails, or companies. When someone requests an intro, you review their profile and decide whether to connect them.
            </p>
          </div>

          {/* Active filter summary */}
          {sharingPrefs?.category_filters?.include_departments?.length > 0 && (
            <p className="text-sm text-slate-400">
              Sharing {sharingPrefs.category_filters.include_departments.join(' and ')} contacts.{' '}
              <Link to="/settings?tab=sharing" className="text-amber-400 hover:text-amber-300">
                Change in Settings &rarr;
              </Link>
            </p>
          )}

          {/* Card grid */}
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {listings.map((l) => {
              const contactId = l.contact_id || l.id;
              const isHidden = excludedIds.includes(contactId);
              return (
                <div key={l.id} className={`surface-raised p-4 relative${isHidden ? ' opacity-50' : ''}`}>
                  {/* Eye toggle button */}
                  <button
                    type="button"
                    onClick={() => toggleContactVisibility(contactId)}
                    disabled={toggleLoading === contactId}
                    className="absolute top-3 right-3 p-2 text-slate-500 hover:text-slate-300 disabled:opacity-50"
                    aria-label={isHidden ? 'Show contact on marketplace' : 'Hide contact from marketplace'}
                  >
                    {isHidden ? (
                      <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M3.98 8.223A10.477 10.477 0 0 0 1.934 12C3.226 16.338 7.244 19.5 12 19.5c.993 0 1.953-.138 2.863-.395M6.228 6.228A10.451 10.451 0 0 1 12 4.5c4.756 0 8.773 3.162 10.065 7.498a10.522 10.522 0 0 1-4.293 5.774M6.228 6.228 3 3m3.228 3.228 3.65 3.65m7.894 7.894L21 21m-3.228-3.228-3.65-3.65m0 0a3 3 0 1 0-4.243-4.243m4.242 4.242L9.88 9.88" />
                      </svg>
                    ) : (
                      <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M2.036 12.322a1.012 1.012 0 0 1 0-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178Z" />
                        <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z" />
                      </svg>
                    )}
                  </button>

                  {/* Top zone — NH's private view */}
                  <div className="pr-8">
                    <p className="font-bold text-slate-50">{l.contact_name || '—'}</p>
                    <p className="text-sm text-slate-400">
                      {l.contact_title || '—'}{l.contact_company ? ` at ${l.contact_company}` : ''}
                    </p>
                    <p className="mt-1 text-xs text-slate-500">Only you see this</p>
                  </div>

                  {/* Dashed divider */}
                  <div className="border-t border-dashed border-slate-700 my-3" />

                  {/* Bottom zone — job seeker anonymized view */}
                  <div>
                    {isHidden ? (
                      <p className="text-sm text-slate-500">Hidden from marketplace</p>
                    ) : (
                      <>
                        <p className="mb-1.5 text-xs text-slate-500">Job seekers see</p>
                        <div className="flex items-center gap-1.5 flex-wrap">
                          <MarketplaceBadge value={l.role_level} type="role" />
                          <span className="text-slate-600">&middot;</span>
                          <MarketplaceBadge value={l.department_category} type="department" />
                          <span className="text-slate-600">&middot;</span>
                          <MarketplaceBadge value={l.warm_score_range} type="strength" />
                        </div>
                      </>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
          <p className="text-xs text-slate-500">
            Hidden contacts can be restored in{' '}
            <Link to="/settings?tab=sharing" className="text-amber-400 hover:text-amber-300">
              Sharing Settings &rarr;
            </Link>
          </p>
        </div>
      ) : (
        <div className="surface-raised p-12 text-center">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-slate-800" aria-hidden="true">
            <svg className="h-7 w-7 text-slate-400" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 12h16.5m-16.5 3.75h16.5M3.75 19.5h16.5M5.625 4.5h12.75a1.875 1.875 0 0 1 0 3.75H5.625a1.875 1.875 0 0 1 0-3.75Z" />
            </svg>
          </div>
          <h2 className="mb-2 text-base font-semibold text-slate-50">No marketplace listings yet</h2>
          <p className="mx-auto mb-4 max-w-sm text-sm text-slate-400">
            Upload your contacts and enable sharing to list them anonymously on the marketplace. You'll earn credits and capture referral bonuses when candidates get hired.
          </p>
          <Link to="/settings?tab=sharing" className="inline-block rounded-lg bg-amber-500 px-6 py-2.5 text-sm font-medium text-white hover:bg-amber-400">
            Enable Sharing
          </Link>
        </div>
      )}
      {/* LinkedIn fallback modal */}
      <IntroRelayModal
        isOpen={!!relayModal}
        onClose={() => setRelayModal(null)}
        contactName={relayModal?.contactName}
        linkedinUrl={relayModal?.linkedinUrl}
        draftedMessage={relayModal?.draftedMessage}
        onConfirmSent={() => handleConfirmSent(relayModal?.id)}
      />
    </div>
  );
}
