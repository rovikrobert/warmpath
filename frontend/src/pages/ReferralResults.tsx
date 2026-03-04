import { useEffect, useState } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { search as searchApi, credits as creditsApi, matches as matchesApi } from '../api/client';
import RequestIntroModal from '../components/RequestIntroModal';
import FeedbackModal from '../components/FeedbackModal';
import MatchBadge from '../components/MatchBadge';
import { MarketplaceBadge } from '../utils/marketplace';
import ScoreExplainer from '../components/ScoreExplainer';
import { WARM_TIERS } from '../utils/scores';
import Modal from '../components/ui/Modal';
import Button from '../components/ui/Button';
import Badge from '../components/ui/Badge';
import Spinner from '../components/ui/Spinner';
import { useToast } from '../components/ui/Toast';
import useDocumentTitle from '../hooks/useDocumentTitle';

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

const STEP_LABELS: Record<string, string> = {
  reconnect: 'Reconnect',
  explore: 'Feel it out',
  referral_ask: 'The Ask',
};

function IntroModal({ intro, onClose, contactName, linkedinUrl }) {
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
        {messages.map((msg, idx) => {
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
                  <Badge color="slate">{label}</Badge>
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
                  <Button
                    size="sm"
                    onClick={() => copyAndOpenLinkedIn(msg)}
                    aria-label={`Copy message and open LinkedIn profile for ${contactName || 'contact'}`}
                  >
                    {isCopied ? 'Copied! Opening LinkedIn...' : 'Copy & Open LinkedIn'}
                  </Button>
                ) : (
                  <Button
                    size="sm"
                    onClick={() => copyMessage(msg)}
                    aria-label="Copy message to clipboard"
                  >
                    {isCopied ? 'Copied!' : 'Copy Message'}
                  </Button>
                )}
                {linkedinUrl && (
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => copyMessage(msg)}
                    aria-label="Copy message to clipboard"
                  >
                    {isCopied ? 'Copied!' : 'Copy Only'}
                  </Button>
                )}
              </div>
            </div>
          );
        })}
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

function CompanyCard({ company, onRequestIntro, onDraftIntro, introLoading, searchScope }) {
  const ownPaths = company.referral_paths?.filter((p) => p.source === 'own_network') || [];
  const marketPaths = company.referral_paths?.filter((p) => p.source === 'marketplace') || [];
  const [showAll, setShowAll] = useState(false);

  const openings = company.active_openings || [];
  const visibleCount = showAll ? openings.length : Math.min(5, openings.length);
  const visibleOpenings = openings.slice(0, visibleCount);
  const hasHiddenOnPage = openings.length > 5 && !showAll;
  const totalMatched = company.total_matched_openings ?? openings.length;
  const hasMoreBeyondPage = company.has_more_openings;

  // Determine which ATS source link to use for "view all"
  const atsSource = openings[0]?.source;
  const atsLabel = atsSource === 'greenhouse' ? 'Greenhouse' : atsSource === 'lever' ? 'Lever' : atsSource === 'ashby' ? 'Ashby' : 'their job board';

  return (
    <div className="rounded-xl bg-card border border-border shadow-sm">
      <div className="border-b border-border px-5 py-4 flex items-center justify-between">
        <h3 className="text-base font-semibold text-foreground">{company.name}</h3>
        {company.careers_url && (
          <a
            href={company.careers_url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-primary hover:text-primary"
          >
            Careers page &rarr;
          </a>
        )}
      </div>

      <div className="divide-y divide-border px-5">
        {/* Active Openings */}
        <div className="py-4">
          <h4 className="mb-2 text-xs font-medium uppercase tracking-wider text-muted-foreground">
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
              <span className="ml-2 rounded-full bg-muted/50 px-2 py-0.5 text-xs font-normal normal-case text-muted-foreground">
                job board not indexed
              </span>
            )}
          </h4>
          {visibleOpenings.length > 0 ? (
            <div className="space-y-2">
              {visibleOpenings.map((job, i) => {
                // Show divider before the first out-of-region job
                const showRegionDivider =
                  job.in_target_region === false &&
                  (i === 0 || visibleOpenings[i - 1]?.in_target_region !== false);
                return (
                  <div key={i}>
                    {showRegionDivider && (
                      <p className="py-1 text-xs text-muted-foreground italic">
                        No more openings in your target region — showing other locations
                      </p>
                    )}
                    <div className="flex items-center justify-between text-sm">
                      <div className="flex items-center gap-2">
                        <FitBadge score={job.fit_score} />
                        <span className="text-foreground">{job.title}</span>
                        {job.location && <span className="text-xs text-muted-foreground">{job.location}</span>}
                        {job.is_remote && <Badge color="blue" size="sm">Remote</Badge>}
                      </div>
                      {job.url && (
                        <a href={job.url} target="_blank" rel="noopener noreferrer" className="shrink-0 text-xs text-primary hover:text-primary">
                          View &rarr;
                        </a>
                      )}
                    </div>
                  </div>
                );
              })}
              {hasHiddenOnPage && (
                <button
                  onClick={() => setShowAll(true)}
                  aria-label={`Show ${openings.length - 5} more openings`}
                  className="mt-1 text-xs font-medium text-primary hover:text-primary"
                >
                  Show {openings.length - 5} more
                </button>
              )}
              {showAll && hasMoreBeyondPage && company.careers_url && (
                <p className="mt-1 text-xs text-muted-foreground">
                  View all {totalMatched} openings on{' '}
                  <a href={company.careers_url} target="_blank" rel="noopener noreferrer" className="text-primary hover:text-primary">
                    {atsLabel} &rarr;
                  </a>
                </p>
              )}
            </div>
          ) : company.careers_url ? (
            <p className="text-sm text-muted-foreground">
              No openings matching your role found.{' '}
              <a href={company.careers_url} target="_blank" rel="noopener noreferrer" className="text-primary hover:text-primary">
                Browse all openings &rarr;
              </a>
            </p>
          ) : company.job_scan_status !== 'no_board' ? (
            <p className="text-sm text-muted-foreground">No openings matching your target role.</p>
          ) : (
            <p className="text-sm text-muted-foreground">This company's job board isn't in our index yet.</p>
          )}
        </div>

        {/* Own Network Paths */}
        {ownPaths.length > 0 && (
          <div className="py-4">
            <h4 className="mb-2 text-xs font-medium uppercase tracking-wider text-muted-foreground">Your Network</h4>
            <div className="space-y-2">
              {ownPaths.map((path, i) => (
                <div key={i} className="flex items-center justify-between gap-3 rounded-lg border border-border bg-muted/50 p-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <p className="truncate text-sm font-medium text-foreground" title={path.contact.name}>
                        {path.contact.name}
                      </p>
                      <MatchBadge score={path.contact.warm_score} type="warm" />
                      <ScoreExplainer
                        title="Connection Score"
                        body="Your connection strength with this person. Higher means they're more likely to help."
                        tiers={WARM_TIERS}
                        learnMoreHref="/help/scores#connection-score"
                      />
                    </div>
                    <p className="truncate text-xs text-muted-foreground" title={`${path.contact.title} at ${path.contact.company}`}>
                      {path.contact.title} · {path.contact.company}
                    </p>
                    {path.contact.relationship_type && (
                      <p className="text-xs text-muted-foreground">
                        {REL_LABELS[path.contact.relationship_type] || path.contact.relationship_type}
                      </p>
                    )}
                  </div>
                  <Button
                    onClick={() => onDraftIntro(path.contact)}
                    loading={introLoading === path.contact.id}
                    size="sm"
                    className="shrink-0"
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
            <h4 className="mb-2 text-xs font-medium uppercase tracking-wider text-muted-foreground">Via Marketplace</h4>
            <div className="space-y-2">
              {marketPaths.map((path, i) => (
                <div key={i} className="rounded-lg border border-dashed border-border bg-muted/30 p-3">
                  <div className="flex items-center gap-2 text-sm font-medium text-foreground">
                    <MarketplaceBadge value={path.listing.role_level} type="role" />
                    <span>at {company.name}</span>
                  </div>
                  <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                    {path.listing.department_category && <span>{path.listing.department_category}</span>}
                    {path.listing.department_category && <span>&middot;</span>}
                    <MarketplaceBadge value={path.listing.warm_score_range} type="strength" />
                    <ScoreExplainer
                      title="Connection Strength"
                      body="The network holder's relationship strength with this contact. Stronger connections lead to better intro outcomes."
                      learnMoreHref="/help/scores#warm-score"
                    />
                    {path.listing.connection_recency && <><span>&middot;</span><span>{path.listing.connection_recency}</span></>}
                  </div>
                  {path.network_holder_reputation && (
                    <p className="mt-1 text-xs text-muted-foreground">
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

        {/* Empty marketplace state — searched marketplace but no results */}
        {searchScope === 'marketplace' && marketPaths.length === 0 && (
          <div className="py-4">
            <h4 className="mb-2 text-xs font-medium uppercase tracking-wider text-muted-foreground">Via Marketplace</h4>
            <p className="text-sm text-muted-foreground">
              No additional connections at {company.name} in the marketplace yet. As more people share their networks, new referral paths will appear here.
            </p>
          </div>
        )}

        {/* No paths */}
        {ownPaths.length === 0 && marketPaths.length === 0 && (
          <div className="py-4 text-center text-sm text-muted-foreground">
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
  useDocumentTitle('Referral Results');
  const { id } = useParams();
  const navigate = useNavigate();
  const toast = useToast();
  const [data, setData] = useState(null);
  const [searchMeta, setSearchMeta] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [balance, setBalance] = useState(0);
  const [introModal, setIntroModal] = useState<any>(null);
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

  const handleDraftIntro = async (contact) => {
    setIntroLoading(contact.id);
    try {
      const res = await matchesApi.createIntro({
        contact_id: contact.id,
        tone: 'professional',
        channel: 'linkedin',
      });
      setDraftModal({
        ...res.data,
        contactName: contact.name,
        linkedinUrl: contact.linkedin_url,
      });
    } catch (err) {
      toast.error(err.message);
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
      <div className="mx-auto max-w-2xl rounded-xl bg-destructive/10 p-6 text-center text-sm text-destructive" role="alert" aria-live="polite">
        {error}
      </div>
    );
  }

  const companies = data?.companies || data?.results_data?.companies || [];
  const summary = data?.summary || data?.results_data?.summary || {};
  const searchScope = data?.scope || data?.results_data?.scope || 'own_network';
  const searchedNames = searchMeta?.target_companies || companies.map((c) => c.name);

  return (
    <div className="mx-auto max-w-3xl" role="main">
      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-xl font-bold text-foreground">Referral Results</h1>
          {searchedNames.length > 0 && (
            <p className="mt-1 text-sm text-muted-foreground">
              {searchedNames.join(', ')}
            </p>
          )}
          {summary.companies_searched != null && (
            <p className="text-xs text-muted-foreground">
              {summary.companies_searched} searched · {summary.total_referral_paths ?? 0} referral paths · {summary.total_openings ?? 0} openings
            </p>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <Link
            to="/help/scores"
            className="inline-flex items-center gap-1 rounded-md border border-border bg-card px-2 py-1 text-xs text-muted-foreground hover:bg-muted"
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
        <div className="rounded-xl bg-card border border-border p-12 text-center">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-muted" aria-hidden="true">
            <svg className="h-7 w-7 text-muted-foreground" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z" />
            </svg>
          </div>
          <h2 className="mb-2 text-base font-semibold text-foreground">No referral paths found</h2>
          <p className="mx-auto mb-4 max-w-sm text-sm text-muted-foreground">
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
              searchScope={searchScope}
              onDraftIntro={handleDraftIntro}
              introLoading={introLoading}
              onRequestIntro={(path) => setIntroModal(path)}
            />
          ))}
        </div>
      )}

      {alsoHiring.length > 0 && (
        <div className="mt-6">
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-muted-foreground">
            Companies where you can get referred
          </h2>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {alsoHiring.map((rec) => (
              <button
                key={rec.company}
                onClick={() => navigate('/referrals')}
                className="group flex flex-col gap-1 rounded-lg border border-border bg-card p-3 text-left hover:border-primary/30 hover:bg-primary/5 transition-colors"
                aria-label={`Search referrals at ${rec.display_name}`}
              >
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-foreground">
                    {rec.display_name}
                  </span>
                  {rec.referral_ready && (
                    <span className="rounded-full bg-primary/20 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-primary">
                      Referral Ready
                    </span>
                  )}
                </div>
                {rec.network_label && (
                  <span className="text-xs text-muted-foreground">{rec.network_label}</span>
                )}
                {rec.matching_count > 0 && (
                  <span className="text-xs text-muted-foreground">
                    {rec.matching_count} matching opening{rec.matching_count !== 1 ? 's' : ''}
                  </span>
                )}
                <span className="mt-1 text-xs text-primary/70 group-hover:text-primary">
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
            window.dispatchEvent(new Event('journey-updated'));
          }}
        />
      )}

      {draftModal && (
        <IntroModal
          intro={draftModal}
          onClose={() => setDraftModal(null)}
          contactName={draftModal.contactName}
          linkedinUrl={draftModal.linkedinUrl}
        />
      )}

      {showFeedback && import.meta.env.VITE_BETA_MODE !== 'true' && (
        <FeedbackModal
          feature="referral_search"
          resourceId={id}
          onClose={() => setShowFeedback(false)}
        />
      )}
    </div>
  );
}
