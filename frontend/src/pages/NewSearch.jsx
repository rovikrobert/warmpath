import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { search as searchApi } from '../api/client';
import TagInput from '../components/TagInput';

export default function NewSearch() {
  const navigate = useNavigate();
  const [form, setForm] = useState({
    name: '',
    description: '',
    target_roles: [],
    target_companies: [],
    target_industries: [],
    target_locations: [],
    min_score: 40,
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const set = (key) => (e) => setForm({ ...form, [key]: e.target.value });
  const setTags = (key) => (tags) => setForm({ ...form, [key]: tags });

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.name.trim()) {
      setError('Search name is required');
      return;
    }
    if (form.target_roles.length === 0 && form.target_companies.length === 0 && form.target_industries.length === 0) {
      setError('Add at least one target role, company, or industry');
      return;
    }

    setLoading(true);
    setError('');
    try {
      // Create the search
      const createRes = await searchApi.create(form);
      const searchId = createRes.data.id;

      // Immediately run it
      await searchApi.run(searchId);

      // Navigate to results
      navigate(`/search/${searchId}`);
    } catch (err) {
      setError(err.message);
      setLoading(false);
    }
  };

  const inputClass = 'w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500';

  return (
    <div className="mx-auto max-w-2xl" role="main">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold text-slate-900">New Search</h1>
        <button
          onClick={() => navigate('/dashboard')}
          className="text-sm text-amber-600 hover:text-amber-700"
        >
          &larr; Back to Dashboard
        </button>
      </div>

      <form onSubmit={handleSubmit} className="space-y-5 rounded-xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
        <p className="text-sm text-slate-500">
          Define who you're looking for. WarmPath will search your network and score each contact by relevance and warmth.
        </p>

        <div>
          <label htmlFor="search-name" className="mb-1 block text-sm font-medium text-slate-700">Search Name</label>
          <input
            id="search-name"
            type="text"
            value={form.name}
            onChange={set('name')}
            className={inputClass}
            placeholder="e.g. Series A Founders in Singapore"
            required
            aria-required="true"
          />
        </div>

        <div>
          <label htmlFor="search-description" className="mb-1 block text-sm font-medium text-slate-700">Description</label>
          <textarea
            id="search-description"
            value={form.description}
            onChange={set('description')}
            rows={2}
            className={inputClass}
            placeholder="Looking for early-stage founders to partner with on GTM strategy..."
          />
        </div>

        <TagInput
          label="Target Roles"
          value={form.target_roles}
          onChange={setTags('target_roles')}
          placeholder="e.g. CEO, VP Sales, Head of Marketing"
        />

        <TagInput
          label="Target Companies"
          value={form.target_companies}
          onChange={setTags('target_companies')}
          placeholder="e.g. Stripe, Shopify, HubSpot"
        />

        <TagInput
          label="Target Industries"
          value={form.target_industries}
          onChange={setTags('target_industries')}
          placeholder="e.g. SaaS, FinTech, Professional Services"
        />

        <TagInput
          label="Target Locations"
          value={form.target_locations}
          onChange={setTags('target_locations')}
          placeholder="e.g. Singapore, San Francisco, London"
        />

        <div>
          <label htmlFor="search-min-score" className="mb-1 block text-sm font-medium text-slate-700">
            Minimum Score: {form.min_score}
          </label>
          <input
            id="search-min-score"
            type="range"
            min="0"
            max="100"
            step="5"
            value={form.min_score}
            onChange={(e) => setForm({ ...form, min_score: Number(e.target.value) })}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={form.min_score}
            aria-label={`Minimum score: ${form.min_score}`}
            className="w-full accent-amber-500"
          />
          <div className="flex justify-between text-xs text-slate-400">
            <span>0 — Include all</span>
            <span>100 — Only perfect matches</span>
          </div>
        </div>

        {error && <p role="alert" aria-live="polite" className="rounded-md bg-red-50 p-2 text-sm text-red-600">{error}</p>}

        <button
          type="submit"
          disabled={loading}
          className="w-full rounded-lg bg-amber-500 py-2.5 text-sm font-medium text-white hover:bg-amber-600 disabled:opacity-50"
        >
          {loading ? 'Creating & running search...' : 'Create & Run Search'}
        </button>
      </form>
    </div>
  );
}
