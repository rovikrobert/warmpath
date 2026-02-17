import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { marketplace as mpApi, contacts as contactsApi } from '../api/client';

const DEPARTMENT_OPTIONS = [
  'Engineering', 'Product', 'Design', 'Marketing', 'Sales',
  'Finance', 'Operations', 'HR / People', 'Legal', 'Data / Analytics',
  'Customer Success', 'Executive', 'Other',
];

export default function SharingSettings() {
  const [prefs, setPrefs] = useState(null);
  const [contacts, setContacts] = useState([]);
  const [excludedIds, setExcludedIds] = useState([]);
  const [categoryFilters, setCategoryFilters] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');

  useEffect(() => {
    const load = async () => {
      try {
        const [prefsRes, contactsRes] = await Promise.all([
          mpApi.getSharingPrefs().catch(() => ({ data: { opt_in_marketplace: false, is_paused: false } })),
          contactsApi.list(1, 500).catch(() => ({ data: [] })),
        ]);
        const p = prefsRes.data;
        setPrefs(p);
        setCategoryFilters(p.category_filters?.include_departments || []);
        setExcludedIds(p.excluded_contact_ids || []);
        setContacts(contactsRes.data || []);
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  const handleSave = async () => {
    setSaving(true);
    setSaved(false);
    try {
      const body = {
        opt_in_marketplace: prefs.opt_in_marketplace,
        is_paused: prefs.is_paused,
        category_filters: categoryFilters.length > 0 ? { include_departments: categoryFilters } : null,
        excluded_contact_ids: excludedIds.length > 0 ? excludedIds : null,
      };
      const res = await mpApi.updateSharingPrefs(body);
      setPrefs(res.data);
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (err) {
      console.error(err);
    } finally {
      setSaving(false);
    }
  };

  const toggleDepartment = (dept) => {
    setCategoryFilters((prev) =>
      prev.includes(dept) ? prev.filter((d) => d !== dept) : [...prev, dept]
    );
  };

  const toggleExclude = (id) => {
    setExcludedIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  };

  const filteredContacts = contacts.filter((c) => {
    if (!searchTerm) return false; // Only show when searching
    const term = searchTerm.toLowerCase();
    return (
      c.full_name?.toLowerCase().includes(term) ||
      c.current_company?.toLowerCase().includes(term) ||
      c.current_title?.toLowerCase().includes(term)
    );
  });

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20" aria-live="polite" aria-busy="true">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-amber-500 border-t-transparent" role="status" aria-label="Loading sharing settings" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6" role="main">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-slate-900">Sharing Settings</h1>
        <Link to="/marketplace/dashboard" className="text-sm text-amber-600 hover:text-amber-700">
          &larr; Back to Dashboard
        </Link>
      </div>

      {/* Privacy explainer */}
      <div className="rounded-lg border border-blue-200 bg-blue-50 p-4">
        <h3 className="mb-1 text-sm font-semibold text-blue-800">How marketplace sharing works</h3>
        <p className="text-sm text-blue-700">
          Job seekers see <strong>role level and department only</strong> &mdash; never names or contact details.
          When someone requests an intro, you see their profile and choose whether to introduce them to your contact.
          Names and details are never revealed without your explicit approval.
        </p>
      </div>

      {/* Share toggle */}
      <div className="rounded-xl bg-white p-5 shadow-sm ring-1 ring-slate-200">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-base font-semibold text-slate-900">Share my network on the marketplace</h2>
            <p className="text-sm text-slate-500">
              {prefs?.opt_in_marketplace
                ? 'Your contacts are visible (anonymized) to job seekers.'
                : 'Enable sharing to help others get referred and earn credits.'}
            </p>
          </div>
          <button
            onClick={() => setPrefs({ ...prefs, opt_in_marketplace: !prefs.opt_in_marketplace })}
            role="switch"
            aria-checked={!!prefs?.opt_in_marketplace}
            aria-label="Share my network on the marketplace"
            className={`relative h-6 w-11 rounded-full transition ${
              prefs?.opt_in_marketplace ? 'bg-amber-500' : 'bg-slate-300'
            }`}
          >
            <span aria-hidden="true" className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition ${
              prefs?.opt_in_marketplace ? 'left-5.5' : 'left-0.5'
            }`} style={{ left: prefs?.opt_in_marketplace ? '22px' : '2px' }} />
          </button>
        </div>
      </div>

      {/* Pause toggle */}
      <div className="rounded-xl bg-white p-5 shadow-sm ring-1 ring-slate-200">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-base font-semibold text-slate-900">Temporarily hide all my listings</h2>
            <p className="text-sm text-slate-500">
              Pause sharing without losing your listings. You can resume anytime.
            </p>
          </div>
          <button
            onClick={() => setPrefs({ ...prefs, is_paused: !prefs.is_paused })}
            role="switch"
            aria-checked={!!prefs?.is_paused}
            aria-label="Temporarily hide all my listings"
            className={`relative h-6 w-11 rounded-full transition ${
              prefs?.is_paused ? 'bg-amber-500' : 'bg-slate-300'
            }`}
          >
            <span aria-hidden="true" className="absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition"
              style={{ left: prefs?.is_paused ? '22px' : '2px' }} />
          </button>
        </div>
      </div>

      {/* Category filters */}
      <div className="rounded-xl bg-white p-5 shadow-sm ring-1 ring-slate-200">
        <h2 className="mb-1 text-base font-semibold text-slate-900">Department Filters</h2>
        <p className="mb-3 text-sm text-slate-500">
          Only share contacts in selected departments. Leave all unchecked to share all departments.
        </p>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          {DEPARTMENT_OPTIONS.map((dept) => (
            <label key={dept} className="flex items-center gap-2 rounded-lg border border-slate-200 p-2 text-sm hover:bg-slate-50">
              <input
                type="checkbox"
                checked={categoryFilters.includes(dept)}
                onChange={() => toggleDepartment(dept)}
                className="h-4 w-4 rounded border-slate-300 text-amber-500 focus:ring-amber-500"
              />
              <span className="text-slate-700">{dept}</span>
            </label>
          ))}
        </div>
      </div>

      {/* Excluded contacts */}
      <div className="rounded-xl bg-white p-5 shadow-sm ring-1 ring-slate-200">
        <h2 className="mb-1 text-base font-semibold text-slate-900">Excluded Contacts</h2>
        <p className="mb-3 text-sm text-slate-500">
          Search and select specific contacts to exclude from the marketplace.
        </p>

        <label htmlFor="exclude-search" className="sr-only">Search contacts to exclude</label>
        <input
          id="exclude-search"
          type="text"
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          placeholder="Search contacts by name, company, or title..."
          aria-label="Search contacts to exclude from marketplace"
          className="mb-3 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500"
        />

        {/* Search results */}
        {filteredContacts.length > 0 && (
          <div className="mb-3 max-h-48 overflow-y-auto rounded-lg border border-slate-200">
            {filteredContacts.slice(0, 20).map((c) => (
              <label key={c.id} className="flex items-center gap-2 border-b border-slate-100 px-3 py-2 text-sm last:border-0 hover:bg-slate-50">
                <input
                  type="checkbox"
                  checked={excludedIds.includes(c.id)}
                  onChange={() => toggleExclude(c.id)}
                  className="h-4 w-4 rounded border-slate-300 text-red-500 focus:ring-red-500"
                />
                <span className="text-slate-900">{c.full_name}</span>
                {c.current_title && <span className="text-slate-400">— {c.current_title}</span>}
                {c.current_company && <span className="text-xs text-slate-400">at {c.current_company}</span>}
              </label>
            ))}
          </div>
        )}

        {/* Excluded count */}
        {excludedIds.length > 0 && (
          <p className="text-xs text-slate-500">
            {excludedIds.length} contact{excludedIds.length !== 1 ? 's' : ''} excluded
          </p>
        )}
      </div>

      {/* Save button */}
      <div className="flex items-center gap-3">
        <button
          onClick={handleSave}
          disabled={saving}
          className="rounded-lg bg-amber-500 px-6 py-2.5 text-sm font-medium text-white hover:bg-amber-600 disabled:opacity-50"
        >
          {saving ? 'Saving...' : 'Save Settings'}
        </button>
        {saved && (
          <span className="text-sm text-green-600" role="status" aria-live="polite">Settings saved!</span>
        )}
      </div>
    </div>
  );
}
