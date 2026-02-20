import { useEffect, useState } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { search as searchApi, credits as creditsApi, matches as matchesApi } from '../api/client';
import RequestIntroModal from '../components/RequestIntroModal';
import FeedbackModal from '../components/FeedbackModal';
import MatchBadge from '../components/MatchBadge';
import ScoreExplainer from '../components/ScoreExplainer';
import { WARM_TIERS } from '../utils/scores';
import { MarketplaceBadge } from '../utils/marketplace';
import Modal from '../components/ui/Modal';
import Button from '../components/ui/Button';
import Badge from '../components/ui/Badge';
import Spinner from '../components/ui/Spinner';

/* ------------------------------------------------------------------ */
/* Channel + likelihood labels                                        */
/* ------------------------------------------------------------------ */

const CHANNEL_LABELS = {
  linkedin: 'LinkedIn',
  linkedin_message: 'LinkedIn message',
  email: 'Email',
  whatsapp: 'WhatsApp',
  phone: 'Phone',
  in_person: 'In person',
  slack: 'Slack',
  text: 'Text message',
};

function channelLabel(raw) {
  if (!raw) return null;
  return CHANNEL_LABELS[raw] || raw.replace(/_/g, ' ');
}

function LikelihoodBadge({ level }) {
  return <MatchBadge level={level} type="likelihood" />;
}

const REL_LABELS = {
  current_colleague: 'current colleague',
  former_colleague: 'former colleague',
  manager: 'former manager',
  alumni: 'alumni',
  industry_peer: 'industry peer',
  friend: 'friend',
  mentor: 'mentor',
  recruiter: 'recruiter',
};

/* ------------------------------------------------------------------ */
/* Intro Draft Modal                                                  */
/* ------------------------------------------------------------------ */

function IntroModal({ intro, onClose }) {
  if (!intro) return null;
  return (
    <Modal open={!!intro} onClose={onClose} title="Intro Drafts" maxWidth="max-w-xl">
      <div className="space-y-4">
        {intro.messages?.map((msg) => (
          <div key={msg.id} className="rounded-lg border border-slate-700/50 p-4">
            <div className="mb-2 flex items-center justify-between">
              <Badge color="amber">
                {msg.variant_label}
              </Badge>
              <span className="text-xs text-slate-500">{msg.ai_model_version}</span>
            </div>
            {msg.subject_line && (
              <p className="mb-1 text-xs text-slate-400">
                Subject: <span className="font-medium text-slate-300">{msg.subject_line}</span>
              </p>
            )}
            <p className="whitespace-pre-wrap text-sm text-slate-300">{msg.message_body}</p>
          </div>
        ))}
      </div>
    </Modal>
  );
}

/* ------------------------------------------------------------------ */
/* Company Card                                                       */
/* ------------------------------------------------------------------ */

function FitBadge({ score }) {
  if (score == null) return null;
  return <MatchBadge score={score} type="fit" />;
}

function CompanyCard({ company, onRequestIntro, onDraftIntro, introLoading }) {
  const ownPaths = company.referral_paths?.filter((p) => p.source === 'own_network') || [];
  const marketPaths = company.referral_paths?.filter((p) => p.source === 'marketplace') || [];
  const [showAll, setShowAll] = useState(false);

  const openings = company.active_openings || [];
  const visibleCount = showAll ? openings.length : Math.min(5, openings.length);
  const visibleOpenings = openings.slice(0, visibleCount);
  const hasHiddenOnPage = openings.length > 5 && !showAll;
  const totalMatched = company.total_matched_openings ?? openings.length;
  const hasMoreBeyondPage = company.has_mo[RESEND_KEY_REDACTED];

  // Determine which ATS source link to use for "view all"
  const atsSource = openings[0]?.source;
  const atsLabel = atsSource === 'greenhouse' ? 'Greenhouse' : atsSource === 'lever' ? 'Lever' : atsSource === 'ashby' ? 'Ashby' : 'their job board';

  return (
    <div className="rounded-xl bg-slate-900 border border-slate-700/50 shadow-sm">
      <div className="border-b border-slate-700/50 px-5 py-4 flex items-center justify-between">
        <h3 className="text-base font-semibold text-slate-50">{company.name}</h3>
        {company.careers_url && (
          <a
            href={company.careers_url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-amber-400 hover:text-amber-300"
          >
            Careers page &rarr;
          </a>
        )}
      </div>

      <div className="divide-y divide-slate-700/50 px-5">
        {/* Active Openings */}
        <div className="py-4">
          <h4 className="mb-2 text-xs font-medium uppercase tracking-wider text-slate-400">
            Live Openings
            {(company.job_scan_status === 'matched' || company.job_scan_status === 'discovered') && (
              <Badge color="emerald" className="ml-2 font-normal normal-case">
                {totalMatched} found
              </Badge>
            )}
            {company.job_scan_status === 'discovered' && (
              <Badge color="blue" className="ml-2 font-normal normal-case">
                auto-detected
              </Badge>
            )}
            {company.job_scan_status === 'no_match' && (
              <Badge color="slate" className="ml-2 font-normal normal-case">
                {company.total_jobs_fetched} scanned, 0 match your role
              </Badge>
            )}
            {company.job_scan_status === 'no_board' && (
              <span className="ml-2 rounded-full bg-slate-700/50 px-2 py-0.5 text-xs font-normal normal-case text-slate-500">
                job board not indexed
              </span>
            )}
          </h4>
          {visibleOpenings.length > 0 ? (
            <div className="space-y-2">
              {visibleOpenings.map((job, i) => (
                <div key={i} className="flex items-center justify-between text-sm">
                  <div className="flex items-center gap-2">
                    <FitBadge score={job.fit_score} />
                    <span className="text-slate-50">{job.title}</span>
                    {job.location && <span className="text-xs text-slate-500">{job.location}</span>}
                    {job.is_remote && <Badge color="blue" size="sm">Remote</Badge>}
                  </div>
                  {job.url && (
                    <a href={job.url} target="_blank" rel="noopener noreferrer" className="shrink-0 text-xs text-amber-400 hover:text-amber-300">
                      View &rarr;
                    </a>
                  )}
                </div>
              ))}
              {hasHiddenOnPage && (
                <button
                  onClick={() => setShowAll(true)}
                  aria-label={`Show ${openings.length - 5} more openings`}
                  className="mt-1 text-xs font-medium text-amber-400 hover:text-amber-300"
                >
                  Show {openings.length - 5} more
                </button>
              )}
              {showAll && hasMoreBeyondPage && company.careers_url && (
                <p className="mt-1 text-xs text-slate-400">
                  View all {totalMatched} openings on{' '}
                  <a href={company.careers_url} target="_blank" rel="noopener noreferrer" className="text-amber-400 hover:text-amber-300">
                    {atsLabel} &rarr;
                  </a>
                </p>
              )}
            </div>
          ) : company.careers_url ? (
            <p className="text-sm text-slate-500">
              No openings matching your role found.{' '}
              <a href={company.careers_url} target="_blank" rel="noopener noreferrer" className="text-amber-400 hover:text-amber-300">
                Browse all openings &rarr;
              </a>
            </p>
          ) : company.job_scan_status !== 'no_board' ? (
            <p className="text-sm text-slate-500">No openings matching your target role.</p>
          ) : (
            <p className="text-sm text-slate-500">This company's job board isn't in our index yet.</p>
          )}
        </div>

        {/* Own Network Paths */}
        {ownPaths.length > 0 && (
          <div className="py-4">
            <h4 className="mb-2 text-xs font-medium uppercase tracking-wider text-slate-400">Your Network</h4>
            <div className="space-y-2">
              {ownPaths.map((path, i) => (
                <div key={i} className="flex items-center justify-between rounded-lg border border-slate-700/50 bg-slate-800/50 p-3">
                  <div>
                    <p className="text-sm font-medium text-slate-50">
                      {path.contact.name} — {path.contact.title} at {path.contact.company}
                      {path.contact.relationship_type && (
                        <span className="ml-1 text-slate-500">({REL_LABELS[path.contact.relationship_type] || path.contact.relationship_type})</span>
                      )}
                    </p>
                    <div className="mt-1 flex flex-wrap gap-2">
                      <MatchBadge score={path.contact.warm_score} type="warm" showScore />
                      <LikelihoodBadge level={path.contact.referral_likelihood} />
                      {path.recommended_channel && (
                        <span className="text-xs text-slate-500">via {channelLabel(path.recommended_channel)}</span>
                      )}
                    </div>
                  </div>
                  <Button
                    onClick={() => onDraftIntro(path.contact.id)}
                    loading={introLoading === path.contact.id}
                    size="sm"
                  >
                    Draft Intro
                  </Button>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Marketplace Paths */}
        {marketPaths.length > 0 && (
          <div className="py-4">
            <h4 className="mb-2 text-xs font-medium uppercase tracking-wider text-slate-400">Via Marketplace</h4>
            <div className="space-y-2">
              {marketPaths.map((path, i) => (
                <div key={i} className="rounded-lg border border-dashed border-slate-600 bg-slate-800/30 p-3">
                  <div className="flex items-center gap-2 text-sm font-medium text-slate-50">
                    <MarketplaceBadge value={path.listing.role_level} type="role" />
                    <span>at {company.name}</span>
                  </div>
                  <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-slate-400">
                    {path.listing.department_category && <span>{path.listing.department_category}</span>}
                    {path.listing.department_category && <span>&middot;</span>}
                    <MarketplaceBadge value={path.listing.warm_sco[RESEND_KEY_REDACTED]} type="strength" />
                    {path.listing.connection_recency && <><span>&middot;</span><span>{path.listing.connection_recency}</span></>}
                  </div>
                  {path.network_holder_reputation && (
                    <p className="mt-1 text-xs text-slate-500">
                      Reputation: {path.network_holder_reputation.avg_rating?.toFixed(1) ?? '—'}
                      {' '}({path.network_holder_reputation.intros_facilitated} intros
                      {path.network_holder_reputation.response_rate != null && `, ${Math.round(path.network_holder_reputation.response_rate * 100)}% response`})
                    </p>
                  )}
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => onRequestIntro(path)}
                    className="mt-2"
                  >
                    Request Intro — 20 credits
                  </Button>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* No paths */}
        {ownPaths.length === 0 && marketPaths.length === 0 && (
          <div className="py-4 text-center text-sm text-slate-500">
            No referral paths found at {company.name}
          </div>
        )}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Main Page                                                          */
/* ------------------------------------------------------------------ */

export default function ReferralResults() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [searchMeta, setSearchMeta] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [balance, setBalance] = useState(0);
  const [introModal, setIntroModal] = useState(null);
  const [introLoading, setIntroLoading] = useState(null);
  const [draftModal, setDraftModal] = useState(null);
  const [alsoHiring, setAlsoHiring] = useState([]);
  const [showFeedback, setShowFeedback] = useState(false);

  useEffect(() => {
    const load = async () => {
      try {
        const [searchRes, balRes] = await Promise.all([
          searchApi.get(id),
          creditsApi.balance().catch(() => ({ data: { balance: 0 } })),
        ]);
        setData(searchRes.data);
        // The search object itself contains target_companies, name, etc.
        setSearchMeta({
          name: searchRes.data?.name,
          target_companies: searchRes.data?.target_companies,
        });
        setBalance(balRes.data?.balance ?? 0);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [id]);

  useEffect(() => {
    if (!data) return;
    const searched = (data.companies || data.results_data?.companies || [])
      .map((c) => c.name?.toLowerCase()).filter(Boolean);
    if (searched.length === 0) return;
    searchApi.recommendations({ exclude: searched.join(','), limit: 6 })
      .then((r) => setAlsoHiring(r.data?.recommendations ?? []))
      .catch(() => {});
    const timer = setTimeout(() => setShowFeedback(true), 5000);
    return () => clearTimeout(timer);
  }, [data]);

  const handleDraftIntro = async (contactId) => {
    setIntroLoading(contactId);
    try {
      const res = await matchesApi.createIntro({
        contact_id: contactId,
        tone: 'professional',
        channel: 'linkedin',
      });
      setDraftModal(res.data);
    } catch (err) {
      alert(err.message);
    } finally {
      setIntroLoading(null);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20" role="main" aria-live="polite" aria-busy="true">
        <Spinner size="lg" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="mx-auto max-w-2xl rounded-xl bg-red-500/10 p-6 text-center text-sm text-red-400" role="alert" aria-live="polite">
        {error}
      </div>
    );
  }

  const companies = data?.companies || data?.results_data?.companies || [];
  const summary = data?.summary || data?.results_data?.summary || {};
  const searchedNames = searchMeta?.target_companies || companies.map((c) => c.name);

  return (
    <div className="mx-auto max-w-3xl" role="main">
      <div className="mb-6 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-slate-50">Referral Results</h1>
          {searchedNames.length > 0 && (
            <p className="mt-1 text-sm text-slate-400">
              {searchedNames.join(', ')}
            </p>
          )}
          {summary.companies_searched != null && (
            <p className="text-xs text-slate-500">
              {summary.companies_searched} searched · {summary.total_referral_paths ?? 0} referral paths · {summary.total_openings ?? 0} openings
            </p>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <Link
            to="/help/scores"
            className="inline-flex items-center gap-1 rounded-md border border-slate-700/50 bg-slate-900 px-2 py-1 text-xs text-slate-400 hover:bg-slate-800"
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" d="M13 16h-1v-4h-1m1-4h.01M12 2a10 10 0 100 20 10 10 0 000-20z" />
            </svg>
            How scores work
          </Link>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => navigate('/referrals')}
          >
            New Search
          </Button>
        </div>
      </div>

      {companies.length === 0 ? (
        <div className="rounded-xl bg-slate-900 border border-slate-700/50 p-12 text-center">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-slate-800" aria-hidden="true">
            <svg className="h-7 w-7 text-slate-500" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z" />
            </svg>
          </div>
          <h2 className="mb-2 text-base font-semibold text-slate-50">No referral paths found</h2>
          <p className="mx-auto mb-4 max-w-sm text-sm text-slate-400">
            We couldn't find connections at these companies yet. This is a growing network — try different companies, or help grow it by sharing your own network.
          </p>
          <div className="flex items-center justify-center gap-3">
            <Button onClick={() => navigate('/referrals')}>
              Try Different Companies
            </Button>
            <Button variant="secondary" onClick={() => navigate('/settings?tab=sharing')}>
              Share Your Network
            </Button>
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          {companies.map((company, i) => (
            <CompanyCard
              key={i}
              company={company}
              onDraftIntro={handleDraftIntro}
              introLoading={introLoading}
              onRequestIntro={(path) => setIntroModal(path)}
            />
          ))}
        </div>
      )}

      {alsoHiring.length > 0 && (
        <div className="mt-6">
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-slate-400">
            Companies where you can get referred
          </h2>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {alsoHiring.map((rec) => (
              <button
                key={rec.company}
                onClick={() => navigate('/referrals')}
                className="group flex flex-col gap-1 rounded-lg border border-slate-700/50 bg-slate-900 p-3 text-left hover:border-amber-500/30 hover:bg-amber-500/5 transition-colors"
                aria-label={`Search referrals at ${rec.display_name}`}
              >
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-slate-200">
                    {rec.display_name}
                  </span>
                  {rec.referral_ready && (
                    <span className="rounded-full bg-amber-500/20 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-amber-400">
                      Referral Ready
                    </span>
                  )}
                </div>
                {rec.network_label && (
                  <span className="text-xs text-slate-400">{rec.network_label}</span>
                )}
                {rec.matching_count > 0 && (
                  <span className="text-xs text-slate-500">
                    {rec.matching_count} matching opening{rec.matching_count !== 1 ? 's' : ''}
                  </span>
                )}
                <span className="mt-1 text-xs text-amber-500/70 group-hover:text-amber-400">
                  {rec.matching_count > 0 ? 'View openings →' : rec.careers_url ? 'View careers →' : 'Search →'}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}

      {introModal && (
        <RequestIntroModal
          listing={introModal}
          creditBalance={balance}
          onClose={() => setIntroModal(null)}
          onSuccess={() => {
            setIntroModal(null);
            setBalance((b) => Math.max(0, b - 20));
          }}
        />
      )}

      {draftModal && <IntroModal intro={draftModal} onClose={() => setDraftModal(null)} />}

      {showFeedback && (
        <FeedbackModal
          feature="referral_search"
          resourceId={id}
          onClose={() => setShowFeedback(false)}
        />
      )}
    </div>
  );
}
