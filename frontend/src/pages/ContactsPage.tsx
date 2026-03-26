import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { contacts as contactsApi, companies as companiesApi, feed as feedApi } from '../api/client';
import MatchBadge from '../components/MatchBadge';
import { getNlpMatchTier, WARM_TIERS } from '../utils/scores';
import ScoreExplainer from '../components/ScoreExplainer';
import EnrichmentProgress from '../components/EnrichmentProgress';
import { EnrichmentActions } from '../components/FeedCard';
import KeevsAvatar from '../components/KeevsAvatar';
import EmptyState from '../components/ui/EmptyState';
import noContactsIllustration from '../assets/illustrations/no-contacts.webp';
import ContactsPageSkeleton from '../components/skeletons/ContactsPageSkeleton';
import SlideOver from '../components/SlideOver';
import ContactDetailPanel from '../components/ContactDetail';
import useKeyboardShortcuts from '../hooks/useKeyboardShortcuts';
import UploadModal from '../components/UploadModal';
import useDocumentTitle from '../hooks/useDocumentTitle';

const RELATIONSHIP_TYPES = [
  { value: '', label: 'All types' },
  { value: 'current_colleague', label: 'Current colleague' },
  { value: 'former_colleague', label: 'Former colleague' },
  { value: 'manager', label: 'Manager' },
  { value: 'alumni', label: 'Alumni' },
  { value: 'industry_peer', label: 'Industry peer' },
  { value: 'friend', label: 'Friend' },
  { value: 'mentor', label: 'Mentor' },
  { value: 'client', label: 'Client' },
  { value: 'vendor', label: 'Vendor / Supplier' },
  { value: 'investor', label: 'Investor' },
  { value: 'recruiter', label: 'Recruiter' },
];

const REL_BADGE_COLORS = {
  current_colleague: 'bg-blue-500/10 text-blue-400',
  former_colleague: 'bg-indigo-500/10 text-indigo-400',
  manager: 'bg-success/10 text-success',
  alumni: 'bg-purple-500/10 text-purple-400',
  industry_peer: 'bg-cyan-500/10 text-cyan-400',
  friend: 'bg-primary/10 text-primary',
  mentor: 'bg-teal-500/10 text-teal-400',
  client: 'bg-orange-500/10 text-orange-400',
  vendor: 'bg-lime-500/10 text-lime-400',
  investor: 'bg-rose-500/10 text-rose-400',
  recruiter: 'bg-muted/50 text-muted-foreground',
};

function RelBadge({ type, onClick, showSetType = true, animate = false }) {
  if (!type) {
    return (onClick && showSetType) ? (
      <button onClick={onClick} aria-label="Set relationship type" className="text-xs text-primary hover:text-primary">Set type</button>
    ) : null;
  }
  const label = RELATIONSHIP_TYPES.find((r) => r.value === type)?.label || type;
  const color = REL_BADGE_COLORS[type] || 'bg-muted/50 text-muted-foreground';
  return (
    <span
      onClick={onClick}
      role="button"
      tabIndex={0}
      aria-label={`Relationship type: ${label}. Click to edit`}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') onClick?.(e); }}
      className={`inline-flex cursor-pointer rounded-full px-2 py-0.5 text-xs font-medium ${color} ${animate ? 'animate-scale-in' : ''}`}
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

  const inputClass = 'w-full rounded-lg border border-border bg-muted px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" role="dialog" aria-modal="true" aria-labelledby="add-contact-title">
      <div className="relative mx-4 w-full max-w-lg rounded-xl bg-card border border-border p-6 shadow-xl">
        <button onClick={onClose} aria-label="Close add contact dialog" className="absolute right-4 top-4 text-muted-foreground hover:text-secondary-foreground">&times;</button>
        <h2 id="add-contact-title" className="mb-4 text-lg font-semibold text-foreground">Add Contact</h2>

        <form onSubmit={handleSubmit} className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label htmlFor="add-first-name" className="mb-1 block text-xs font-medium text-secondary-foreground">First name *</label>
              <input id="add-first-name" type="text" value={form.first_name} onChange={set('first_name')} aria-required="true" className={inputClass} />
            </div>
            <div>
              <label htmlFor="add-last-name" className="mb-1 block text-xs font-medium text-secondary-foreground">Last name *</label>
              <input id="add-last-name" type="text" value={form.last_name} onChange={set('last_name')} aria-required="true" className={inputClass} />
            </div>
          </div>

          <div className="relative">
            <label htmlFor="add-company" className="mb-1 block text-xs font-medium text-secondary-foreground">Company *</label>
            <input id="add-company" type="text" value={form.company} onChange={set('company')} aria-required="true" className={inputClass} />
            {suggestions.length > 0 && (
              <div className="absolute z-10 mt-1 w-full rounded-lg border border-border bg-card shadow-md">
                {suggestions.map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => { setForm((f) => ({ ...f, company: s })); setSuggestions([]); }}
                    className="block w-full px-3 py-1.5 text-left text-sm text-secondary-foreground hover:bg-muted"
                  >
                    {s}
                  </button>
                ))}
              </div>
            )}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label htmlFor="add-position" className="mb-1 block text-xs font-medium text-secondary-foreground">Position</label>
              <input id="add-position" type="text" value={form.position} onChange={set('position')} className={inputClass} />
            </div>
            <div>
              <label htmlFor="add-email" className="mb-1 block text-xs font-medium text-secondary-foreground">Email</label>
              <input id="add-email" type="email" value={form.email} onChange={set('email')} className={inputClass} />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label htmlFor="add-location" className="mb-1 block text-xs font-medium text-secondary-foreground">Location</label>
              <input id="add-location" type="text" value={form.location} onChange={set('location')} className={inputClass} />
            </div>
            <div>
              <label htmlFor="add-relationship-type" className="mb-1 block text-xs font-medium text-secondary-foreground">Relationship type</label>
              <select id="add-relationship-type" value={form.relationship_type} onChange={set('relationship_type')} className={inputClass}>
                <option value="">Select...</option>
                {RELATIONSHIP_TYPES.filter((r) => r.value).map((r) => (
                  <option key={r.value} value={r.value}>{r.label}</option>
                ))}
              </select>
            </div>
          </div>

          <div>
            <label htmlFor="add-how-you-know" className="mb-1 block text-xs font-medium text-secondary-foreground">How do you know them?</label>
            <textarea id="add-how-you-know" value={form.how_you_know} onChange={set('how_you_know')} rows={2} className={inputClass} placeholder="College roommate, worked together at Google..." />
          </div>

          <div>
            <label htmlFor="add-last-interaction" className="mb-1 block text-xs font-medium text-secondary-foreground">Last interaction date</label>
            <input id="add-last-interaction" type="date" value={form.last_interaction_date} onChange={set('last_interaction_date')} className={inputClass} />
          </div>

          {error && <p role="alert" aria-live="polite" className="rounded-md bg-destructive/10 p-2 text-sm text-destructive">{error}</p>}

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-lg bg-primary py-2.5 text-sm font-medium text-white hover:bg-primary/90 disabled:opacity-50"
          >
            {loading ? 'Adding...' : 'Add Contact'}
          </button>
        </form>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main ContactsPage
// ---------------------------------------------------------------------------
export default function ContactsPage() {
  useDocumentTitle('Contacts');
  const [contactsList, setContactsList] = useState([]);
  const [meta, setMeta] = useState({});
  const [filter, setFilter] = useState('');
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [showAddModal, setShowAddModal] = useState(false);
  const [showBulkModal, setShowBulkModal] = useState(false);
  const [companyNames, setCompanyNames] = useState([]);
  const [addedCompanies, setAddedCompanies] = useState([]);
  const [selectedContact, setSelectedContact] = useState(null);
  const [focusedIndex, setFocusedIndex] = useState(-1);
  const [recentlyUpdatedId, setRecentlyUpdatedId] = useState(null);
  const [toast, setToast] = useState(null);
  // Bulk update state
  const [bulkRelType, setBulkRelType] = useState('');
  const [bulkUpdating, setBulkUpdating] = useState(false);
  const [bulkConfirm, setBulkConfirm] = useState(false);

  // Batch processing banner state (set when upload completes in batch mode)
  const [batchUpload, setBatchUpload] = useState(null);

  // Latest upload status banner
  const [latestUpload, setLatestUpload] = useState(null);
  const [latestUploadDismissed, setLatestUploadDismissed] = useState(false);

  // Enrichment prompt feed items
  const [enrichmentPrompts, setEnrichmentPrompts] = useState([]);
  const [enrichmentRefreshKey, setEnrichmentRefreshKey] = useState(0);

  // Export state
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState('');

  // NLP search state
  const [searchInput, setSearchInput] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [nlpResults, setNlpResults] = useState(null);
  const [nlpInterpretation, setNlpInterpretation] = useState(null);
  const [nlpLoading, setNlpLoading] = useState(false);
  const [nlpError, setNlpError] = useState('');
  const [nlpFadingOut, setNlpFadingOut] = useState(false);

  // Debounce search input for list filtering
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(searchInput.trim());
      setPage(1);
    }, 300);
    return () => clearTimeout(timer);
  }, [searchInput]);

  const handleNlpSearch = useCallback(async () => {
    const query = searchInput.trim();
    if (!query) return;
    setNlpLoading(true);
    setNlpError('');
    try {
      const res = await contactsApi.nlpSearch(query);
      setNlpResults(res.data || []);
      setNlpInterpretation(res.meta?.interpretation || null);
    } catch (err) {
      setNlpError(err.message || 'NLP search failed');
      setNlpResults(null);
    } finally {
      setNlpLoading(false);
    }
  }, [searchInput]);

  const clearNlpSearch = useCallback(() => {
    setNlpFadingOut(true);
    setTimeout(() => {
      setSearchInput('');
      setNlpResults(null);
      setNlpInterpretation(null);
      setNlpError('');
      setNlpFadingOut(false);
    }, 200);
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = { page, per_page: 50 };
      // '__none__' is the UI sentinel for "no relationship type set". Don't send
      // it as relationship_type (the backend would treat it as a literal string
      // and return 0 results). Backend support for a dedicated `unclassified`
      // param is tracked as a follow-up; for now the filter falls back to "show
      // all contacts", which is better than silently returning nothing.
      if (filter && filter !== '__none__') params.relationship_type = filter;
      if (debouncedSearch) params.search = debouncedSearch;
      const res = await contactsApi.list(params);
      setContactsList(res.data || []);
      setMeta(res.meta || {});
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, [page, filter, debouncedSearch]);

  useEffect(() => { load(); }, [load]);

  // Load company names for autocomplete (once)
  useEffect(() => {
    companiesApi.list(1, 200).then((res) => {
      setCompanyNames((res.data || []).map((c) => c.name).filter(Boolean));
    }).catch((err) => { console.error('Failed to load company names for autocomplete:', err); });
  }, []);

  // Check latest upload status on mount (for failure/processing banners)
  useEffect(() => {
    contactsApi.getLatestUpload().then((res) => {
      if (res.data) setLatestUpload(res.data);
    }).catch((err) => { console.error('Failed to load latest upload status:', err); });
  }, []);

  // Load enrichment prompt feed items (once)
  useEffect(() => {
    feedApi.list({ item_type: 'enrichment_prompt', limit: 3 })
      .then((r) => setEnrichmentPrompts(r.data?.items || r.data || []))
      .catch((err) => { console.error('Failed to load enrichment prompt feed items:', err); });
  }, []);

  const handleEnrichmentResponse = async (item, signalType, signalValue) => {
    try {
      await feedApi.enrichmentResponse({
        feed_item_id: item.id,
        signal_type: signalType,
        signal_value: signalValue,
      });
      setEnrichmentPrompts((prev) => prev.filter((p) => p.id !== item.id));
      setEnrichmentRefreshKey((k) => k + 1);
      // Update the contact in the list if visible
      const contactId = item.metadata?.contact_id;
      if (contactId && signalType === 'relationship_type') {
        handleContactUpdate(contactId, { relationship_type: signalValue }, true);
      }
    } catch (err) {
      setToast(err.message || 'Failed to save — please try again');
      setTimeout(() => setToast(null), 4000);
    }
  };

  const handleEnrichmentDismiss = async (item) => {
    try {
      await feedApi.dismiss(item.id);
      setEnrichmentPrompts((prev) => prev.filter((p) => p.id !== item.id));
    } catch (err) {
      console.error('Failed to dismiss enrichment prompt:', err);
    }
  };

  const handleAddSuccess = () => {
    setShowAddModal(false);
    load();
  };

  const handleManualSuccess = (newCompanies) => {
    load();
    if (newCompanies?.length) setAddedCompanies(newCompanies);
  };

  const handleContactUpdate = useCallback((contactId, updates, animate = false) => {
    setContactsList((prev) =>
      prev.map((c) => c.id === contactId ? { ...c, ...updates } : c)
    );
    setSelectedContact((prev) => prev && prev.id === contactId ? { ...prev, ...updates } : prev);
    if (animate && updates.relationship_type) {
      setRecentlyUpdatedId(contactId);
      setTimeout(() => setRecentlyUpdatedId(null), 250);
    }
  }, []);

  const handleContactError = useCallback((message) => {
    setToast(message);
    setTimeout(() => setToast(null), 3000);
  }, []);

  const handleExport = async () => {
    setExporting(true);
    setExportError('');
    try {
      const params = {};
      // Same sentinel guard as the load() callback — don't forward '__none__'
      // to the backend; it is a UI-only value meaning "unclassified".
      if (filter && filter !== '__none__') params.relationship_type = filter;
      await contactsApi.exportCsv(params);
    } catch (err) {
      setExportError(err.message || 'Export failed');
    } finally {
      setExporting(false);
    }
  };

  const handleBulkUpdate = async () => {
    if (!bulkRelType) return;
    setBulkUpdating(true);
    setBulkConfirm(false);
    try {
      let body = { relationship_type: bulkRelType };
      if (nlpResults) {
        // NLP mode: send explicit IDs
        body.contact_ids = nlpResults.map((c) => c.id);
      } else {
        // Regular filter/search mode: send filter object
        body.filter = {};
        if (debouncedSearch) body.filter.search = debouncedSearch;
        if (filter) body.filter.relationship_type = filter;
      }
      const res = await contactsApi.bulkUpdate(body);
      const count = res.data?.updated_count || 0;
      const label = RELATIONSHIP_TYPES.find((r) => r.value === bulkRelType)?.label || bulkRelType;
      setToast(`Updated ${count} contact${count !== 1 ? 's' : ''} to ${label}`);
      setTimeout(() => setToast(null), 3000);
      setBulkRelType('');
      // Refresh contact list
      if (nlpResults) {
        handleNlpSearch();
      } else {
        load();
      }
    } catch (err) {
      setToast(err.message || 'Bulk update failed');
      setTimeout(() => setToast(null), 3000);
    } finally {
      setBulkUpdating(false);
    }
  };

  const totalPages = meta.total_pages || Math.ceil((meta.total || contactsList.length) / 50);

  const isFiltered = !!(debouncedSearch || filter || nlpResults);
  const bulkTotal = nlpResults ? nlpResults.length : (meta.total || 0);

  const unclassifiedShowSet = useMemo(() => {
    const ids = new Set();
    let count = 0;
    for (const c of contactsList) {
      if (!c.relationship_type && count < 50) {
        ids.add(c.id);
        count++;
      }
    }
    return ids;
  }, [contactsList]);

  // Reset focused index when list changes
  useEffect(() => {
    setFocusedIndex(-1);
  }, [contactsList, nlpResults]);

  // J/K/Enter/Escape keyboard navigation
  useKeyboardShortcuts([
    { key: 'j', action: () => {
      if (nlpResults !== null) return;
      setFocusedIndex((prev) => {
        const next = Math.min(prev + 1, contactsList.length - 1);
        requestAnimationFrame(() => {
          document.querySelector(`[data-contact-index="${next}"]`)?.scrollIntoView({ block: 'nearest' });
        });
        return next;
      });
    }},
    { key: 'k', action: () => {
      if (nlpResults !== null) return;
      setFocusedIndex((prev) => {
        const next = Math.max(prev - 1, 0);
        requestAnimationFrame(() => {
          document.querySelector(`[data-contact-index="${next}"]`)?.scrollIntoView({ block: 'nearest' });
        });
        return next;
      });
    }},
    { key: 'Enter', action: () => {
      if (focusedIndex >= 0 && focusedIndex < contactsList.length) {
        setSelectedContact(contactsList[focusedIndex]);
      }
    }},
    { key: 'Escape', action: () => {
      if (selectedContact) setSelectedContact(null);
      else setFocusedIndex(-1);
    }},
  ], [contactsList, focusedIndex, selectedContact, nlpResults]);

  return (
    <div className="mx-auto max-w-4xl" role="main">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h1 className="page-title">Contacts</h1>
        <div className="flex gap-2">
          <button
            onClick={() => setShowAddModal(true)}
            className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary/90"
          >
            Add Contact
          </button>
          {/* Secondary actions collapse behind overflow menu on mobile */}
          <div className="hidden sm:flex gap-2">
            <button
              onClick={() => setShowBulkModal(true)}
              className="rounded-lg border border-primary px-4 py-2 text-sm font-medium text-primary hover:bg-primary/10"
            >
              Import Multiple
            </button>
            <button
              onClick={handleExport}
              disabled={exporting}
              aria-label="Export contacts as CSV"
              className="rounded-lg border border-border px-4 py-2 text-sm font-medium text-secondary-foreground hover:bg-muted disabled:opacity-50"
            >
              {exporting ? 'Exporting...' : 'Export CSV'}
            </button>
          </div>
          {/* Mobile overflow menu */}
          <div className="relative sm:hidden">
            <button
              onClick={(e) => {
                const menu = e.currentTarget.nextElementSibling;
                menu.classList.toggle('hidden');
              }}
              className="rounded-lg border border-border px-3 py-2 text-sm text-secondary-foreground hover:bg-muted"
              aria-label="More actions"
            >
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M6.75 12a.75.75 0 11-1.5 0 .75.75 0 011.5 0zM12.75 12a.75.75 0 11-1.5 0 .75.75 0 011.5 0zM18.75 12a.75.75 0 11-1.5 0 .75.75 0 011.5 0z" />
              </svg>
            </button>
            <div className="hidden absolute right-0 top-full mt-1 z-20 w-44 rounded-lg border border-border bg-muted py-1 shadow-lg">
              <button
                onClick={() => { setShowBulkModal(true); }}
                className="w-full px-4 py-2.5 text-left text-sm text-foreground hover:bg-muted"
              >
                Import Multiple
              </button>
              <button
                onClick={handleExport}
                disabled={exporting}
                className="w-full px-4 py-2.5 text-left text-sm text-foreground hover:bg-muted disabled:opacity-50"
              >
                {exporting ? 'Exporting...' : 'Export CSV'}
              </button>
            </div>
          </div>
        </div>
      </div>

      <EnrichmentProgress key={enrichmentRefreshKey} />

      {/* Upload failure banner */}
      {latestUpload && !latestUploadDismissed && latestUpload.status === 'failed' && (
        <div className="mb-4 rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-3" role="alert">
          <div className="flex items-start justify-between gap-3">
            <div className="flex items-start gap-3">
              <svg className="mt-0.5 h-5 w-5 shrink-0 text-amber-400" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z" />
              </svg>
              <div>
                <p className="text-sm font-medium text-amber-200">
                  Your last upload didn't go through — it was a problem on our end, not yours.
                </p>
                {latestUpload.error_message && (
                  <p className="mt-1 text-xs text-amber-300/70">{latestUpload.error_message}</p>
                )}
                <button
                  onClick={() => { setLatestUploadDismissed(true); setShowBulkModal(true); }}
                  className="mt-2 rounded-md bg-amber-500/20 px-3 py-1.5 text-xs font-medium text-amber-200 hover:bg-amber-500/30"
                >
                  Re-Upload CSV
                </button>
              </div>
            </div>
            <button
              onClick={() => setLatestUploadDismissed(true)}
              aria-label="Dismiss upload failure banner"
              className="shrink-0 text-amber-400/60 hover:text-amber-400"
            >
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth="2" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>
      )}

      {/* Upload processing banner */}
      {latestUpload && !latestUploadDismissed && (latestUpload.status === 'processing' || latestUpload.status === 'queued') && (
        <div className="mb-4 rounded-lg border border-blue-500/20 bg-blue-500/10 px-4 py-3" role="status">
          <div className="flex items-center gap-3">
            <svg className="h-5 w-5 shrink-0 animate-spin text-blue-400" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
            </svg>
            <p className="text-sm text-blue-200">
              Your upload is still processing...
            </p>
          </div>
        </div>
      )}

      {/* Batch processing banner */}
      {batchUpload && batchUpload.progress_phase?.startsWith('batch_') && (
        <div className="mb-4 rounded-lg border border-amber-500/20 bg-amber-500/5 px-4 py-3">
          <div className="flex items-center gap-3">
            <div className="h-2 w-2 animate-pulse rounded-full bg-amber-400" />
            <p className="text-sm text-amber-200">
              Importing <span className="font-medium">{batchUpload.filename}</span> — processing in background...
            </p>
          </div>
        </div>
      )}

      {/* Enrichment prompt feed items */}
      {enrichmentPrompts.length > 0 && (
        <div className="mb-4 rounded-lg border border-primary/20 bg-primary/5 p-3">
          {enrichmentPrompts.slice(0, 1).map((prompt) => (
            <div key={prompt.id} className="flex items-start gap-3">
              <div className="mt-0.5 shrink-0">
                <KeevsAvatar size="sm" />
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-foreground">{prompt.title}</p>
                {prompt.body && (
                  <p className="mt-0.5 text-xs text-muted-foreground">{prompt.body}</p>
                )}
                <EnrichmentActions
                  item={prompt}
                  onRespond={handleEnrichmentResponse}
                />
              </div>
              <button
                type="button"
                onClick={() => handleEnrichmentDismiss(prompt)}
                className="shrink-0 text-xs text-muted-foreground hover:text-muted-foreground transition-colors"
                aria-label="Dismiss enrichment prompt"
              >
                Dismiss
              </button>
            </div>
          ))}
          {enrichmentPrompts.length > 1 && (
            <p className="mt-2 text-xs text-muted-foreground">
              +{enrichmentPrompts.length - 1} more {enrichmentPrompts.length - 1 === 1 ? 'question' : 'questions'}
            </p>
          )}
        </div>
      )}

      {exportError && (
        <p role="alert" className="mb-4 rounded-md bg-destructive/10 p-2 text-sm text-destructive">{exportError}</p>
      )}

      {/* Search + Filter bar */}
      <div className="mb-4 space-y-3">
        <div className="flex items-center gap-2">
          <div className="relative flex-1">
            <label htmlFor="contacts-search" className="sr-only">Search contacts with natural language</label>
            {nlpResults !== null && !nlpFadingOut && (
              <span className="absolute left-2.5 top-1/2 z-10 -translate-y-1/2 rounded bg-primary/10 px-1.5 py-0.5 text-xs font-medium text-primary">AI</span>
            )}
            <input
              id="contacts-search"
              data-search-input
              type="text"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && searchInput.trim()) handleNlpSearch(); }}
              placeholder='Search contacts or try "CTOs at big tech in Singapore"...'
              aria-label="Search contacts using natural language"
              className={`w-full rounded-lg border border-border bg-muted py-2 pr-10 text-sm text-foreground placeholder:text-muted-foreground transition-colors duration-200 focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring ${nlpResults !== null && !nlpFadingOut ? 'pl-11' : 'pl-3'}`}
            />
            {searchInput.trim() && (
              <button
                onClick={handleNlpSearch}
                disabled={nlpLoading}
                aria-label="Run AI search"
                title="AI Search"
                className="absolute right-2 top-1/2 -translate-y-1/2 rounded-md px-1.5 py-1 text-primary hover:text-primary disabled:opacity-50"
              >
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="h-4 w-4" aria-hidden="true">
                  <path d="M10 1l2.39 4.843L17.5 6.91l-3.75 3.654.886 5.16L10 13.21l-4.636 2.513.886-5.16L2.5 6.91l5.11-1.066L10 1z" />
                </svg>
              </button>
            )}
          </div>
          <label htmlFor="contacts-filter" className="sr-only">Filter by relationship type</label>
          <select
            id="contacts-filter"
            value={filter}
            onChange={(e) => { setFilter(e.target.value); setPage(1); }}
            aria-label="Filter contacts by relationship type"
            className="rounded-lg border border-border bg-muted px-3 py-2 text-sm text-foreground transition-colors duration-200 focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring"
          >
            {RELATIONSHIP_TYPES.map((r) => (
              <option key={r.value} value={r.value}>{r.label}</option>
            ))}
            <option value="__none__">Unclassified</option>
          </select>
        </div>
        {meta.total != null && !nlpResults && (
          <span className="text-sm text-muted-foreground">{meta.total} contacts</span>
        )}
      </div>

      {/* Bulk update bar */}
      {bulkTotal > 0 && !loading && !nlpLoading && (
        <div className="mb-4 flex flex-wrap items-center gap-2 rounded-lg border border-border bg-surface-raised px-4 py-2.5">
          <span className="text-sm text-secondary-foreground">
            {isFiltered
              ? `${bulkTotal} contact${bulkTotal !== 1 ? 's' : ''} matched`
              : `${bulkTotal} contact${bulkTotal !== 1 ? 's' : ''}`}
          </span>
          <span className="text-muted-foreground">&middot;</span>
          <label htmlFor="bulk-rel-type" className="text-sm text-muted-foreground">Bulk update:</label>
          <select
            id="bulk-rel-type"
            value={bulkRelType}
            onChange={(e) => setBulkRelType(e.target.value)}
            className="rounded-md border border-border bg-muted px-2 py-1 text-sm text-foreground focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring"
          >
            <option value="">Relationship type...</option>
            {RELATIONSHIP_TYPES.filter((r) => r.value).map((r) => (
              <option key={r.value} value={r.value}>{r.label}</option>
            ))}
          </select>
          {!bulkConfirm ? (
            <button
              onClick={() => setBulkConfirm(true)}
              disabled={!bulkRelType || bulkUpdating}
              className="rounded-md bg-primary px-3 py-1 text-sm font-medium text-white hover:bg-primary/90 disabled:opacity-50"
            >
              Apply
            </button>
          ) : (
            <div className="flex items-center gap-2">
              <span className="text-xs text-primary">
                Update {bulkTotal} contact{bulkTotal !== 1 ? 's' : ''} to {RELATIONSHIP_TYPES.find((r) => r.value === bulkRelType)?.label}?
              </span>
              <button
                onClick={handleBulkUpdate}
                disabled={bulkUpdating}
                className="rounded-md bg-primary px-3 py-1 text-sm font-medium text-white hover:bg-primary/90 disabled:opacity-50"
              >
                {bulkUpdating ? 'Updating...' : 'Confirm'}
              </button>
              <button
                onClick={() => setBulkConfirm(false)}
                className="text-xs text-muted-foreground hover:text-muted-foreground"
              >
                Cancel
              </button>
            </div>
          )}
        </div>
      )}

      {/* NLP search result summary */}
      {nlpResults && (
        <div className={`mb-4 transition-opacity duration-200 ${nlpFadingOut ? 'opacity-0' : 'opacity-100'}`}>
          <div className="flex items-center gap-3">
            <span className="text-sm text-muted-foreground">
              {(() => {
                const best = nlpResults.filter((r) => (r.nlp_match_score ?? 0) >= 65).length;
                const possible = nlpResults.filter((r) => (r.nlp_match_score ?? 0) >= 35 && (r.nlp_match_score ?? 0) < 65).length;
                const parts = [];
                if (best) parts.push(`${best} best ${best === 1 ? 'match' : 'matches'}`);
                if (possible) parts.push(`${possible} possible`);
                const rest = nlpResults.length - best - possible;
                if (rest) parts.push(`${rest} partial`);
                return parts.join(', ') || `${nlpResults.length} matches`;
              })()}
            </span>
            <button
              onClick={clearNlpSearch}
              aria-label="Clear AI search and return to normal contact list"
              className="text-xs text-muted-foreground hover:text-muted-foreground"
            >
              Clear AI search &times;
            </button>
          </div>
        </div>
      )}

      {/* NLP error display */}
      {nlpError && (
        <div className="mb-4 rounded-lg bg-destructive/10 p-3" role="alert" aria-live="polite">
          <p className="text-sm text-destructive">{nlpError}</p>
          <button
            onClick={clearNlpSearch}
            className="mt-1 text-xs text-muted-foreground hover:text-muted-foreground"
          >
            Clear AI search &times;
          </button>
        </div>
      )}

      {/* Post-add prompt */}
      {addedCompanies.length > 0 && (
        <div className="mb-4 rounded-lg border border-success/30 bg-success/10 p-3">
          <p className="text-sm text-success">
            Contacts added! Want to search for referral paths at{' '}
            <strong>{addedCompanies.slice(0, 3).join(', ')}</strong>
            {addedCompanies.length > 3 && ` and ${addedCompanies.length - 3} more`}?
          </p>
          <a href="/referrals" className="mt-1 inline-block text-sm font-medium text-success hover:opacity-80">
            Search now &rarr;
          </a>
        </div>
      )}

      {/* NLP loading spinner */}
      {nlpLoading ? (
        <div className="flex items-center justify-center py-20" aria-live="polite" aria-busy="true">
          <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" role="status" aria-label="Searching contacts with AI" />
        </div>
      ) : nlpResults !== null ? (
        /* ---- NLP search results mode ---- */
        nlpResults.length === 0 ? (
          <div className={`rounded-xl bg-card p-12 text-center border border-border transition-opacity duration-200 ${nlpFadingOut ? 'opacity-0' : 'opacity-100'}`}>
            <p className="text-sm text-muted-foreground">No contacts match your search.</p>
            <button
              onClick={clearNlpSearch}
              className="mt-3 text-xs text-muted-foreground hover:text-muted-foreground"
            >
              Clear AI search &times;
            </button>
          </div>
        ) : (
          <div className={`space-y-2 page-enter transition-opacity duration-200 ${nlpFadingOut ? 'opacity-0' : 'opacity-100'}`}>
            {(() => {
              // Group results by NLP match tier
              const groups = [
                { min: 65, label: 'Best matches', items: [] },
                { min: 35, label: 'Possible matches', items: [] },
                { min: 0,  label: 'Partial matches', items: [] },
              ];
              for (const c of nlpResults) {
                const s = c.nlp_match_score ?? 0;
                const g = groups.find((g) => s >= g.min);
                if (g) g.items.push(c);
              }
              const nonEmpty = groups.filter((g) => g.items.length > 0);
              const showDividers = nonEmpty.length > 1;

              return nonEmpty.map((group) => (
                <div key={group.label}>
                  {showDividers && (
                    <div className="flex items-center gap-3 py-2">
                      <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">{group.label}</span>
                      <div className="h-px flex-1 bg-muted/50" />
                    </div>
                  )}
                  <div className="space-y-2">
                    {group.items.map((c) => {
                      const nlpTier = getNlpMatchTier(c.nlp_match_score ?? 0);
                      return (
                        <div
                          key={c.id}
                          onClick={() => setSelectedContact(c)}
                          onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') setSelectedContact(c); }}
                          role="button"
                          tabIndex={0}
                          aria-label={`${c.full_name}, ${nlpTier.label}${c.warm_score != null ? `, ${c.warm_score >= 70 ? 'Strong' : c.warm_score >= 40 ? 'Moderate' : 'Weak'} connection` : ''}, click to view details`}
                          className={`surface-interactive hover-lift cursor-pointer ${selectedContact?.id === c.id ? 'ring-1 ring-primary/50 bg-surface-raised' : ''}`}
                        >
                          <div className="flex items-center justify-between px-4 py-3">
                            <div className="flex items-center gap-3">
                              <div>
                                <p className="text-sm font-medium text-foreground">{c.full_name}</p>
                                <p className="text-xs text-muted-foreground">
                                  {c.current_title && `${c.current_title} at `}{c.current_company || ''}
                                </p>
                                {c.current_company && (
                                  <Link
                                    to={`/referrals?company=${encodeURIComponent(c.current_company)}`}
                                    onClick={(e) => e.stopPropagation()}
                                    className="text-xs text-primary hover:underline"
                                    aria-label={`Find referrals at ${c.current_company}`}
                                  >
                                    Find referrals at {c.current_company}
                                  </Link>
                                )}
                              </div>
                              <RelBadge
                                type={c.relationship_type}
                                onClick={(e) => { e.stopPropagation(); setSelectedContact(c); }}
                              />
                            </div>
                            <div className="flex items-center gap-3">
                              <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${nlpTier.color}`}>
                                {nlpTier.label}
                              </span>
                              {c.warm_score != null && (
                                <>
                                  <MatchBadge score={c.warm_score} type="warm" />
                                  <ScoreExplainer
                                    title="Connection Score"
                                    body="How strong your connection is. Higher means they're more likely to respond to your request."
                                    tiers={WARM_TIERS}
                                    learnMoreHref="/help/scores#connection-score"
                                  />
                                </>
                              )}
                              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="h-4 w-4 text-muted-foreground" aria-hidden="true">
                                <path fillRule="evenodd" d="M8.22 5.22a.75.75 0 0 1 1.06 0l4.25 4.25a.75.75 0 0 1 0 1.06l-4.25 4.25a.75.75 0 0 1-1.06-1.06L11.94 10 8.22 6.28a.75.75 0 0 1 0-1.06Z" clipRule="evenodd" />
                              </svg>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              ));
            })()}
          </div>
        )
      ) : loading ? (
        <ContactsPageSkeleton />
      ) : contactsList.length === 0 ? (
        filter ? (
          <div className="rounded-xl bg-card p-12 text-center border border-border">
            <p className="text-sm text-muted-foreground">No contacts match this filter.</p>
          </div>
        ) : (
          <div
            className="border-2 border-dashed border-border hover:border-primary/50 hover:shadow-[0_0_20px_var(--primary-glow)] transition-all duration-200 rounded-xl cursor-pointer"
            onClick={() => setShowBulkModal(true)}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') setShowBulkModal(true); }}
            aria-label="Upload LinkedIn CSV to import contacts"
          >
            <EmptyState
              illustration={noContactsIllustration}
              title="Import your professional network"
              description="Upload your LinkedIn connections CSV to see who can refer you. We'll score every contact by referral potential."
              stats={[
                { value: '4,000+', label: 'avg contacts per user' },
                { value: '< 30s', label: 'to upload' },
              ]}
              preview={
                <div className="flex items-center justify-between rounded-lg bg-muted/80 px-4 py-3">
                  <div className="text-left">
                    <p className="text-sm font-medium text-secondary-foreground">Sarah Chen</p>
                    <p className="text-xs text-muted-foreground">Senior PM at Stripe</p>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="rounded-full bg-success/10 px-2.5 py-0.5 text-xs font-medium text-success">Strong</span>
                    <span className="text-sm font-semibold text-primary">82</span>
                  </div>
                </div>
              }
              primaryAction={{ label: 'Upload LinkedIn CSV', onClick: (e) => { e?.stopPropagation(); setShowBulkModal(true); } }}
              secondaryAction={{
                label: 'How to export from LinkedIn \u2192',
                onClick: (e) => { e?.stopPropagation(); window.open('https://www.linkedin.com/help/linkedin/answer/a1339364', '_blank'); },
              }}
            />
          </div>
        )
      ) : (
        <div className="space-y-2">
          {contactsList.map((c, i) => {
            const score = c.warm_score ?? 0;
            const borderCls = score >= 70 ? 'border-l-2 border-l-success'
              : score >= 40 ? 'border-l-2 border-l-primary'
              : '';
            const opacityCls = score < 20 ? 'opacity-70' : '';
            const focusedCls = (focusedIndex === i || selectedContact?.id === c.id) ? 'ring-1 ring-primary/50 bg-surface-raised' : '';
            return (
              <div
                key={c.id}
                data-contact-index={i}
                onClick={() => setSelectedContact(c)}
                onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') setSelectedContact(c); }}
                role="button"
                tabIndex={0}
                aria-label={`${c.full_name}, click to view details`}
                className={`surface-interactive hover-lift cursor-pointer ${borderCls} ${opacityCls} ${focusedCls}`}
              >
                <div className="flex items-center justify-between px-4 py-3">
                  <div className="flex items-center gap-3">
                    <div>
                      <p className="text-sm font-medium text-foreground">{c.full_name}</p>
                      <p className="text-xs text-muted-foreground">
                        {c.current_title && `${c.current_title} at `}{c.current_company || ''}
                      </p>
                      {c.current_company && (
                        <Link
                          to={`/referrals?company=${encodeURIComponent(c.current_company)}`}
                          onClick={(e) => e.stopPropagation()}
                          className="text-xs text-primary hover:underline"
                          aria-label={`Find referrals at ${c.current_company}`}
                        >
                          Find referrals at {c.current_company}
                        </Link>
                      )}
                    </div>
                    <RelBadge
                      type={c.relationship_type}
                      onClick={(e) => { e.stopPropagation(); setSelectedContact(c); }}
                      showSetType={unclassifiedShowSet.has(c.id)}
                      animate={recentlyUpdatedId === c.id}
                    />
                    {c.relationship_type && score >= 40 && (
                      <span className={`h-2 w-2 shrink-0 rounded-full ${score >= 70 ? 'bg-success' : 'bg-primary'}`} aria-hidden="true" />
                    )}
                  </div>
                  <div className="flex items-center gap-3">
                    {score >= 70 && (
                      <span className="inline-flex items-center rounded-full bg-success/10 px-2 py-0.5 text-xs font-medium text-success">Strong</span>
                    )}
                    {score >= 40 && score < 70 && (
                      <span className="inline-flex items-center rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">Warm</span>
                    )}
                    {score >= 40 && (
                      <ScoreExplainer
                        title="Connection Score"
                        body="How strong your connection is. Higher means they're more likely to respond to your request."
                        tiers={WARM_TIERS}
                        learnMoreHref="/help/scores#connection-score"
                      />
                    )}
                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="h-4 w-4 text-muted-foreground" aria-hidden="true">
                      <path fillRule="evenodd" d="M8.22 5.22a.75.75 0 0 1 1.06 0l4.25 4.25a.75.75 0 0 1 0 1.06l-4.25 4.25a.75.75 0 0 1-1.06-1.06L11.94 10 8.22 6.28a.75.75 0 0 1 0-1.06Z" clipRule="evenodd" />
                    </svg>
                  </div>
                </div>
              </div>
            );
          })}

          {/* Pagination */}
          {totalPages > 1 && (
            <nav className="flex items-center justify-center gap-2 pt-4" role="navigation" aria-label="Contacts pagination">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1}
                aria-label="Previous page"
                className="rounded-md border border-border px-3 py-1.5 text-sm text-muted-foreground hover:bg-muted disabled:opacity-50"
              >
                Prev
              </button>
              <span className="text-sm text-muted-foreground" aria-current="page">Page {page} of {totalPages}</span>
              <button
                onClick={() => setPage((p) => p + 1)}
                disabled={page >= totalPages}
                aria-label="Next page"
                className="rounded-md border border-border px-3 py-1.5 text-sm text-muted-foreground hover:bg-muted disabled:opacity-50"
              >
                Next
              </button>
            </nav>
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
        <UploadModal
          onClose={() => setShowBulkModal(false)}
          onComplete={(uploadResult) => {
            load();
            if (uploadResult?.progress_phase?.startsWith('batch_')) {
              setBatchUpload(uploadResult);
            } else {
              setBatchUpload(null);
            }
          }}
          hasContacts={contactsList.length > 0}
        />
      )}

      <SlideOver open={!!selectedContact} onClose={() => setSelectedContact(null)} title="Contact Details">
        {selectedContact && (
          <ContactDetailPanel
            contact={selectedContact}
            onClose={() => setSelectedContact(null)}
            onContactUpdate={handleContactUpdate}
            onError={handleContactError}
          />
        )}
      </SlideOver>

      {toast && (
        <div className={`fixed bottom-24 left-1/2 z-50 -translate-x-1/2 rounded-lg px-4 py-2 text-sm font-medium text-white shadow-lg lg:bottom-8 ${toast.startsWith('Updated') ? 'bg-success/90' : 'bg-destructive/90'}`} role="alert" aria-live="polite">
          {toast}
        </div>
      )}
    </div>
  );
}
