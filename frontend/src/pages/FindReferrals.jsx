import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { search as searchApi, credits as creditsApi, preferences as prefsApi } from '../api/client';
import TagInput from '../components/TagInput';

function ShimmerCard() {
  return (
    <div className="animate-pulse rounded-lg border border-slate-200 bg-white p-4" aria-hidden="true">
      <div className="mb-2 h-4 w-2/3 rounded bg-slate-200" />
      <div className="mb-3 h-3 w-1/3 rounded bg-slate-100" />
      <div className="mb-1 h-3 w-full rounded bg-slate-100" />
      <div className="h-3 w-3/4 rounded bg-slate-100" />
    </div>
  );
}

function RecommendationCard({ rec, onAdd }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4">
      <div className="flex items-start justify-between">
        <div className="min-w-0 flex-1">
          <p className="font-medium text-slate-900">{rec.display_name}</p>
          <div className="mt-1 flex flex-wrap gap-1.5">
            {rec.region && (
              <span className="inline-flex rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-500">
                {rec.region}
              </span>
            )}
            <span className="inline-flex rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-700">
              {rec.matching_count} matching
            </span>
          </div>
          <div className="mt-2 space-y-0.5">
            {rec.top_titles?.slice(0, 2).map((title, i) => (
              <p key={i} className="truncate text-xs text-slate-500">{title}</p>
            ))}
          </div>
        </div>
        <button
          onClick={() => onAdd(rec.display_name)}
          aria-label={`Add ${rec.display_name} to target companies`}
          className="ml-3 shrink-0 rounded-md border border-amber-500 px-2.5 py-1 text-xs font-medium text-amber-600 hover:bg-amber-50"
        >
          + Add
        </button>
      </div>
    </div>
  );
}

export default function FindReferrals() {
  const navigate = useNavigate();
  const [companies, setCompanies] = useState([]);
  const [scope, setScope] = useState('own_network');
  const [balance, setBalance] = useState(null);
  const [hasPrefs, setHasPrefs] = useState(null);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState('');
  const [recommendations, setRecommendations] = useState([]);
  const [loadingRecs, setLoadingRecs] = useState(false);
  const [recsStale, setRecsStale] = useState(false);

  useEffect(() => {
    creditsApi.balance().then((r) => setBalance(r.data?.balance ?? 0)).catch(() => {});
    prefsApi.getJob().then(() => setHasPrefs(true)).catch((e) => {
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
      navigate(`/referrals/${res.data.id}`);
    } catch (err) {
      setError(err.message);
      setSearching(false);
    }
  };

  return (
    <div className="mx-auto max-w-2xl" role="main">
      <h1 className="mb-1 text-xl font-bold text-slate-900">Find Referral Paths</h1>
      <p className="mb-6 text-sm text-slate-500">
        Search your network and the marketplace for people who can refer you.
      </p>

      {hasPrefs === false && (
        <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
          You haven't set your job preferences yet. Results will be better if you{' '}
          <button onClick={() => navigate('/profile/edit')} className="font-medium underline">
            set your target role
          </button>.
        </div>
      )}

      <div className="space-y-5 rounded-xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
        <TagInput
          label="Target Companies"
          value={companies}
          onChange={setCompanies}
          placeholder="e.g. Stripe, Figma, Shopify"
        />

        {/* Scope toggle */}
        <div>
          <label id="search-scope-label" className="mb-2 block text-sm font-medium text-slate-700">Search Scope</label>
          <div className="grid grid-cols-2 gap-3" role="radiogroup" aria-labelledby="search-scope-label">
            <button
              type="button"
              role="radio"
              aria-checked={scope === 'own_network'}
              onClick={() => setScope('own_network')}
              className={`rounded-lg border-2 p-4 text-left transition ${
                scope === 'own_network' ? 'border-amber-500 bg-amber-50' : 'border-slate-200 hover:border-slate-300'
              }`}
            >
              <p className="font-medium text-slate-900">My network only</p>
              <p className="mt-1 text-xs text-slate-500">Search your uploaded contacts</p>
              <p className="mt-2 text-xs font-medium text-green-600">Free</p>
            </button>
            <button
              type="button"
              role="radio"
              aria-checked={scope === 'marketplace'}
              onClick={() => setScope('marketplace')}
              className={`rounded-lg border-2 p-4 text-left transition ${
                scope === 'marketplace' ? 'border-amber-500 bg-amber-50' : 'border-slate-200 hover:border-slate-300'
              }`}
            >
              <p className="font-medium text-slate-900">+ Marketplace</p>
              <p className="mt-1 text-xs text-slate-500">Also search other people's networks</p>
              <p className="mt-2 text-xs font-medium text-amber-600">
                5 credits {balance !== null && <span className="text-slate-400">({balance} available)</span>}
              </p>
            </button>
          </div>
        </div>

        {error && <p role="alert" aria-live="polite" className="rounded-md bg-red-50 p-2 text-sm text-red-600">{error}</p>}

        <button
          onClick={handleSearch}
          disabled={companies.length === 0 || searching}
          className="w-full rounded-lg bg-amber-500 py-2.5 text-sm font-medium text-white hover:bg-amber-600 disabled:opacity-50"
        >
          {searching ? 'Searching...' : 'Find Referral Paths'}
        </button>
      </div>

      {/* Recommendations section */}
      {(loadingRecs || recommendations.length > 0) && (
        <div className="mt-8">
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-slate-500">
            Hiring for Your Role
          </h2>
          {loadingRecs && recsStale && (
            <p className="mb-2 text-xs text-slate-400" aria-live="polite">
              Scanning job boards — this may take a moment...
            </p>
          )}
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {loadingRecs
              ? Array.from({ length: 4 }).map((_, i) => <ShimmerCard key={i} />)
              : recommendations.map((rec) => (
                  <RecommendationCard key={rec.company} rec={rec} onAdd={handleAddRec} />
                ))}
          </div>
        </div>
      )}
    </div>
  );
}
