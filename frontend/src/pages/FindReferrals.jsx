import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { search as searchApi, credits as creditsApi, preferences as prefsApi } from '../api/client';
import TagInput from '../components/TagInput';

export default function FindReferrals() {
  const navigate = useNavigate();
  const [companies, setCompanies] = useState([]);
  const [scope, setScope] = useState('own_network');
  const [balance, setBalance] = useState(null);
  const [hasPrefs, setHasPrefs] = useState(null);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    creditsApi.balance().then((r) => setBalance(r.data?.balance ?? 0)).catch(() => {});
    prefsApi.getJob().then(() => setHasPrefs(true)).catch((e) => {
      setHasPrefs(e.status === 404 ? false : null);
    });
  }, []);

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
    <div className="mx-auto max-w-2xl">
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
          <label className="mb-2 block text-sm font-medium text-slate-700">Search Scope</label>
          <div className="grid grid-cols-2 gap-3">
            <button
              type="button"
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

        {error && <p className="rounded-md bg-red-50 p-2 text-sm text-red-600">{error}</p>}

        <button
          onClick={handleSearch}
          disabled={companies.length === 0 || searching}
          className="w-full rounded-lg bg-amber-500 py-2.5 text-sm font-medium text-white hover:bg-amber-600 disabled:opacity-50"
        >
          {searching ? 'Searching...' : 'Find Referral Paths'}
        </button>
      </div>
    </div>
  );
}
