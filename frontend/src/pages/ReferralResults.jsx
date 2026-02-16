import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { search as searchApi, credits as creditsApi } from '../api/client';
import RequestIntroModal from '../components/RequestIntroModal';

function WarmBadge({ score }) {
  const color = score >= 70 ? 'bg-green-100 text-green-700' : score >= 40 ? 'bg-amber-100 text-amber-700' : 'bg-slate-100 text-slate-600';
  return <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${color}`}>Warm {score}</span>;
}

function LikelihoodBadge({ level }) {
  const map = { high: 'bg-green-100 text-green-700', medium: 'bg-amber-100 text-amber-700', low: 'bg-slate-100 text-slate-600' };
  return <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${map[level] || map.low}`}>{level}</span>;
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

function CompanyCard({ company, onRequestIntro, navigate }) {
  const ownPaths = company.referral_paths?.filter((p) => p.source === 'own_network') || [];
  const marketPaths = company.referral_paths?.filter((p) => p.source === 'marketplace') || [];

  return (
    <div className="rounded-xl bg-white shadow-sm ring-1 ring-slate-200">
      <div className="border-b border-slate-200 px-5 py-4">
        <h3 className="text-base font-semibold text-slate-900">{company.name}</h3>
      </div>

      <div className="divide-y divide-slate-100 px-5">
        {/* Active Openings */}
        {company.active_openings?.length > 0 && (
          <div className="py-4">
            <h4 className="mb-2 text-xs font-medium uppercase tracking-wider text-slate-500">Active Openings</h4>
            <div className="space-y-2">
              {company.active_openings.map((job, i) => (
                <div key={i} className="flex items-center justify-between text-sm">
                  <div>
                    <span className="text-slate-900">{job.title}</span>
                    {job.location && <span className="ml-2 text-xs text-slate-400">{job.location}</span>}
                    {job.is_remote && <span className="ml-2 rounded bg-blue-50 px-1.5 py-0.5 text-xs text-blue-600">Remote</span>}
                  </div>
                  {job.url && (
                    <a href={job.url} target="_blank" rel="noopener noreferrer" className="text-xs text-amber-600 hover:text-amber-700">
                      View &rarr;
                    </a>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

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
                    <div className="mt-1 flex gap-2">
                      <WarmBadge score={path.contact.warm_score} />
                      <LikelihoodBadge level={path.contact.referral_likelihood} />
                      {path.recommended_channel && (
                        <span className="text-xs text-slate-400">via {path.recommended_channel}</span>
                      )}
                    </div>
                  </div>
                  <button
                    onClick={() => navigate(`/search/${path.contact.id}`)}
                    className="shrink-0 rounded-md bg-amber-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-amber-600"
                  >
                    Draft Intro
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
                    {path.listing.warm_score_range} connection
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
        {ownPaths.length === 0 && marketPaths.length === 0 && !company.active_openings?.length && (
          <div className="py-4 text-center text-sm text-slate-400">
            No referral paths or openings found at {company.name}
          </div>
        )}
      </div>
    </div>
  );
}

export default function ReferralResults() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [balance, setBalance] = useState(0);
  const [introModal, setIntroModal] = useState(null);

  useEffect(() => {
    const load = async () => {
      try {
        const [searchRes, balRes] = await Promise.all([
          searchApi.get(id),
          creditsApi.balance().catch(() => ({ data: { balance: 0 } })),
        ]);
        setData(searchRes.data);
        setBalance(balRes.data?.balance ?? 0);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [id]);

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

  return (
    <div className="mx-auto max-w-3xl">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-900">Referral Results</h1>
          {summary.companies_searched != null && (
            <p className="text-sm text-slate-500">
              {summary.companies_searched} companies searched · {summary.total_referral_paths ?? 0} referral paths · {summary.total_openings ?? 0} openings
            </p>
          )}
        </div>
        <button
          onClick={() => navigate('/referrals')}
          className="rounded-md border border-slate-300 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50"
        >
          New Search
        </button>
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
              navigate={navigate}
              onRequestIntro={(path) => setIntroModal(path)}
            />
          ))}
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
    </div>
  );
}
