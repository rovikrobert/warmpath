import { useEffect, useState } from 'react';
import { useNavigate, useLocation, Link } from 'react-router-dom';
import { search as searchApi, credits as creditsApi, preferences as prefsApi, companies as companiesApi } from '../api/client';
import CompanyAutocomplete from '../components/CompanyAutocomplete';
import { trackEvent } from '../utils/analytics';
import {
  getCreditInsufficientMessage,
  getRateLimitMessage,
  isCreditInsufficientError,
} from '../utils/errorCopy';
import Button from '../components/ui/Button';
import useDocumentTitle from '../hooks/useDocumentTitle';

const SEARCH_SCOPE_EXPERIMENT_KEY = 'warmpath_search_scope_v1';

function getExperimentVariant(): 'control' | 'treatment' {
  if (typeof window === 'undefined') return 'control';
  const saved = window.localStorage.getItem(SEARCH_SCOPE_EXPERIMENT_KEY);
  if (saved === 'control' || saved === 'treatment') return saved;
  const assigned = Math.random() < 0.5 ? 'control' : 'treatment';
  window.localStorage.setItem(SEARCH_SCOPE_EXPERIMENT_KEY, assigned);
  return assigned;
}

function ShimmerCard() {
  return (
    <div className="animate-pulse rounded-lg border border-border bg-muted p-4" aria-hidden="true">
      <div className="mb-2 h-4 w-2/3 rounded bg-muted" />
      <div className="mb-3 h-3 w-1/3 rounded bg-muted" />
      <div className="mb-1 h-3 w-full rounded bg-muted" />
      <div className="h-3 w-3/4 rounded bg-muted" />
    </div>
  );
}

function RecommendationCard({ rec, onAdd, isAdded }) {
  const jobLabel =
    rec.matching_count > 0
      ? `${rec.matching_count} job${rec.matching_count !== 1 ? 's' : ''} matching your criteria`
      : 'No matching jobs found';
  const jobBadgeStyle =
    rec.matching_count > 0
      ? 'bg-emerald-500/10 text-emerald-400'
      : 'bg-muted/50 text-muted-foreground';
  return (
    <div className="surface-interactive p-4">
      <div className="flex items-start justify-between">
        <div className="min-w-0 flex-1">
          <p className="font-medium text-foreground">{rec.display_name}</p>
          <div className="mt-1 flex flex-wrap gap-1.5">
            {rec.region && (
              <span className="inline-flex rounded-full bg-muted/50 px-2 py-0.5 text-xs text-muted-foreground">
                {rec.region}
              </span>
            )}
            {rec.network_label ? (
              <span className="inline-flex rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">
                {rec.network_label}
              </span>
            ) : null}
            <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${jobBadgeStyle}`}>
              {jobLabel}
            </span>
            {rec.referral_ready && (
              <span className="inline-flex rounded-full bg-primary/20 px-2 py-0.5 text-xs font-semibold text-primary">
                Referral Ready
              </span>
            )}
          </div>
          <div className="mt-2 space-y-0.5">
            {rec.top_titles?.slice(0, 2).map((title, i) => (
              <p key={i} className="truncate text-xs text-muted-foreground">{title}</p>
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
            className="ml-3 shrink-0 rounded-md border border-primary px-2.5 py-1 text-xs font-medium text-primary hover:bg-primary/10"
          >
            + Add
          </button>
        )}
      </div>
    </div>
  );
}

export default function FindReferrals() {
  useDocumentTitle('Find Referrals');
  const navigate = useNavigate();
  const location = useLocation();
  const [companies, setCompanies] = useState(() => location.state?.prefillCompanies ?? []);
  const [scope, setScope] = useState('own_network');
  const [scopeTouched, setScopeTouched] = useState(false);
  const [experimentVariant] = useState<'control' | 'treatment'>(() => getExperimentVariant());
  const [balance, setBalance] = useState(null);
  const [hasPrefs, setHasPrefs] = useState(null);
  const [targetRole, setTargetRole] = useState(null);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState('');
  const [showCreditsCta, setShowCreditsCta] = useState(false);
  const [recommendations, setRecommendations] = useState([]);
  const [loadingRecs, setLoadingRecs] = useState(false);
  const [companyCounts, setCompanyCounts] = useState({});
  const [discoveryStatus, setDiscoveryStatus] = useState({});
  const [shownNudgeKey, setShownNudgeKey] = useState<string | null>(null);

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
    trackEvent('search_scope_experiment_assigned', { experiment_variant: experimentVariant });
  }, [experimentVariant]);

  useEffect(() => {
    if (hasPrefs !== true) return;
    setLoadingRecs(true);

    let retryTimer;
    searchApi.recommendations({ limit: 8 })
      .then((r) => {
        setRecommendations(r.data?.recommendations ?? []);
        // If backend is warming uncached companies, silently refresh after 6s
        const uncached = r.data?.scan_stats?.uncached_count ?? 0;
        if (uncached > 0) {
          retryTimer = setTimeout(() => {
            searchApi.recommendations({ limit: 8 })
              .then((r2) => setRecommendations(r2.data?.recommendations ?? []))
              .catch(() => {});
          }, 6000);
        }
      })
      .catch(() => {})
      .finally(() => setLoadingRecs(false));

    return () => clearTimeout(retryTimer);
  }, [hasPrefs]);

  // Fetch connection counts for newly added companies
  useEffect(() => {
    setCompanyCounts((prev) => {
      const missing = companies.filter((c) => !(c in prev));
      if (missing.length === 0) return prev;

      missing.forEach((name) => {
        companiesApi
          .search({ query: name, limit: 5 })
          .then((res) => {
            const results = res.data ?? [];
            // Sum contact counts across all name variants (e.g. "Meta" matches
            // "Meta", "Meta Platforms", "Meta Platforms Inc" in the Company table)
            const count = results.reduce((sum, c) => sum + (c.contact_count ?? 0), 0);
            setCompanyCounts((p) => ({ ...p, [name]: count }));
          })
          .catch(() => {
            setCompanyCounts((p) => ({ ...p, [name]: 0 }));
          });
      });
      return prev;
    });
  }, [companies]);

  // Discover jobs at newly added companies
  useEffect(() => {
    setDiscoveryStatus((prev) => {
      const undiscovered = companies.filter((c) => !(c in prev));
      if (undiscovered.length === 0) return prev;

      undiscovered.forEach((name) => {
        setDiscoveryStatus((p) => ({ ...p, [name]: { status: 'discovering' } }));
        companiesApi
          .discover(name)
          .then((res) => {
            const d = res.data ?? {};
            setDiscoveryStatus((p) => ({
              ...p,
              [name]: {
                status: d.jobs_found > 0 ? 'found' : 'not_found',
                jobsCount: d.jobs_found ?? 0,
                careersUrl: d.careers_url,
              },
            }));
          })
          .catch(() => {
            setDiscoveryStatus((p) => ({
              ...p,
              [name]: { status: 'not_found', jobsCount: 0 },
            }));
          });
      });
      return prev;
    });
  }, [companies]);

  // Computed values for scope toggle UI
  const companiesLoaded = companies.length > 0 && companies.every((c) => c in companyCounts);
  const totalOwnConnections = companies.reduce((sum, c) => sum + (companyCounts[c] ?? 0), 0);
  const targetsWithCoverage = companies.reduce((sum, c) => sum + ((companyCounts[c] ?? 0) > 0 ? 1 : 0), 0);
  const coverageRate = companies.length > 0 ? targetsWithCoverage / companies.length : 0;
  const canAffordMarketplace = balance !== null && balance >= 5;
  const lowCoverageWithoutCredits = coverageRate < 0.2 && balance !== null && balance < 5;
  const recommendedScope = coverageRate < 0.2 && canAffordMarketplace ? 'marketplace' : 'own_network';
  const shouldShowLowCoverageNudge = (
    experimentVariant === 'treatment' &&
    scope === 'own_network' &&
    companies.length > 0 &&
    companiesLoaded &&
    recommendedScope === 'marketplace'
  );

  useEffect(() => {
    if (experimentVariant !== 'treatment') return;
    if (companies.length === 0 || !companiesLoaded) return;
    if (scopeTouched) return;
    if (recommendedScope !== 'marketplace') return;
    if (scope === 'marketplace') return;

    setScope('marketplace');
    trackEvent('search_scope_auto_selected', {
      experiment_variant: experimentVariant,
      selected_scope: 'marketplace',
      reason: coverageRate === 0 ? 'zero_coverage' : 'low_coverage',
      coverage_rate: coverageRate,
      total_targets: companies.length,
      targets_with_coverage: targetsWithCoverage,
    });
  }, [experimentVariant, companies.length, companiesLoaded, scopeTouched, recommendedScope, scope, coverageRate, targetsWithCoverage]);

  useEffect(() => {
    if (!shouldShowLowCoverageNudge) return;
    const nudgeKey = `${companies.slice().sort().join('|')}::${targetsWithCoverage}`;
    if (shownNudgeKey === nudgeKey) return;
    trackEvent('marketplace_nudge_shown', {
      experiment_variant: experimentVariant,
      nudge_type: coverageRate === 0 ? 'zero_coverage' : 'low_coverage',
      coverage_rate: coverageRate,
      total_targets: companies.length,
      targets_with_coverage: targetsWithCoverage,
      selected_scope: scope,
    });
    setShownNudgeKey(nudgeKey);
  }, [shouldShowLowCoverageNudge, companies, targetsWithCoverage, shownNudgeKey, experimentVariant, coverageRate, scope]);

  const handleAddRec = (name) => {
    if (!companies.includes(name)) {
      setCompanies((prev) => [...prev, name]);
    }
  };

  const selectScope = (nextScope: 'own_network' | 'marketplace', source: 'manual' | 'nudge' = 'manual') => {
    setScope(nextScope);
    setScopeTouched(true);
    trackEvent('search_scope_selected', {
      experiment_variant: experimentVariant,
      selected_scope: nextScope,
      source,
      coverage_rate: coverageRate,
      total_targets: companies.length,
      targets_with_coverage: targetsWithCoverage,
    });
    if (source === 'nudge' && nextScope === 'marketplace') {
      trackEvent('marketplace_nudge_accepted', {
        experiment_variant: experimentVariant,
        previous_scope: scope,
        new_scope: 'marketplace',
        coverage_rate: coverageRate,
        total_targets: companies.length,
        targets_with_coverage: targetsWithCoverage,
      });
    }
  };

  const handleSearch = async () => {
    if (companies.length === 0) return;
    if (hasPrefs === false) {
      setError('Set your target role first so we can match you to the right referrals.');
      setShowCreditsCta(false);
      return;
    }
    setSearching(true);
    setError('');
    setShowCreditsCta(false);
    try {
      const res = await searchApi.smart({ company_names: companies, scope });
      trackEvent('search_scope_decision', {
        experiment_variant: experimentVariant,
        selected_scope: scope,
        recommended_scope: recommendedScope,
        followed_recommendation: scope === recommendedScope,
        coverage_rate: coverageRate,
        total_targets: companies.length,
        targets_with_coverage: targetsWithCoverage,
      });
      trackEvent('search_performed', {
        scope,
        experiment_variant: experimentVariant,
      });
      navigate(`/referrals/${res.data.id}`);
    } catch (err) {
      const msg = err?.message || 'Search failed';
      if (msg.toLowerCase().includes('set job preferences first')) {
        setError('Set your target role first so we can match you to the right referrals.');
      } else if (isCreditInsufficientError(err)) {
        setError(getCreditInsufficientMessage(err, msg));
        setShowCreditsCta(true);
      } else if (err?.status === 429 || msg.toLowerCase().includes('limit')) {
        setError(getRateLimitMessage(err, 'Search failed'));
      } else {
        setError(msg);
      }
    } finally {
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
        <Link to="/applications" className="text-muted-foreground hover:text-secondary-foreground">Track applications</Link>
        <span className="text-muted-foreground">&middot;</span>
        <Link to="/help/scores" className="text-muted-foreground hover:text-secondary-foreground">How scores work</Link>
      </div>

      {hasPrefs === false && (
        <div className="mb-4 rounded-lg border border-primary/30 bg-primary/10 p-3 text-sm text-primary">
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

        {/* Connection count + discovery status preview */}
        {companies.length > 0 && (
          <div className="space-y-1" aria-live="polite">
            {companies.map((name) => {
              const count = companyCounts[name];
              const discovery = discoveryStatus[name];
              return (
                <div key={name} className="text-xs text-muted-foreground">
                  <p>
                    <span className="text-muted-foreground">{name}</span>
                    {' — '}
                    {count === undefined ? (
                      <span className="italic">checking...</span>
                    ) : count > 0 ? (
                      <span className="font-medium text-primary">
                        {count} {count === 1 ? 'connection' : 'connections'} in your network
                      </span>
                    ) : (
                      'no connections yet'
                    )}
                  </p>
                  {discovery && (
                    <p className="ml-0">
                      {discovery.status === 'discovering' && (
                        <span className="italic text-muted-foreground">Discovering jobs at {name}...</span>
                      )}
                      {discovery.status === 'found' && (
                        <span className="text-emerald-400">{discovery.jobsCount} job{discovery.jobsCount !== 1 ? 's' : ''} found</span>
                      )}
                      {discovery.status === 'not_found' && (
                        <span className="text-muted-foreground">
                          No listings found.{' '}
                          {discovery.careersUrl && (
                            <a
                              href={discovery.careersUrl}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-primary hover:text-primary"
                            >
                              Try their careers page ↗
                            </a>
                          )}
                        </span>
                      )}
                    </p>
                  )}
                </div>
              );
            })}
          </div>
        )}

        {/* Scope toggle */}
        <div>
          <label id="search-scope-label" className="mb-2 block text-sm font-medium text-secondary-foreground">Search Scope</label>
          <div className="grid grid-cols-2 gap-3" role="radiogroup" aria-labelledby="search-scope-label">
            <button
              type="button"
              role="radio"
              aria-checked={scope === 'own_network'}
              onClick={() => selectScope('own_network')}
              className={`rounded-lg border-2 p-4 text-left transition ${
                scope === 'own_network' ? 'border-primary bg-primary/10' : 'border-border hover:border-border'
              }`}
            >
              <p className="font-medium text-foreground">Your Network</p>
              <p className="mt-1 text-xs text-muted-foreground">Search your uploaded contacts</p>
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
              onClick={() => selectScope('marketplace')}
              className={`relative rounded-lg border-2 p-4 text-left transition ${
                scope === 'marketplace'
                  ? 'border-primary bg-primary/10'
                  : 'border-primary/20 hover:border-primary/40'
              }`}
            >
              {scope !== 'marketplace' && (
                <span className="absolute top-2 right-2 rounded-full bg-primary/10 px-1.5 py-0.5 text-[10px] font-medium text-primary">
                  Recommended
                </span>
              )}
              <p className="font-medium text-foreground">All Networks</p>
              <p className="mt-1 text-xs text-muted-foreground">Search across the entire marketplace</p>
              <div className="mt-2 flex items-center gap-2">
                <span className="text-xs font-medium text-primary">5 credits</span>
                {balance !== null && <span className="text-xs text-muted-foreground">({balance} available)</span>}
              </div>
              {scope !== 'marketplace' && (
                <p className="mt-1.5 text-xs text-primary/80">
                  Unlock 200+ additional referral paths
                </p>
              )}
            </button>
          </div>

          {/* Marketplace explainer */}
          {scope === 'marketplace' && (
            <p className="mt-2 flex items-center gap-1 text-xs text-muted-foreground">
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="currentColor" className="h-3 w-3 shrink-0">
                <path fillRule="evenodd" d="M8 1a3.5 3.5 0 0 0-3.5 3.5V7H3a1 1 0 0 0-1 1v5a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1V8a1 1 0 0 0-1-1h-1.5V4.5A3.5 3.5 0 0 0 8 1Zm2 6V4.5a2 2 0 1 0-4 0V7h4Z" clipRule="evenodd" />
              </svg>
              You'll see anonymized matches from other users' networks. 5 credits per search.
            </p>
          )}

          {/* Nudge to switch to marketplace when few/no connections */}
          {shouldShowLowCoverageNudge && (
            <div className="mt-2 flex items-center gap-2 text-sm text-primary">
              <span>
                {coverageRate === 0
                  ? `No direct connections found at ${companies.length === 1 ? companies[0] : `${companies.length} target companies`}.`
                  : `Only ${targetsWithCoverage} of ${companies.length} target companies have direct connections.`}{' '}
                Switch to All Networks to find 200+ more paths.
              </span>
              <button
                type="button"
                onClick={() => selectScope('marketplace', 'nudge')}
                className="shrink-0 font-medium hover:text-primary"
              >
                Switch &rarr;
              </button>
            </div>
          )}

          {scope === 'own_network' && companies.length > 0 && companiesLoaded && lowCoverageWithoutCredits && (
            <div className="mt-2 text-sm text-amber-400">
              Your own-network coverage is limited for these companies. All Networks costs 5 credits per search. Upload contacts to earn free credits, or buy credits.
              <Link to="/credits" className="ml-1 font-medium text-amber-300 hover:text-amber-200">
                Get credits &rarr;
              </Link>
            </div>
          )}
        </div>

        {error && (
          <div role="alert" aria-live="polite" className="rounded-md bg-red-500/10 p-2 text-sm text-red-400">
            <p>{error}</p>
            {showCreditsCta && (
              <Link to="/credits" className="mt-1 inline-block font-medium text-red-300 hover:text-red-200">
                Go to Credits &rarr;
              </Link>
            )}
          </div>
        )}

        <Button
          onClick={handleSearch}
          disabled={companies.length === 0 || hasPrefs === false}
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
            <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
              Hiring {targetRole ? `for "${targetRole}"` : 'for Your Role'}
            </h2>
            <button
              onClick={() => navigate('/settings?tab=profile')}
              className="text-xs text-primary hover:text-primary"
              aria-label="Edit target role"
            >
              Edit
            </button>
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {loadingRecs
              ? Array.from({ length: 4 }).map((_, i) => <ShimmerCard key={i} />)
              : recommendations.map((rec) => (
                  <RecommendationCard
                    key={rec.display_name || rec.company}
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
