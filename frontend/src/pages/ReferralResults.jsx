import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { search as searchApi, credits as creditsApi, matches as matchesApi } from '../api/client';
import RequestIntroModal from '../components/RequestIntroModal';

/* ------------------------------------------------------------------ */
/* Warm Score legend + badge                                          */
/* ------------------------------------------------------------------ */

const WARM_TIERS = [
  { min: 70, label: 'Strong', color: 'bg-green-100 text-green-700', desc: 'Recent contact, strong relationship — ideal referral path' },
  { min: 40, label: 'Moderate', color: 'bg-amber-100 text-amber-700', desc: 'Some connection — may need a warm-up message first' },
  { min: 0, label: 'Weak', color: 'bg-slate-100 text-slate-600', desc: 'Distant or old connection — consider building rapport before asking' },
];

function warmTier(score) {
  return WARM_TIERS.find((t) => score >= t.min) || WARM_TIERS[2];
}

function WarmBadge({ score }) {
  const tier = warmTier(score);
  return (
    <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${tier.color}`}>
      {tier.label} ({score})
    </span>
  );
}

function WarmScoreLegend() {
  const [open, setOpen] = useState(false);
  return (
    <div className="relative inline-block">
      <button
        onClick={() => setOpen(!open)}
        className="inline-flex items-center gap-1 rounded-md border border-slate-200 bg-white px-2 py-1 text-xs text-slate-500 hover:bg-slate-50"
      >
        <svg xmlns="http://www.w3.org/2000/svg" className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M13 16h-1v-4h-1m1-4h.01M12 2a10 10 0 100 20 10 10 0 000-20z" />
        </svg>
        What are warm scores?
      </button>
      {open && (
        <div className="absolute right-0 z-10 mt-1 w-72 rounded-lg border border-slate-200 bg-white p-4 shadow-lg">
          <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-700">Warm Score Guide</h4>
          <p className="mb-3 text-xs text-slate-500">
            Measures how likely this person is to respond to your referral request, based on recency of contact, relationship strength, role relevance, and tenure.
          </p>
          <div className="space-y-2">
            {WARM_TIERS.map((tier) => (
              <div key={tier.label} className="flex items-start gap-2">
                <span className={`mt-0.5 shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${tier.color}`}>
                  {tier.min}+
                </span>
                <div>
                  <span className="text-xs font-medium text-slate-700">{tier.label}</span>
                  <p className="text-xs text-slate-400">{tier.desc}</p>
                </div>
              </div>
            ))}
          </div>
          <button onClick={() => setOpen(false)} className="mt-3 text-xs text-amber-600 hover:text-amber-700">
            Got it
          </button>
        </div>
      )}
    </div>
  );
}

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
  const map = { high: 'bg-green-100 text-green-700', medium: 'bg-amber-100 text-amber-700', low: 'bg-slate-100 text-slate-600' };
  const labels = { high: 'High likelihood', medium: 'Medium likelihood', low: 'Low likelihood' };
  return <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${map[level] || map.low}`}>{labels[level] || level}</span>;
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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="w-full max-w-xl rounded-xl bg-white shadow-xl">
        <div className="flex items-center justify-between border-b border-slate-200 px-6 py-4">
          <h2 className="text-lg font-semibold text-slate-900">Intro Drafts</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600 text-xl leading-none">&times;</button>
        </div>
        <div className="max-h-[70vh] overflow-y-auto px-6 py-4 space-y-4">
          {intro.messages?.map((msg) => (
            <div key={msg.id} className="rounded-lg border border-slate-200 p-4">
              <div className="mb-2 flex items-center justify-between">
                <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-700">
                  {msg.variant_label}
                </span>
                <span className="text-xs text-slate-400">{msg.ai_model_version}</span>
              </div>
              {msg.subject_line && (
                <p className="mb-1 text-xs text-slate-500">
                  Subject: <span className="font-medium text-slate-700">{msg.subject_line}</span>
                </p>
              )}
              <p className="whitespace-pre-wrap text-sm text-slate-700">{msg.message_body}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Company Card                                                       */
/* ------------------------------------------------------------------ */

function FitBadge({ score }) {
  if (score == null) return null;
  const color = score >= 80 ? 'bg-green-50 text-green-600' : score >= 50 ? 'bg-amber-50 text-amber-600' : 'bg-slate-50 text-slate-500';
  return <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${color}`}>{score}</span>;
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
    <div className="rounded-xl bg-white shadow-sm ring-1 ring-slate-200">
      <div className="border-b border-slate-200 px-5 py-4 flex items-center justify-between">
        <h3 className="text-base font-semibold text-slate-900">{company.name}</h3>
        {company.careers_url && (
          <a
            href={company.careers_url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-amber-600 hover:text-amber-700"
          >
            Careers page &rarr;
          </a>
        )}
      </div>

      <div className="divide-y divide-slate-100 px-5">
        {/* Active Openings */}
        <div className="py-4">
          <h4 className="mb-2 text-xs font-medium uppercase tracking-wider text-slate-500">
            Live Openings
            {(company.job_scan_status === 'matched' || company.job_scan_status === 'discovered') && (
              <span className="ml-2 rounded-full bg-green-100 px-2 py-0.5 text-xs font-normal normal-case text-green-700">
                {totalMatched} found
              </span>
            )}
            {company.job_scan_status === 'discovered' && (
              <span className="ml-2 rounded-full bg-blue-100 px-2 py-0.5 text-xs font-normal normal-case text-blue-600">
                auto-detected
              </span>
            )}
            {company.job_scan_status === 'no_match' && (
              <span className="ml-2 rounded-full bg-slate-100 px-2 py-0.5 text-xs font-normal normal-case text-slate-500">
                {company.total_jobs_fetched} scanned, 0 match your role
              </span>
            )}
            {company.job_scan_status === 'no_board' && (
              <span className="ml-2 rounded-full bg-slate-100 px-2 py-0.5 text-xs font-normal normal-case text-slate-400">
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
                    <span className="text-slate-900">{job.title}</span>
                    {job.location && <span className="text-xs text-slate-400">{job.location}</span>}
                    {job.is_remote && <span className="rounded bg-blue-50 px-1.5 py-0.5 text-xs text-blue-600">Remote</span>}
                  </div>
                  {job.url && (
                    <a href={job.url} target="_blank" rel="noopener noreferrer" className="shrink-0 text-xs text-amber-600 hover:text-amber-700">
                      View &rarr;
                    </a>
                  )}
                </div>
              ))}
              {hasHiddenOnPage && (
                <button
                  onClick={() => setShowAll(true)}
                  className="mt-1 text-xs font-medium text-amber-600 hover:text-amber-700"
                >
                  Show {openings.length - 5} more
                </button>
              )}
              {showAll && hasMoreBeyondPage && company.careers_url && (
                <p className="mt-1 text-xs text-slate-500">
                  View all {totalMatched} openings on{' '}
                  <a href={company.careers_url} target="_blank" rel="noopener noreferrer" className="text-amber-600 hover:text-amber-700">
                    {atsLabel} &rarr;
                  </a>
                </p>
              )}
            </div>
          ) : company.careers_url ? (
            <p className="text-sm text-slate-400">
              No openings matching your role found.{' '}
              <a href={company.careers_url} target="_blank" rel="noopener noreferrer" className="text-amber-600 hover:text-amber-700">
                Browse all openings &rarr;
              </a>
            </p>
          ) : company.job_scan_status !== 'no_board' ? (
            <p className="text-sm text-slate-400">No openings matching your target role.</p>
          ) : (
            <p className="text-sm text-slate-400">This company's job board isn't in our index yet.</p>
          )}
        </div>

        {/* Own Network Paths */}
        {ownPaths.length > 0 && (
          <div className="py-4">
            <h4 className="mb-2 text-xs font-medium uppercase tracking-wider text-slate-500">Your Network</h4>
            <div className="space-y-2">
              {ownPaths.map((path, i) => (
                <div key={i} className="flex items-center justify-between rounded-lg border border-slate-100 p-3">
                  <div>
                    <p className="text-sm font-medium text-slate-900">
                      {path.contact.name} — {path.contact.title} at {path.contact.company}
                      {path.contact.relationship_type && (
                        <span className="ml-1 text-slate-400">({REL_LABELS[path.contact.relationship_type] || path.contact.relationship_type})</span>
                      )}
                    </p>
                    <div className="mt-1 flex flex-wrap gap-2">
                      <WarmBadge score={path.contact.warm_score} />
                      <LikelihoodBadge level={path.contact.referral_likelihood} />
                      {path.recommended_channel && (
                        <span className="text-xs text-slate-400">Reach out via {channelLabel(path.recommended_channel)}</span>
                      )}
                    </div>
                  </div>
                  <button
                    onClick={() => onDraftIntro(path.contact.id)}
                    disabled={introLoading === path.contact.id}
                    className="shrink-0 rounded-md bg-amber-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-amber-600 disabled:opacity-50"
                  >
                    {introLoading === path.contact.id ? 'Drafting...' : 'Draft Intro'}
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Marketplace Paths */}
        {marketPaths.length > 0 && (
          <div className="py-4">
            <h4 className="mb-2 text-xs font-medium uppercase tracking-wider text-slate-500">Via Marketplace</h4>
            <div className="space-y-2">
              {marketPaths.map((path, i) => (
                <div key={i} className="rounded-lg border border-dashed border-slate-200 bg-slate-50/50 p-3">
                  <p className="text-sm font-medium text-slate-900">
                    {path.listing.role_level} at {company.name}
                  </p>
                  <p className="text-xs text-slate-500">
                    {path.listing.department_category && `${path.listing.department_category} · `}
                    {path.listing.warm_sco[RESEND_KEY_REDACTED]} connection
                    {path.listing.connection_recency && ` · ${path.listing.connection_recency}`}
                  </p>
                  {path.network_holder_reputation && (
                    <p className="mt-1 text-xs text-slate-400">
                      Reputation: {path.network_holder_reputation.avg_rating?.toFixed(1) ?? '—'}
                      {' '}({path.network_holder_reputation.intros_facilitated} intros
                      {path.network_holder_reputation.response_rate != null && `, ${Math.round(path.network_holder_reputation.response_rate * 100)}% response`})
                    </p>
                  )}
                  <button
                    onClick={() => onRequestIntro(path)}
                    className="mt-2 rounded-md border border-amber-500 px-3 py-1.5 text-xs font-medium text-amber-600 hover:bg-amber-50"
                  >
                    Request Intro — 20 credits
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* No paths */}
        {ownPaths.length === 0 && marketPaths.length === 0 && (
          <div className="py-4 text-center text-sm text-slate-400">
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
      <div className="flex items-center justify-center py-20">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-amber-500 border-t-transparent" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="mx-auto max-w-2xl rounded-xl bg-red-50 p-6 text-center text-sm text-red-600">
        {error}
      </div>
    );
  }

  const companies = data?.companies || data?.results_data?.companies || [];
  const summary = data?.summary || data?.results_data?.summary || {};
  const searchedNames = searchMeta?.target_companies || companies.map((c) => c.name);

  return (
    <div className="mx-auto max-w-3xl">
      <div className="mb-6 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-slate-900">Referral Results</h1>
          {searchedNames.length > 0 && (
            <p className="mt-1 text-sm text-slate-600">
              {searchedNames.join(', ')}
            </p>
          )}
          {summary.companies_searched != null && (
            <p className="text-xs text-slate-400">
              {summary.companies_searched} searched · {summary.total_referral_paths ?? 0} referral paths · {summary.total_openings ?? 0} openings
            </p>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <WarmScoreLegend />
          <button
            onClick={() => navigate('/referrals')}
            className="rounded-md border border-slate-300 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50"
          >
            New Search
          </button>
        </div>
      </div>

      {companies.length === 0 ? (
        <div className="rounded-xl bg-white p-12 text-center ring-1 ring-slate-200">
          <p className="text-sm text-slate-500">No results found. Try different companies or expand to marketplace scope.</p>
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
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-slate-500">
            Also hiring for your role
          </h2>
          <div className="flex flex-wrap gap-2">
            {alsoHiring.map((rec) => (
              <button
                key={rec.company}
                onClick={() => navigate('/referrals')}
                className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-sm text-slate-700 hover:border-amber-300 hover:bg-amber-50"
              >
                {rec.display_name}
                <span className="text-xs text-slate-400">{rec.matching_count} openings</span>
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
    </div>
  );
}
