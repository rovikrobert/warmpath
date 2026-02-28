import { useEffect, useState, useMemo } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { search as searchApi, preferences as prefsApi } from '../api/client';
import DashboardSkeleton from '../components/skeletons/DashboardSkeleton';
import useDocumentTitle from '../hooks/useDocumentTitle';

function ShimmerCard() {
  return (
    <div className="animate-pulse surface-raised p-5" aria-hidden="true">
      <div className="mb-3 h-5 w-1/2 rounded bg-muted" />
      <div className="mb-2 h-4 w-2/3 rounded bg-muted" />
      <div className="mb-4 h-3 w-1/3 rounded bg-muted" />
      <div className="h-8 w-24 rounded bg-muted" />
    </div>
  );
}

function CompanyCard({ rec, onSearch }) {
  const marketplacePaths = Math.max(0, (rec.network_density ?? 0) - (rec.own_contacts ?? 0));
  const hasOwn = (rec.own_contacts ?? 0) > 0;

  return (
    <div className="surface-raised p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="text-lg font-medium text-foreground">{rec.display_name}</p>
          {rec.region && (
            <span className="mt-1 inline-block rounded-full bg-muted/50 px-2 py-0.5 text-xs text-muted-foreground">
              {rec.region}
            </span>
          )}
        </div>
        {rec.referral_ready && (
          <span className="shrink-0 rounded-full bg-primary/20 px-2 py-0.5 text-xs font-semibold text-primary">
            Referral Ready
          </span>
        )}
      </div>

      <p className="mt-2 text-sm text-primary">
        {rec.network_density} referral {rec.network_density === 1 ? 'path' : 'paths'}
      </p>

      {/* Network comparison */}
      {(hasOwn || marketplacePaths > 0) && (
        <p className="mt-1 text-xs text-muted-foreground">
          {hasOwn && (
            <span>Your network: {rec.own_contacts}</span>
          )}
          {hasOwn && marketplacePaths > 0 && (
            <span className="mx-1.5 text-muted-foreground">|</span>
          )}
          {marketplacePaths > 0 && (
            <span className="text-primary/70">Marketplace: {marketplacePaths} more</span>
          )}
        </p>
      )}

      {/* Job openings */}
      {rec.matching_count > 0 && (
        <p className="mt-1 text-xs text-emerald-400">
          {rec.matching_count} open {rec.matching_count === 1 ? 'role' : 'roles'} matching your criteria
        </p>
      )}

      {/* Top titles */}
      {rec.top_titles?.length > 0 && (
        <div className="mt-2">
          {rec.top_titles.slice(0, 2).map((title, i) => (
            <p key={i} className="truncate text-xs text-muted-foreground">{title}</p>
          ))}
        </div>
      )}

      <button
        onClick={() => onSearch(rec.display_name)}
        className="mt-3 rounded-md bg-primary/10 px-3 py-2.5 text-sm font-medium text-primary hover:bg-primary/20 transition-colors"
        aria-label={`Search referral paths at ${rec.display_name}`}
      >
        Search
      </button>
    </div>
  );
}

export default function MarketplaceBrowse() {
  useDocumentTitle('Browse Marketplace');
  const navigate = useNavigate();
  const [recommendations, setRecommendations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [hasPrefs, setHasPrefs] = useState(null);
  const [filter, setFilter] = useState('');

  useEffect(() => {
    prefsApi.getJob()
      .then(() => setHasPrefs(true))
      .catch((e) => setHasPrefs(e.status === 404 ? false : null));
  }, []);

  useEffect(() => {
    if (hasPrefs !== true) {
      if (hasPrefs !== null) setLoading(false);
      return;
    }
    setLoading(true);
    searchApi.recommendations({ limit: 20 })
      .then((r) => setRecommendations(r.data?.recommendations ?? []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [hasPrefs]);

  const filtered = useMemo(() => {
    if (!filter.trim()) return recommendations;
    const q = filter.toLowerCase();
    return recommendations.filter((r) =>
      r.display_name.toLowerCase().includes(q),
    );
  }, [recommendations, filter]);

  const handleSearch = (companyName) => {
    navigate('/referrals', { state: { prefillCompanies: [companyName] } });
  };

  if (loading) {
    return <DashboardSkeleton />;
  }

  return (
    <div role="main">
      <div className="mb-1">
        <h1 className="page-title">Marketplace</h1>
        <p className="page-subtitle">Browse referral paths across all networks</p>
      </div>

      <div className="mb-6 flex flex-wrap items-center gap-3 text-sm">
        <Link to="/referrals" className="text-muted-foreground hover:text-secondary-foreground">Find Referrals</Link>
        <span className="text-muted-foreground">&middot;</span>
        <Link to="/marketplace" className="text-muted-foreground hover:text-secondary-foreground">Marketplace Overview</Link>
      </div>

      {hasPrefs === false ? (
        <div className="surface-raised p-8 text-center">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-muted" aria-hidden="true">
            <svg className="h-7 w-7 text-muted-foreground" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 6a3.75 3.75 0 1 1-7.5 0 3.75 3.75 0 0 1 7.5 0ZM4.501 20.118a7.5 7.5 0 0 1 14.998 0A17.933 17.933 0 0 1 12 21.75c-2.676 0-5.216-.584-7.499-1.632Z" />
            </svg>
          </div>
          <h2 className="mb-2 text-base font-semibold text-foreground">Set your job preferences first</h2>
          <p className="mx-auto mb-4 max-w-sm text-sm text-muted-foreground">
            We need your target role to find companies that are hiring and have referral paths available.
          </p>
          <Link
            to="/settings?tab=profile"
            className="inline-block rounded-lg bg-primary px-6 py-2.5 text-sm font-medium text-white hover:bg-primary/90"
          >
            Set Target Role
          </Link>
        </div>
      ) : (
        <>
          {/* Search filter */}
          <div className="mb-6">
            <input
              type="text"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="Filter companies..."
              aria-label="Filter companies"
              className="w-full rounded-lg border border-border bg-muted px-4 py-2.5 text-sm text-foreground placeholder:text-muted-foreground focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring sm:max-w-sm"
            />
          </div>

          {filtered.length === 0 ? (
            <div className="surface-raised p-8 text-center">
              <p className="text-sm text-muted-foreground">
                {filter
                  ? `No companies matching "${filter}"`
                  : 'No marketplace data available yet. Try uploading your contacts first.'}
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
              {filtered.map((rec) => (
                <CompanyCard key={rec.company} rec={rec} onSearch={handleSearch} />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
