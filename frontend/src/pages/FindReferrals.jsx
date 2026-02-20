import { useEffect, useState } from 'react';
import { useNavigate, useLocation, Link } from 'react-router-dom';
import { search as searchApi, credits as creditsApi, preferences as prefsApi, companies as companiesApi } from '../api/client';
import CompanyAutocomplete from '../components/CompanyAutocomplete';
import { trackEvent } from '../utils/analytics';
import Button from '../components/ui/Button';

function ShimmerCard() {
  return (
    <div className="animate-pulse rounded-lg border border-slate-700/50 bg-slate-800 p-4" aria-hidden="true">
      <div className="mb-2 h-4 w-2/3 rounded bg-slate-700" />
      <div className="mb-3 h-3 w-1/3 rounded bg-slate-700" />
      <div className="mb-1 h-3 w-full rounded bg-slate-700" />
      <div className="h-3 w-3/4 rounded bg-slate-700" />
    </div>
  );
}

function RecommendationCard({ rec, onAdd, isAdded }) {
  const jobLabel =
    rec.matching_count > 0
      ? `${rec.matching_count} job${rec.matching_count !== 1 ? 's' : ''} matching your criteria`
      : null;
  return (
    <div className="surface-interactive p-4">
      <div className="flex items-start justify-between">
        <div className="min-w-0 flex-1">
          <p className="font-medium text-slate-50">{rec.display_name}</p>
          <div className="mt-1 flex flex-wrap gap-1.5">
            {rec.region && (
              <span className="inline-flex rounded-full bg-slate-700/50 px-2 py-0.5 text-xs text-slate-400">
                {rec.region}
              </span>
            )}
            {rec.network_label ? (
              <span className="inline-flex rounded-full bg-amber-500/10 px-2 py-0.5 text-xs font-medium text-amber-400">
                {rec.network_label}
              </span>
            ) : null}
            {jobLabel ? (
              <span className="inline-flex rounded-full bg-emerald-500/10 px-2 py-0.5 text-xs font-medium text-emerald-400">
                {jobLabel}
              </span>
            ) : null}
            {rec.referral_ready && (
              <span className="inline-flex rounded-full bg-amber-500/20 px-2 py-0.5 text-xs font-semibold text-amber-400">
                Referral Ready
              </span>
            )}
          </div>
          <div className="mt-2 space-y-0.5">
            {rec.top_titles?.slice(0, 2).map((title, i) => (
              <p key={i} className="truncate text-xs text-slate-400">{title}</p>
            ))}
          </div>
        </div>
        {isAdded ? (
          <span
            className="ml-3 shrink-0 rounded-md border border-emerald-500 bg-emerald-500/10 px-2.5 py-1 text-xs font-medium text-emerald-400"
            aria-label={`${rec.display_name} added`}
          >
            Added
          </span>
        ) : (
          <button
            onClick={() => onAdd(rec.display_name)}
            aria-label={`Add ${rec.display_name} to target companies`}
            className="ml-3 shrink-0 rounded-md border border-amber-500 px-2.5 py-1 text-xs font-medium text-amber-400 hover:bg-amber-500/10"
          >
            + Add
          </button>
        )}
      </div>
    </div>
  );
}

export default function FindReferrals() {
  const navigate = useNavigate();
  const location = useLocation();
  const [companies, setCompanies] = useState(() => location.state?.prefillCompanies ?? []);
  const [scope, setScope] = useState('own_network');
  const [balance, setBalance] = useState(null);
  const [hasPrefs, setHasPrefs] = useState(null);
  const [targetRole, setTargetRole] = useState(null);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState('');
  const [recommendations, setRecommendations] = useState([]);
  const [loadingRecs, setLoadingRecs] = useState(false);
  const [recsStale, setRecsStale] = useState(false);
  const [companyCounts, setCompanyCounts] = useState({});

  useEffect(() => {
    creditsApi.balance().then((r) => setBalance(r.data?.balance ?? 0)).catch(() => {});
    prefsApi.getJob().then((r) => {
      setHasPrefs(true);
      setTargetRole(r.data?.target_role ?? null);
    }).catch((e) => {
      setHasPrefs(e.status === 404 ? false : null);
    });
  }, []);

  useEffect(() => {
    if (hasPrefs !== true) return;
    setLoadingRecs(true);
    setRecsStale(false);

    // Show "still loading" message after 3 seconds
    const staleTimer = setTimeout(() => setRecsStale(true), 3000);

    searchApi.recommendations({ limit: 8 })
      .then((r) => setRecommendations(r.data?.recommendations ?? []))
      .catch(() => {})
      .finally(() => {
        clearTimeout(staleTimer);
        setLoadingRecs(false);
        setRecsStale(false);
      });

    return () => clearTimeout(staleTimer);
  }, [hasPrefs]);

  // Fetch connection counts for newly added companies
  useEffect(() => {
    const missing = companies.filter((c) => !(c in companyCounts));
    if (missing.length === 0) return;

    missing.forEach((name) => {
      companiesApi
        .search({ query: name, limit: 1 })
        .then((res) => {
          const match = (res.data ?? []).find(
            (c) => c.name.toLowerCase() === name.toLowerCase(),
          );
          setCompanyCounts((prev) => ({
            ...prev,
            [name]: match?.contact_count ?? 0,
          }));
        })
        .catch(() => {
          setCompanyCounts((prev) => ({ ...prev, [name]: 0 }));
        });
    });
  }, [companies, companyCounts]);

  // Computed values for scope toggle UI
  const companiesLoaded = companies.length > 0 && companies.every((c) => c in companyCounts);
  const totalOwnConnections = companies.reduce((sum, c) => sum + (companyCounts[c] ?? 0), 0);

  const handleAddRec = (name) => {
    if (!companies.includes(name)) {
      setCompanies((prev) => [...prev, name]);
    }
  };

  const handleSearch = async () => {
    if (companies.length === 0) return;
    setSearching(true);
    setError('');
    try {
      const res = await searchApi.smart({ company_names: companies, scope });
      trackEvent('search_performed');
      navigate(`/referrals/${res.data.id}`);
    } catch (err) {
      setError(err.message);
      setSearching(false);
    }
  };

  return (
    <div className="mx-auto max-w-2xl" role="main">
      <h1 className="page-title">Find Referral Paths</h1>
      <p className="page-subtitle mb-6">
        Search your network and the marketplace for people who can refer you.
      </p>

      <div className="mb-6 flex items-center gap-3 text-sm">
        <Link to="/marketplace/browse" className="text-amber-400 hover:text-amber-300">Browse Marketplace</Link>
        <span className="text-slate-600">&middot;</span>
        <Link to="/applications" className="text-slate-400 hover:text-slate-300">Track applications</Link>
        <span className="text-slate-600">&middot;</span>
        <Link to="/help/scores" className="text-slate-400 hover:text-slate-300">How scores work</Link>
      </div>

      {hasPrefs === false && (
        <div className="mb-4 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-400">
          You haven't set your job preferences yet. Results will be better if you{' '}
          <button onClick={() => navigate('/settings?tab=profile')} className="font-medium underline">
            set your target role
          </button>.
        </div>
      )}

      <div className="space-y-5 surface-raised p-6 shadow-sm">
        <div data-search-input>
          <CompanyAutocomplete
            value={companies}
            onChange={setCompanies}
            placeholder="e.g. Stripe, Figma, Shopify"
          />
        </div>

        {/* Connection count preview */}
        {companies.length > 0 && (
          <div className="space-y-1">
            {companies.map((name) => {
              const count = companyCounts[name];
              return (
                <p key={name} className="text-xs text-slate-500">
                  <span className="text-slate-400">{name}</span>
                  {' — '}
                  {count === undefined ? (
                    <span className="italic">checking...</span>
                  ) : count > 0 ? (
                    <span className="font-medium text-amber-400">
                      {count} {count === 1 ? 'connection' : 'connections'} in your network
                    </span>
                  ) : (
                    'no connections yet'
                  )}
                </p>
              );
            })}
          </div>
        )}

        {/* Scope toggle */}
        <div>
          <label id="search-scope-label" className="mb-2 block text-sm font-medium text-slate-300">Search Scope</label>
          <div className="grid grid-cols-2 gap-3" role="radiogroup" aria-labelledby="search-scope-label">
            <button
              type="button"
              role="radio"
              aria-checked={scope === 'own_network'}
              onClick={() => setScope('own_network')}
              className={`rounded-lg border-2 p-4 text-left transition ${
                scope === 'own_network' ? 'border-amber-500 bg-amber-500/10' : 'border-slate-700/50 hover:border-slate-600'
              }`}
            >
              <p className="font-medium text-slate-50">Your Network</p>
              <p className="mt-1 text-xs text-slate-400">Search your uploaded contacts</p>
              <div className="mt-2 flex items-center gap-2">
                <span className="text-xs font-medium text-emerald-400">Free</span>
              </div>
              {companies.length > 0 && totalOwnConnections > 0 && (
                <p className="mt-1.5 text-xs text-emerald-400">
                  {totalOwnConnections} {totalOwnConnections === 1 ? 'connection' : 'connections'} found
                </p>
              )}
            </button>
            <button
              type="button"
              role="radio"
              aria-checked={scope === 'marketplace'}
              onClick={() => setScope('marketplace')}
              className={`relative rounded-lg border-2 p-4 text-left transition ${
                scope === 'marketplace'
                  ? 'border-amber-500 bg-amber-500/10'
                  : 'border-amber-500/20 hover:border-amber-500/40'
              }`}
            >
              {scope !== 'marketplace' && (
                <span className="absolute top-2 right-2 rounded-full bg-amber-500/10 px-1.5 py-0.5 text-[10px] font-medium text-amber-400">
                  Recommended
                </span>
              )}
              <p className="font-medium text-slate-50">All Networks</p>
              <p className="mt-1 text-xs text-slate-400">Search across the entire marketplace</p>
              <div className="mt-2 flex items-center gap-2">
                <span className="text-xs font-medium text-amber-400">5 credits</span>
                {balance !== null && <span className="text-xs text-slate-500">({balance} available)</span>}
              </div>
              {scope !== 'marketplace' && (
                <p className="mt-1.5 text-xs text-amber-400/80">
                  Unlock 200+ additional referral paths
                </p>
              )}
            </button>
          </div>

          {/* Marketplace explainer */}
          {scope === 'marketplace' && (
            <p className="mt-2 flex items-center gap-1 text-xs text-slate-500">
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="currentColor" className="h-3 w-3 shrink-0">
                <path fillRule="evenodd" d="M8 1a3.5 3.5 0 0 0-3.5 3.5V7H3a1 1 0 0 0-1 1v5a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1V8a1 1 0 0 0-1-1h-1.5V4.5A3.5 3.5 0 0 0 8 1Zm2 6V4.5a2 2 0 1 0-4 0V7h4Z" clipRule="evenodd" />
              </svg>
              You'll see anonymized matches from other users' networks. 5 credits per search.
            </p>
          )}

          {/* Nudge to switch to marketplace when few/no connections */}
          {scope === 'own_network' && companies.length > 0 && companiesLoaded && totalOwnConnections <= 2 && (
            <div className="mt-2 flex items-center gap-2 text-sm text-amber-400">
              <span>
                Only {totalOwnConnections} {totalOwnConnections === 1 ? 'connection' : 'connections'} at{' '}
                {companies.length === 1 ? companies[0] : `${companies.length} companies`}.
                Switch to All Networks to find 200+ more paths.
              </span>
              <button
                type="button"
                onClick={() => setScope('marketplace')}
                className="shrink-0 font-medium hover:text-amber-300"
              >
                Switch &rarr;
              </button>
            </div>
          )}
        </div>

        {error && <p role="alert" aria-live="polite" className="rounded-md bg-red-500/10 p-2 text-sm text-red-400">{error}</p>}

        <Button
          onClick={handleSearch}
          disabled={companies.length === 0}
          loading={searching}
          className="w-full"
          size="lg"
        >
          Find Referral Paths
        </Button>
      </div>

      {/* Recommendations section */}
      {(loadingRecs || recommendations.length > 0) && (
        <div className="mt-8">
          <div className="mb-3 flex items-center gap-2">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-400">
              Hiring {targetRole ? `for "${targetRole}"` : 'for Your Role'}
            </h2>
            <button
              onClick={() => navigate('/settings?tab=profile')}
              className="text-xs text-amber-400 hover:text-amber-300"
              aria-label="Edit target role"
            >
              Edit
            </button>
          </div>
          {loadingRecs && recsStale && (
            <p className="mb-2 text-xs text-slate-500" aria-live="polite">
              Scanning job boards — this may take a moment...
            </p>
          )}
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {loadingRecs
              ? Array.from({ length: 4 }).map((_, i) => <ShimmerCard key={i} />)
              : recommendations.map((rec) => (
                  <RecommendationCard
                    key={rec.company}
                    rec={rec}
                    onAdd={handleAddRec}
                    isAdded={companies.includes(rec.display_name)}
                  />
                ))}
          </div>
        </div>
      )}
    </div>
  );
}
