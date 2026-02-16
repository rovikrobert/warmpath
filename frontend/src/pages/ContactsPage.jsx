import { useCallback, useEffect, useRef, useState } from 'react';
import { contacts as contactsApi, companies as companiesApi } from '../api/client';

const RELATIONSHIP_TYPES = [
  { value: '', label: 'All types' },
  { value: 'current_colleague', label: 'Current colleague' },
  { value: 'former_colleague', label: 'Former colleague' },
  { value: 'manager', label: 'Manager' },
  { value: 'alumni', label: 'Alumni' },
  { value: 'industry_peer', label: 'Industry peer' },
  { value: 'friend', label: 'Friend' },
  { value: 'mentor', label: 'Mentor' },
  { value: 'recruiter', label: 'Recruiter' },
];

const REL_BADGE_COLORS = {
  current_colleague: 'bg-blue-100 text-blue-700',
  former_colleague: 'bg-indigo-100 text-indigo-700',
  manager: 'bg-green-100 text-green-700',
  alumni: 'bg-purple-100 text-purple-700',
  industry_peer: 'bg-cyan-100 text-cyan-700',
  friend: 'bg-amber-100 text-amber-700',
  mentor: 'bg-teal-100 text-teal-700',
  recruiter: 'bg-slate-100 text-slate-500',
};

const REL_SCORE_BONUSES = {
  manager: '+20 referral score bonus',
  former_colleague: '+15 referral score bonus',
  current_colleague: '+10 referral score bonus',
  alumni: '+10 referral score bonus',
  mentor: '+10 referral score bonus',
  friend: '+5 referral score bonus',
  recruiter: '-20 referral score penalty',
};

function RelBadge({ type, onClick }) {
  if (!type) {
    return onClick ? (
      <button onClick={onClick} className="text-xs text-amber-600 hover:text-amber-700">Set type</button>
    ) : null;
  }
  const label = RELATIONSHIP_TYPES.find((r) => r.value === type)?.label || type;
  const color = REL_BADGE_COLORS[type] || 'bg-slate-100 text-slate-600';
  return (
    <span
      onClick={onClick}
      className={`inline-flex cursor-pointer rounded-full px-2 py-0.5 text-xs font-medium ${color}`}
    >
      {label}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Add Contact Modal
// ---------------------------------------------------------------------------
function AddContactModal({ onClose, onSuccess, companies: companyList }) {
  const [form, setForm] = useState({
    first_name: '', last_name: '', company: '', position: '',
    email: '', location: '', relationship_type: '', how_you_know: '',
    last_interaction_date: '',
  });
  const [suggestions, setSuggestions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const set = (key) => (e) => {
    const val = e.target.value;
    setForm((f) => ({ ...f, [key]: val }));
    if (key === 'company' && val.length >= 2 && companyList.length > 0) {
      setSuggestions(companyList.filter((c) => c.toLowerCase().includes(val.toLowerCase())).slice(0, 5));
    } else if (key === 'company') {
      setSuggestions([]);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.first_name.trim() || !form.last_name.trim() || !form.company.trim()) {
      setError('First name, last name, and company are required.');
      return;
    }
    setLoading(true);
    setError('');
    try {
      const body = { ...form };
      if (!body.relationship_type) delete body.relationship_type;
      if (!body.how_you_know) delete body.how_you_know;
      if (!body.last_interaction_date) delete body.last_interaction_date;
      if (!body.email) delete body.email;
      if (!body.location) delete body.location;
      if (!body.position) delete body.position;
      await contactsApi.createManual(body);
      onSuccess();
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const inputClass = 'w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="relative mx-4 w-full max-w-lg rounded-xl bg-white p-6 shadow-xl">
        <button onClick={onClose} className="absolute right-4 top-4 text-slate-400 hover:text-slate-600">&times;</button>
        <h2 className="mb-4 text-lg font-semibold text-slate-900">Add Contact</h2>

        <form onSubmit={handleSubmit} className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-700">First name *</label>
              <input type="text" value={form.first_name} onChange={set('first_name')} className={inputClass} />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-700">Last name *</label>
              <input type="text" value={form.last_name} onChange={set('last_name')} className={inputClass} />
            </div>
          </div>

          <div className="relative">
            <label className="mb-1 block text-xs font-medium text-slate-700">Company *</label>
            <input type="text" value={form.company} onChange={set('company')} className={inputClass} />
            {suggestions.length > 0 && (
              <div className="absolute z-10 mt-1 w-full rounded-lg border border-slate-200 bg-white shadow-md">
                {suggestions.map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => { setForm((f) => ({ ...f, company: s })); setSuggestions([]); }}
                    className="block w-full px-3 py-1.5 text-left text-sm text-slate-700 hover:bg-amber-50"
                  >
                    {s}
                  </button>
                ))}
              </div>
            )}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-700">Position</label>
              <input type="text" value={form.position} onChange={set('position')} className={inputClass} />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-700">Email</label>
              <input type="email" value={form.email} onChange={set('email')} className={inputClass} />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-700">Location</label>
              <input type="text" value={form.location} onChange={set('location')} className={inputClass} />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-700">Relationship type</label>
              <select value={form.relationship_type} onChange={set('relationship_type')} className={inputClass}>
                <option value="">Select...</option>
                {RELATIONSHIP_TYPES.filter((r) => r.value).map((r) => (
                  <option key={r.value} value={r.value}>{r.label}</option>
                ))}
              </select>
            </div>
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-slate-700">How do you know them?</label>
            <textarea value={form.how_you_know} onChange={set('how_you_know')} rows={2} className={inputClass} placeholder="College roommate, worked together at Google..." />
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-slate-700">Last interaction date</label>
            <input type="date" value={form.last_interaction_date} onChange={set('last_interaction_date')} className={inputClass} />
          </div>

          {error && <p className="rounded-md bg-red-50 p-2 text-sm text-red-600">{error}</p>}

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-lg bg-amber-500 py-2.5 text-sm font-medium text-white hover:bg-amber-600 disabled:opacity-50"
          >
            {loading ? 'Adding...' : 'Add Contact'}
          </button>
        </form>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Bulk Import Modal
// ---------------------------------------------------------------------------
function BulkImportModal({ onClose, onSuccess }) {
  const [csvText, setCsvText] = useState('');
  const [preview, setPreview] = useState(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const fileRef = useRef(null);

  const handleFile = (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => setCsvText(ev.target.result);
    reader.readAsText(file);
  };

  const parsePreview = () => {
    if (!csvText.trim()) return;
    const lines = csvText.trim().split('\n');
    if (lines.length < 2) { setError('CSV must have a header row and at least one data row.'); return; }
    const headers = lines[0].split(',').map((h) => h.trim().toLowerCase());
    const rows = lines.slice(1).map((line) => {
      const vals = line.split(',');
      const row = {};
      headers.forEach((h, i) => { row[h] = vals[i]?.trim() || ''; });
      return row;
    }).filter((r) => r.name || r['first name'] || r.first_name);
    setPreview(rows);
    setError('');
  };

  const handleImport = async () => {
    if (!preview?.length) return;
    setLoading(true);
    setError('');
    try {
      const mapped = preview.map((r) => {
        const firstName = r.first_name || r['first name'] || (r.name || '').split(' ')[0];
        const lastName = r.last_name || r['last name'] || (r.name || '').split(' ').slice(1).join(' ');
        return {
          first_name: firstName,
          last_name: lastName,
          company: r.company || '',
          position: r.title || r.position || undefined,
          relationship_type: r.relationship || r.relationship_type || undefined,
          how_you_know: r.how_you_know || r['how you know'] || undefined,
        };
      });
      const res = await contactsApi.bulkImport(mapped);
      setResult(res.data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="relative mx-4 w-full max-w-2xl rounded-xl bg-white p-6 shadow-xl">
        <button onClick={onClose} className="absolute right-4 top-4 text-slate-400 hover:text-slate-600">&times;</button>
        <h2 className="mb-4 text-lg font-semibold text-slate-900">Bulk Import Contacts</h2>

        {result ? (
          <div className="space-y-3 text-center">
            <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-green-100">
              <span className="text-xl text-green-600">&#10003;</span>
            </div>
            <p className="text-sm text-slate-700">
              Added <strong>{result.created}</strong> contacts
              {result.errors?.length > 0 && `, ${result.errors.length} skipped`}
            </p>
            <button onClick={() => { onSuccess(); onClose(); }} className="rounded-lg bg-amber-500 px-6 py-2 text-sm font-medium text-white hover:bg-amber-600">
              Done
            </button>
          </div>
        ) : !preview ? (
          <div className="space-y-3">
            <p className="text-sm text-slate-500">
              Paste or upload a CSV with columns: <code className="rounded bg-slate-100 px-1 text-xs">name, company, title, relationship, how_you_know</code>
            </p>
            <textarea
              value={csvText}
              onChange={(e) => setCsvText(e.target.value)}
              rows={6}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 font-mono text-xs focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500"
              placeholder={'name,company,title,relationship,how_you_know\nJohn Smith,TechCo,Engineer,friend,College buddy\nJane Doe,BigCorp,VP Product,former_colleague,Worked together'}
            />
            <div className="flex items-center gap-3">
              <button onClick={() => fileRef.current?.click()} className="text-sm text-amber-600 hover:text-amber-700">
                Or upload a .csv file
              </button>
              <input ref={fileRef} type="file" accept=".csv" className="hidden" onChange={handleFile} />
            </div>
            {error && <p className="rounded-md bg-red-50 p-2 text-sm text-red-600">{error}</p>}
            <button
              onClick={parsePreview}
              disabled={!csvText.trim()}
              className="w-full rounded-lg bg-amber-500 py-2.5 text-sm font-medium text-white hover:bg-amber-600 disabled:opacity-50"
            >
              Preview
            </button>
          </div>
        ) : (
          <div className="space-y-3">
            <p className="text-sm text-slate-600">{preview.length} contacts to import:</p>
            <div className="max-h-60 overflow-y-auto rounded-lg border border-slate-200">
              <table className="w-full text-left text-xs">
                <thead className="sticky top-0 bg-slate-50">
                  <tr>
                    <th className="px-3 py-2 font-medium text-slate-600">Name</th>
                    <th className="px-3 py-2 font-medium text-slate-600">Company</th>
                    <th className="px-3 py-2 font-medium text-slate-600">Title</th>
                    <th className="px-3 py-2 font-medium text-slate-600">Relationship</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {preview.map((r, i) => (
                    <tr key={i}>
                      <td className="px-3 py-1.5 text-slate-900">{r.name || `${r.first_name || r['first name'] || ''} ${r.last_name || r['last name'] || ''}`.trim()}</td>
                      <td className="px-3 py-1.5 text-slate-600">{r.company}</td>
                      <td className="px-3 py-1.5 text-slate-600">{r.title || r.position}</td>
                      <td className="px-3 py-1.5 text-slate-600">{r.relationship || r.relationship_type || '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {error && <p className="rounded-md bg-red-50 p-2 text-sm text-red-600">{error}</p>}
            <div className="flex gap-3">
              <button onClick={() => setPreview(null)} className="flex-1 rounded-lg border border-slate-300 py-2.5 text-sm font-medium text-slate-600 hover:bg-slate-50">
                Back
              </button>
              <button onClick={handleImport} disabled={loading} className="flex-1 rounded-lg bg-amber-500 py-2.5 text-sm font-medium text-white hover:bg-amber-600 disabled:opacity-50">
                {loading ? 'Importing...' : `Import ${preview.length} contacts`}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Contact Detail Panel (inline expandable)
// ---------------------------------------------------------------------------
function ContactDetail({ contact, onUpdate }) {
  const [relType, setRelType] = useState(contact.relationship_type || '');
  const [saving, setSaving] = useState(false);

  const handleRelChange = async (e) => {
    const val = e.target.value;
    setRelType(val);
    setSaving(true);
    try {
      await contactsApi.patch(contact.id, { relationship_type: val || null });
      onUpdate();
    } catch {
      setRelType(contact.relationship_type || '');
    } finally {
      setSaving(false);
    }
  };

  const bonus = REL_SCORE_BONUSES[relType];

  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
      <div className="grid grid-cols-2 gap-4 text-sm">
        <div>
          <p className="text-xs text-slate-500">Company</p>
          <p className="text-slate-900">{contact.current_company || '-'}</p>
        </div>
        <div>
          <p className="text-xs text-slate-500">Title</p>
          <p className="text-slate-900">{contact.current_title || '-'}</p>
        </div>
        <div>
          <p className="text-xs text-slate-500">Email</p>
          <p className="text-slate-900">{contact.email || '-'}</p>
        </div>
        <div>
          <p className="text-xs text-slate-500">Warm Score</p>
          <p className="text-slate-900">{contact.warm_score ?? '-'}</p>
        </div>
        <div>
          <p className="mb-1 text-xs text-slate-500">Relationship Type</p>
          <select
            value={relType}
            onChange={handleRelChange}
            disabled={saving}
            className="rounded-md border border-slate-300 px-2 py-1 text-sm focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500"
          >
            <option value="">Unclassified</option>
            {RELATIONSHIP_TYPES.filter((r) => r.value).map((r) => (
              <option key={r.value} value={r.value}>{r.label}</option>
            ))}
          </select>
          {bonus && (
            <p className={`mt-1 text-xs ${relType === 'recruiter' ? 'text-red-500' : 'text-green-600'}`}>
              {bonus}
            </p>
          )}
        </div>
        {contact.how_you_know && (
          <div>
            <p className="text-xs text-slate-500">How you know</p>
            <p className="text-slate-900">{contact.how_you_know}</p>
          </div>
        )}
        {contact.source && (
          <div>
            <p className="text-xs text-slate-500">Source</p>
            <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${contact.source === 'manual' ? 'bg-amber-100 text-amber-700' : 'bg-slate-100 text-slate-600'}`}>
              {contact.source === 'manual' ? 'Manual' : 'LinkedIn CSV'}
            </span>
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main ContactsPage
// ---------------------------------------------------------------------------
export default function ContactsPage() {
  const [contactsList, setContactsList] = useState([]);
  const [meta, setMeta] = useState({});
  const [filter, setFilter] = useState('');
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState(null);
  const [showAddModal, setShowAddModal] = useState(false);
  const [showBulkModal, setShowBulkModal] = useState(false);
  const [companyNames, setCompanyNames] = useState([]);
  const [addedCompanies, setAddedCompanies] = useState([]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = { page, per_page: 50 };
      if (filter) params.relationship_type = filter;
      const res = await contactsApi.list(params);
      setContactsList(res.data || []);
      setMeta(res.meta || {});
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, [page, filter]);

  useEffect(() => { load(); }, [load]);

  // Load company names for autocomplete (once)
  useEffect(() => {
    companiesApi.list(1, 200).then((res) => {
      setCompanyNames((res.data || []).map((c) => c.name).filter(Boolean));
    }).catch(() => {});
  }, []);

  const handleAddSuccess = () => {
    setShowAddModal(false);
    load();
  };

  const handleManualSuccess = (newCompanies) => {
    load();
    if (newCompanies?.length) setAddedCompanies(newCompanies);
  };

  const totalPages = meta.total_pages || Math.ceil((meta.total || contactsList.length) / 50);

  return (
    <div className="mx-auto max-w-4xl">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-bold text-slate-900">Contacts</h1>
        <div className="flex gap-2">
          <button
            onClick={() => setShowAddModal(true)}
            className="rounded-lg bg-amber-500 px-4 py-2 text-sm font-medium text-white hover:bg-amber-600"
          >
            Add Contact
          </button>
          <button
            onClick={() => setShowBulkModal(true)}
            className="rounded-lg border border-amber-500 px-4 py-2 text-sm font-medium text-amber-600 hover:bg-amber-50"
          >
            Import Multiple
          </button>
        </div>
      </div>

      {/* Filter bar */}
      <div className="mb-4 flex items-center gap-3">
        <select
          value={filter}
          onChange={(e) => { setFilter(e.target.value); setPage(1); }}
          className="rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500"
        >
          {RELATIONSHIP_TYPES.map((r) => (
            <option key={r.value} value={r.value}>{r.label}</option>
          ))}
          <option value="__none__">Unclassified</option>
        </select>
        {meta.total != null && (
          <span className="text-sm text-slate-500">{meta.total} contacts</span>
        )}
      </div>

      {/* Post-add prompt */}
      {addedCompanies.length > 0 && (
        <div className="mb-4 rounded-lg border border-green-200 bg-green-50 p-3">
          <p className="text-sm text-green-800">
            Contacts added! Want to search for referral paths at{' '}
            <strong>{addedCompanies.slice(0, 3).join(', ')}</strong>
            {addedCompanies.length > 3 && ` and ${addedCompanies.length - 3} more`}?
          </p>
          <a href="/referrals" className="mt-1 inline-block text-sm font-medium text-green-700 hover:text-green-800">
            Search now &rarr;
          </a>
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-20">
          <div className="h-8 w-8 animate-spin rounded-full border-4 border-amber-500 border-t-transparent" />
        </div>
      ) : contactsList.length === 0 ? (
        <div className="rounded-xl bg-white p-12 text-center ring-1 ring-slate-200">
          <p className="text-sm text-slate-500">
            {filter ? 'No contacts match this filter.' : 'No contacts yet. Upload a CSV or add contacts manually.'}
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          {contactsList.map((c) => (
            <div key={c.id} className="rounded-xl bg-white shadow-sm ring-1 ring-slate-200">
              <div
                onClick={() => setExpandedId(expandedId === c.id ? null : c.id)}
                className="flex cursor-pointer items-center justify-between px-4 py-3 hover:bg-amber-50/30"
              >
                <div className="flex items-center gap-3">
                  <div>
                    <p className="text-sm font-medium text-slate-900">{c.full_name}</p>
                    <p className="text-xs text-slate-500">
                      {c.current_title && `${c.current_title} at `}{c.current_company || ''}
                    </p>
                  </div>
                  <RelBadge
                    type={c.relationship_type}
                    onClick={(e) => { e.stopPropagation(); setExpandedId(c.id); }}
                  />
                </div>
                <div className="flex items-center gap-3">
                  {c.warm_score != null && (
                    <span className={`text-xs font-medium ${
                      c.warm_score >= 70 ? 'text-green-600' : c.warm_score >= 40 ? 'text-amber-600' : 'text-slate-400'
                    }`}>
                      {c.warm_score}
                    </span>
                  )}
                  <span className="text-xs text-slate-400">{expandedId === c.id ? '\u25B2' : '\u25BC'}</span>
                </div>
              </div>
              {expandedId === c.id && (
                <div className="border-t border-slate-100 px-4 py-3">
                  <ContactDetail contact={c} onUpdate={load} />
                </div>
              )}
            </div>
          ))}

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-center gap-2 pt-4">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="rounded-md border border-slate-300 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50 disabled:opacity-50"
              >
                Prev
              </button>
              <span className="text-sm text-slate-500">Page {page} of {totalPages}</span>
              <button
                onClick={() => setPage((p) => p + 1)}
                disabled={page >= totalPages}
                className="rounded-md border border-slate-300 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50 disabled:opacity-50"
              >
                Next
              </button>
            </div>
          )}
        </div>
      )}

      {showAddModal && (
        <AddContactModal
          onClose={() => setShowAddModal(false)}
          onSuccess={handleAddSuccess}
          companies={companyNames}
        />
      )}

      {showBulkModal && (
        <BulkImportModal
          onClose={() => setShowBulkModal(false)}
          onSuccess={() => { setShowBulkModal(false); load(); }}
        />
      )}
    </div>
  );
}
