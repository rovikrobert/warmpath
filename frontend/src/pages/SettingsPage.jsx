import { useEffect, useRef, useState } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { auth as authApi, privacy as privacyApi, marketplace as mpApi, contacts as contactsApi } from '../api/client';
import PasswordStrength from '../components/PasswordStrength';
import Spinner from '../components/ui/Spinner';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const TABS = [
  { key: 'profile', label: 'Profile' },
  { key: 'privacy', label: 'Privacy' },
  { key: 'sharing', label: 'Sharing' },
  { key: 'account', label: 'Account' },
];

const DEPARTMENT_OPTIONS = [
  'Engineering', 'Product', 'Design', 'Marketing', 'Sales',
  'Finance', 'Operations', 'HR / People', 'Legal', 'Data / Analytics',
  'Customer Success', 'Executive', 'Other',
];

const REGULATION_OPTIONS = ['GDPR', 'CCPA', 'PDPA', 'Other'];
const REQUEST_TYPES = [
  { value: 'access', label: 'Access my data' },
  { value: 'deletion', label: 'Delete my data' },
  { value: 'rectification', label: 'Correct my data' },
  { value: 'portability', label: 'Data portability' },
];

const EMPTY_ENTRY = { company: '', title: '', start_date: '', end_date: '', is_current: false };

const inputClass = 'w-full rounded-lg border border-slate-700/50 bg-slate-800 text-slate-100 placeholder-slate-500 px-3 py-2 text-sm focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500';

// ---------------------------------------------------------------------------
// Resume Preview Modal (reused from EditProfile)
// ---------------------------------------------------------------------------

function ResumePreviewModal({ data, onApply, onClose }) {
  if (!data) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" role="dialog" aria-modal="true" aria-labelledby="resume-preview-title">
      <div className="mx-4 w-full max-w-lg max-h-[80vh] overflow-y-auto rounded-xl bg-slate-900 p-6 shadow-xl border border-slate-700/50">
        <h3 id="resume-preview-title" className="text-lg font-bold text-slate-50">Resume Preview</h3>
        <p className="mt-1 text-sm text-slate-400">Review parsed data before applying to your profile.</p>
        <div className="mt-4 space-y-3 text-sm">
          {data.headline && <div><span className="font-medium text-slate-300">Headline:</span> {data.headline}</div>}
          {data.current_title && <div><span className="font-medium text-slate-300">Title:</span> {data.current_title}</div>}
          {data.current_company && <div><span className="font-medium text-slate-300">Company:</span> {data.current_company}</div>}
          {data.industry && <div><span className="font-medium text-slate-300">Industry:</span> {data.industry}</div>}
          {data.location && <div><span className="font-medium text-slate-300">Location:</span> {data.location}</div>}
          {data.bio_summary && <div><span className="font-medium text-slate-300">Summary:</span> {data.bio_summary}</div>}
          {data.work_history?.length > 0 && (
            <div>
              <span className="font-medium text-slate-300">Work History:</span>
              <ul className="mt-1 space-y-1 pl-4">
                {data.work_history.map((w, i) => (
                  <li key={i} className="text-slate-400">
                    {w.title} at {w.company} ({w.start_date || '?'} - {w.end_date || 'Present'})
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
        <div className="mt-5 flex gap-3">
          <button onClick={onClose} className="flex-1 rounded-lg border border-slate-700/50 py-2 text-sm font-medium text-slate-300 hover:bg-slate-800">Cancel</button>
          <button onClick={() => onApply(data)} className="flex-1 rounded-lg bg-amber-500 py-2 text-sm font-medium text-white hover:bg-amber-400">Apply to Profile</button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tab: Profile
// ---------------------------------------------------------------------------

function ProfileTab() {
  const [form, setForm] = useState({
    headline: '', current_company: '', current_title: '',
    industry: '', location: '', linkedin_url: '', bio_summary: '',
  });
  const [workHistory, setWorkHistory] = useState([]);
  const [loading, setLoading] = useState(false);
  const [saved, setSaved] = useState(false);
  const [matchFeedback, setMatchFeedback] = useState(null);
  const [error, setError] = useState('');
  const [resumePreview, setResumePreview] = useState(null);
  const [importLoading, setImportLoading] = useState('');
  const resumeRef = useRef(null);

  useEffect(() => {
    const stored = sessionStorage.getItem('linkedin_profile');
    if (stored) {
      try {
        const li = JSON.parse(stored);
        setForm((prev) => ({ ...prev, headline: prev.headline || li.name || '' }));
      } catch { /* ignore */ }
      sessionStorage.removeItem('linkedin_profile');
    }
  }, []);

  useEffect(() => {
    authApi.upsertProfile({}).then((res) => {
      const p = res.data;
      setForm({
        headline: p.headline || '', current_company: p.current_company || '',
        current_title: p.current_title || '', industry: p.industry || '',
        location: p.location || '', linkedin_url: p.linkedin_url || '',
        bio_summary: p.bio_summary || '',
      });
      if (p.work_history?.length) {
        setWorkHistory(p.work_history.map((e) => ({
          company: e.company || '', title: e.title || '',
          start_date: e.start_date || '', end_date: e.end_date || '',
          is_current: !e.end_date,
        })));
      }
    }).catch(() => {});
  }, []);

  const handleResumeUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setImportLoading('resume');
    setError('');
    try {
      const res = await authApi.uploadResume(file);
      setResumePreview(res.data);
    } catch (err) {
      setError(err.message);
    } finally {
      setImportLoading('');
      if (resumeRef.current) resumeRef.current.value = '';
    }
  };

  const applyResumeData = (data) => {
    setForm((prev) => ({
      headline: data.headline || prev.headline,
      current_company: data.current_company || prev.current_company,
      current_title: data.current_title || prev.current_title,
      industry: data.industry || prev.industry,
      location: data.location || prev.location,
      linkedin_url: prev.linkedin_url,
      bio_summary: data.bio_summary || prev.bio_summary,
    }));
    if (data.work_history?.length) {
      setWorkHistory((prev) => [...prev, ...data.work_history.map((w) => ({
        company: w.company || '', title: w.title || '',
        start_date: w.start_date || '', end_date: w.end_date || '',
        is_current: !w.end_date,
      }))]);
    }
    setResumePreview(null);
    setSaved(false);
  };

  const handleLinkedInImport = async () => {
    setImportLoading('linkedin');
    setError('');
    try {
      const res = await authApi.linkedinAuthorize();
      window.location.href = res.data.url;
    } catch (err) {
      setError(err.message);
      setImportLoading('');
    }
  };

  const set = (key) => (e) => { setForm({ ...form, [key]: e.target.value }); setSaved(false); };
  const updateWorkEntry = (index, key, value) => {
    setWorkHistory((wh) => wh.map((entry, i) => i === index ? { ...entry, [key]: value } : entry));
    setSaved(false);
  };
  const addWorkEntry = () => { setWorkHistory((wh) => [...wh, { ...EMPTY_ENTRY }]); setSaved(false); };
  const removeWorkEntry = (index) => { setWorkHistory((wh) => wh.filter((_, i) => i !== index)); setSaved(false); };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    setMatchFeedback(null);
    try {
      const body = {
        ...form,
        work_history: workHistory.filter((e) => e.company.trim()).map((e) => ({
          company: e.company, title: e.title || undefined,
          start_date: e.start_date || undefined,
          end_date: e.is_current ? undefined : (e.end_date || undefined),
        })),
      };
      const res = await authApi.upsertProfile(body);
      setSaved(true);
      if (res.data?.work_history?.length > 0) {
        try {
          const contactsRes = await contactsApi.list({ per_page: 1 });
          const total = contactsRes.meta?.total ?? 0;
          if (total > 0) setMatchFeedback('Work history saved! Contacts at your former companies now have boosted referral scores.');
        } catch { /* ignore */ }
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      {/* Import Profile Card */}
      <div className="mb-6 rounded-xl bg-slate-900 p-6 border border-slate-700/50">
        <h2 className="text-sm font-semibold text-slate-50">Import Profile</h2>
        <p className="mt-1 text-xs text-slate-400">Pre-fill your profile from a resume or LinkedIn.</p>
        <div className="mt-3 flex gap-3">
          <div>
            <input ref={resumeRef} type="file" accept=".pdf" onChange={handleResumeUpload} className="hidden" aria-label="Upload resume PDF" />
            <button type="button" onClick={() => resumeRef.current?.click()} disabled={importLoading === 'resume'} className="rounded-lg border border-amber-500 px-4 py-2 text-sm font-medium text-amber-400 hover:bg-amber-500/10 disabled:opacity-50">
              {importLoading === 'resume' ? 'Parsing...' : 'Import from Resume (PDF)'}
            </button>
          </div>
          <button type="button" onClick={handleLinkedInImport} disabled={importLoading === 'linkedin'} className="rounded-lg px-4 py-2 text-sm font-medium text-white disabled:opacity-50" style={{ backgroundColor: '#0A66C2' }}>
            {importLoading === 'linkedin' ? 'Redirecting...' : 'Import from LinkedIn'}
          </button>
        </div>
      </div>

      <ResumePreviewModal data={resumePreview} onApply={applyResumeData} onClose={() => setResumePreview(null)} />

      <form onSubmit={handleSubmit} className="space-y-4 rounded-xl bg-slate-900 p-6 border border-slate-700/50">
        <p className="text-sm text-slate-400">Your profile is used as context when AI drafts intro messages on your behalf.</p>

        <div>
          <label htmlFor="profile-headline" className="mb-1 block text-sm font-medium text-slate-300">Headline</label>
          <input id="profile-headline" type="text" value={form.headline} onChange={set('headline')} className={inputClass} placeholder="B2B GTM Leader | Field Marketing..." />
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label htmlFor="profile-title" className="mb-1 block text-sm font-medium text-slate-300">Title</label>
            <input id="profile-title" type="text" value={form.current_title} onChange={set('current_title')} className={inputClass} placeholder="Managing Director" />
          </div>
          <div>
            <label htmlFor="profile-company" className="mb-1 block text-sm font-medium text-slate-300">Company</label>
            <input id="profile-company" type="text" value={form.current_company} onChange={set('current_company')} className={inputClass} placeholder="Acme Corp" />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label htmlFor="profile-industry" className="mb-1 block text-sm font-medium text-slate-300">Industry</label>
            <input id="profile-industry" type="text" value={form.industry} onChange={set('industry')} className={inputClass} placeholder="Professional Services" />
          </div>
          <div>
            <label htmlFor="profile-location" className="mb-1 block text-sm font-medium text-slate-300">Location</label>
            <input id="profile-location" type="text" value={form.location} onChange={set('location')} className={inputClass} placeholder="Singapore" />
          </div>
        </div>

        <div>
          <label htmlFor="profile-linkedin-url" className="mb-1 block text-sm font-medium text-slate-300">LinkedIn URL</label>
          <input id="profile-linkedin-url" type="url" value={form.linkedin_url} onChange={set('linkedin_url')} className={inputClass} placeholder="https://linkedin.com/in/yourname" />
        </div>

        <div>
          <label htmlFor="profile-bio" className="mb-1 block text-sm font-medium text-slate-300">Bio summary</label>
          <textarea id="profile-bio" value={form.bio_summary} onChange={set('bio_summary')} rows={3} className={inputClass} placeholder="What you do and who you help..." />
        </div>

        {/* Work History */}
        <div className="border-t border-slate-700/50 pt-4">
          <div className="mb-3 flex items-center justify-between">
            <div>
              <h3 className="text-sm font-semibold text-slate-50">Work History</h3>
              <p className="text-xs text-slate-400">Helps match you with contacts at your former companies.</p>
            </div>
            <button type="button" onClick={addWorkEntry} className="rounded-md border border-amber-500 px-3 py-1 text-xs font-medium text-amber-400 hover:bg-amber-500/10">Add another</button>
          </div>

          {workHistory.length === 0 && (
            <div className="rounded-lg border border-dashed border-slate-700/50 p-4 text-center">
              <p className="text-sm text-slate-400">No work history added yet.</p>
              <button type="button" onClick={addWorkEntry} className="mt-2 text-sm font-medium text-amber-400 hover:text-amber-300">Add your first role</button>
            </div>
          )}

          <div className="space-y-3">
            {workHistory.map((entry, i) => (
              <div key={i} className="rounded-lg bg-slate-800/50 border border-slate-700/50 p-3">
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label htmlFor={`work-company-${i}`} className="mb-1 block text-xs font-medium text-slate-300">Company</label>
                    <input id={`work-company-${i}`} type="text" value={entry.company} onChange={(e) => updateWorkEntry(i, 'company', e.target.value)} className={inputClass} placeholder="Company name" />
                  </div>
                  <div>
                    <label htmlFor={`work-title-${i}`} className="mb-1 block text-xs font-medium text-slate-300">Title / Role</label>
                    <input id={`work-title-${i}`} type="text" value={entry.title} onChange={(e) => updateWorkEntry(i, 'title', e.target.value)} className={inputClass} placeholder="e.g. Software Engineer" />
                  </div>
                </div>
                <div className="mt-2 grid grid-cols-2 gap-3">
                  <div>
                    <label htmlFor={`work-start-${i}`} className="mb-1 block text-xs font-medium text-slate-300">Start date</label>
                    <input id={`work-start-${i}`} type="month" value={entry.start_date} onChange={(e) => updateWorkEntry(i, 'start_date', e.target.value)} className={inputClass} />
                  </div>
                  <div>
                    <label htmlFor={`work-end-${i}`} className="mb-1 block text-xs font-medium text-slate-300">End date</label>
                    {entry.is_current ? (
                      <p className="py-2 text-sm text-slate-400">Present</p>
                    ) : (
                      <input id={`work-end-${i}`} type="month" value={entry.end_date} onChange={(e) => updateWorkEntry(i, 'end_date', e.target.value)} className={inputClass} />
                    )}
                  </div>
                </div>
                <div className="mt-2 flex items-center justify-between">
                  <label className="flex items-center gap-2 text-xs text-slate-400">
                    <input type="checkbox" checked={entry.is_current} onChange={(e) => updateWorkEntry(i, 'is_current', e.target.checked)} className="h-3.5 w-3.5 rounded border-slate-600 bg-slate-800 text-amber-500 focus:ring-amber-500" />
                    I currently work here
                  </label>
                  <button type="button" onClick={() => removeWorkEntry(i)} className="text-xs text-red-400 hover:text-red-300" aria-label={`Remove work history entry ${i + 1}`}>Remove</button>
                </div>
              </div>
            ))}
          </div>
        </div>

        {error && <p className="rounded-md bg-red-500/10 p-2 text-sm text-red-400" role="alert" aria-live="assertive">{error}</p>}
        {saved && <p className="rounded-md bg-emerald-500/10 p-2 text-sm text-emerald-400" role="status" aria-live="polite">Profile saved!</p>}
        {matchFeedback && <p className="rounded-md bg-blue-500/10 p-2 text-sm text-blue-400" role="status" aria-live="polite">{matchFeedback}</p>}

        <button type="submit" disabled={loading} className="w-full rounded-lg bg-amber-500 py-2.5 text-sm font-medium text-white hover:bg-amber-400 disabled:opacity-50">
          {loading ? 'Saving...' : 'Save Profile'}
        </button>
      </form>
    </>
  );
}

// ---------------------------------------------------------------------------
// Tab: Privacy
// ---------------------------------------------------------------------------

function PrivacyTab() {
  const { user } = useAuth();
  const [loading, setLoading] = useState(true);
  const [restricted, setRestricted] = useState(false);
  const [marketingOptedOut, setMarketingOptedOut] = useState(false);
  const [consentRecords, setConsentRecords] = useState([]);
  const [togglingRestrict, setTogglingRestrict] = useState(false);
  const [togglingMarketing, setTogglingMarketing] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [exportDone, setExportDone] = useState(false);
  const [error, setError] = useState('');

  // Data request form
  const [requestType, setRequestType] = useState('access');
  const [requestDetails, setRequestDetails] = useState('');
  const [requestRegulation, setRequestRegulation] = useState('GDPR');
  const [submittingRequest, setSubmittingRequest] = useState(false);
  const [requestSuccess, setRequestSuccess] = useState('');

  useEffect(() => {
    (async () => {
      try {
        const consentRes = await privacyApi.listConsent().catch(() => ({ data: [] }));
        setConsentRecords(consentRes.data || []);
        setRestricted(user?.processing_restricted || false);
        setMarketingOptedOut(user?.marketing_opt_out || false);
      } catch { /* non-critical */ }
      finally { setLoading(false); }
    })();
  }, [user]);

  const handleExport = async () => {
    setExporting(true); setError('');
    try {
      const res = await privacyApi.exportData();
      const blob = new Blob([JSON.stringify(res.data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = 'warmpath-data-export.json'; a.click();
      URL.revokeObjectURL(url);
      setExportDone(true);
    } catch (err) { setError(err.message); }
    finally { setExporting(false); }
  };

  const handleToggleRestrict = async () => {
    setTogglingRestrict(true); setError('');
    try {
      if (restricted) { await privacyApi.unrestrictProcessing(); setRestricted(false); }
      else { await privacyApi.restrictProcessing(); setRestricted(true); }
    } catch (err) { setError(err.message); }
    finally { setTogglingRestrict(false); }
  };

  const handleToggleMarketing = async () => {
    setTogglingMarketing(true); setError('');
    try {
      if (marketingOptedOut) { await privacyApi.marketingOptIn(); setMarketingOptedOut(false); }
      else { await privacyApi.marketingOptOut(); setMarketingOptedOut(true); }
    } catch (err) { setError(err.message); }
    finally { setTogglingMarketing(false); }
  };

  const handleDataRequest = async (e) => {
    e.preventDefault();
    setSubmittingRequest(true); setError(''); setRequestSuccess('');
    try {
      await privacyApi.dataRequest({ request_type: requestType, details: requestDetails.trim() || undefined, regulation: requestRegulation });
      setRequestSuccess('Your request has been submitted. We will respond within the regulatory deadline.');
      setRequestDetails('');
    } catch (err) { setError(err.message); }
    finally { setSubmittingRequest(false); }
  };

  if (loading) {
    return <div className="flex items-center justify-center py-12"><Spinner /></div>;
  }

  return (
    <div className="space-y-6">
      {error && <div role="alert" aria-live="polite" className="rounded-lg bg-red-500/10 p-3 text-sm text-red-400">{error}</div>}

      {/* Data Export */}
      <section className="rounded-xl bg-slate-900 p-5 border border-slate-700/50" aria-label="Data export">
        <h2 className="mb-1 text-base font-semibold text-slate-50">Download My Data</h2>
        <p className="mb-3 text-sm text-slate-400">Export all your personal data as a JSON file.</p>
        <button onClick={handleExport} disabled={exporting} className="rounded-lg bg-amber-500 px-4 py-2 text-sm font-medium text-white hover:bg-amber-400 disabled:opacity-50">
          {exporting ? 'Preparing...' : exportDone ? 'Download Again' : 'Download My Data'}
        </button>
        {exportDone && <p className="mt-2 text-xs text-emerald-400" role="status">Download started.</p>}
      </section>

      {/* Processing Restriction */}
      <section className="rounded-xl bg-slate-900 p-5 border border-slate-700/50" aria-label="Processing restriction">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-base font-semibold text-slate-50">Restrict Processing</h2>
            <p className="text-sm text-slate-400">Limit how we process your data. Some features may be unavailable.</p>
          </div>
          <button onClick={handleToggleRestrict} disabled={togglingRestrict} role="switch" aria-checked={restricted} aria-label="Restrict data processing"
            className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full transition-colors duration-200 ${restricted ? 'bg-amber-500' : 'bg-slate-600'} disabled:opacity-50`}>
            <span className={`inline-block h-5 w-5 transform rounded-full bg-white shadow transition-transform duration-200 ${restricted ? 'translate-x-5' : 'translate-x-0.5'} mt-0.5`} />
          </button>
        </div>
      </section>

      {/* Marketing Preferences */}
      <section className="rounded-xl bg-slate-900 p-5 border border-slate-700/50" aria-label="Marketing preferences">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-base font-semibold text-slate-50">Marketing Communications</h2>
            <p className="text-sm text-slate-400">{marketingOptedOut ? 'You have opted out of marketing emails.' : 'Receive product updates and tips.'}</p>
          </div>
          <button onClick={handleToggleMarketing} disabled={togglingMarketing} role="switch" aria-checked={!marketingOptedOut} aria-label="Marketing communications"
            className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full transition-colors duration-200 ${!marketingOptedOut ? 'bg-amber-500' : 'bg-slate-600'} disabled:opacity-50`}>
            <span className={`inline-block h-5 w-5 transform rounded-full bg-white shadow transition-transform duration-200 ${!marketingOptedOut ? 'translate-x-5' : 'translate-x-0.5'} mt-0.5`} />
          </button>
        </div>
      </section>

      {/* Consent Records */}
      <section className="rounded-xl bg-slate-900 p-5 border border-slate-700/50" aria-label="Consent records">
        <h2 className="mb-3 text-base font-semibold text-slate-50">Consent Records</h2>
        {consentRecords.length === 0 ? (
          <p className="text-sm text-slate-400">No consent records on file.</p>
        ) : (
          <div className="space-y-2">
            {consentRecords.map((record, i) => (
              <div key={record.id || i} className="flex items-center justify-between rounded-lg border border-slate-700/50 p-3">
                <div>
                  <p className="text-sm font-medium text-slate-50">{record.processing_activity || record.activity}</p>
                  <p className="text-xs text-slate-400">
                    {record.status || (record.consented ? 'Consented' : 'Withdrawn')}
                    {record.created_at && ` — ${new Date(record.created_at).toLocaleDateString()}`}
                  </p>
                </div>
                <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${record.consented || record.status === 'granted' ? 'bg-emerald-500/10 text-emerald-400' : 'bg-slate-700/50 text-slate-400'}`}>
                  {record.consented || record.status === 'granted' ? 'Active' : 'Withdrawn'}
                </span>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Formal Data Request */}
      <section className="rounded-xl bg-slate-900 p-5 border border-slate-700/50" aria-label="Formal data request">
        <h2 className="mb-1 text-base font-semibold text-slate-50">Formal Data Request</h2>
        <p className="mb-3 text-sm text-slate-400">Submit a formal data subject access request (DSAR).</p>
        <form onSubmit={handleDataRequest} className="space-y-3">
          <div>
            <label htmlFor="request-type" className="mb-1 block text-sm font-medium text-slate-300">Request type</label>
            <select id="request-type" value={requestType} onChange={(e) => setRequestType(e.target.value)} className={inputClass}>
              {REQUEST_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
            </select>
          </div>
          <div>
            <label htmlFor="request-details" className="mb-1 block text-sm font-medium text-slate-300">Details <span className="text-slate-500">(optional)</span></label>
            <textarea id="request-details" value={requestDetails} onChange={(e) => setRequestDetails(e.target.value)} placeholder="Any specific details..." rows={3} className={inputClass} />
          </div>
          <div>
            <label htmlFor="request-regulation" className="mb-1 block text-sm font-medium text-slate-300">Regulation</label>
            <select id="request-regulation" value={requestRegulation} onChange={(e) => setRequestRegulation(e.target.value)} className={inputClass}>
              {REGULATION_OPTIONS.map((r) => <option key={r} value={r}>{r}</option>)}
            </select>
          </div>
          {requestSuccess && <p role="status" className="rounded-md bg-emerald-500/10 p-2 text-sm text-emerald-400">{requestSuccess}</p>}
          <button type="submit" disabled={submittingRequest} className="rounded-lg bg-amber-500 px-4 py-2 text-sm font-medium text-white hover:bg-amber-400 disabled:opacity-50">
            {submittingRequest ? 'Submitting...' : 'Submit Request'}
          </button>
        </form>
      </section>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tab: Sharing (NH-only)
// ---------------------------------------------------------------------------

function SharingTab() {
  const [prefs, setPrefs] = useState(null);
  const [contacts, setContacts] = useState([]);
  const [excludedIds, setExcludedIds] = useState([]);
  const [categoryFilters, setCategoryFilters] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');

  useEffect(() => {
    (async () => {
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
      } catch { /* ignore */ }
      finally { setLoading(false); }
    })();
  }, []);

  const handleSave = async () => {
    setSaving(true); setSaved(false);
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
    } catch { /* ignore */ }
    finally { setSaving(false); }
  };

  const toggleDepartment = (dept) => {
    setCategoryFilters((prev) => prev.includes(dept) ? prev.filter((d) => d !== dept) : [...prev, dept]);
  };
  const toggleExclude = (id) => {
    setExcludedIds((prev) => prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]);
  };

  const filteredContacts = contacts.filter((c) => {
    if (!searchTerm) return false;
    const term = searchTerm.toLowerCase();
    return c.full_name?.toLowerCase().includes(term) || c.current_company?.toLowerCase().includes(term) || c.current_title?.toLowerCase().includes(term);
  });

  if (loading) {
    return <div className="flex items-center justify-center py-12"><Spinner /></div>;
  }

  return (
    <div className="space-y-6">
      {/* Privacy explainer */}
      <div className="rounded-lg border border-blue-500/30 bg-blue-500/10 p-4">
        <h3 className="mb-1 text-sm font-semibold text-blue-400">How marketplace sharing works</h3>
        <p className="text-sm text-blue-400">
          Job seekers see <strong>role level and department only</strong> — never names or contact details.
          When someone requests an intro, you see their profile and choose whether to introduce them.
        </p>
      </div>

      {/* Share toggle */}
      <div className="rounded-xl bg-slate-900 p-5 border border-slate-700/50">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-base font-semibold text-slate-50">Share my network on the marketplace</h2>
            <p className="text-sm text-slate-400">
              {prefs?.opt_in_marketplace
                ? 'Your contacts are visible (anonymized) to job seekers. Referral bonus ($2-10K) goes to you.'
                : 'Enable sharing to capture referral bonuses ($2-10K per hire) and earn credits.'}
            </p>
          </div>
          <button onClick={() => setPrefs({ ...prefs, opt_in_marketplace: !prefs.opt_in_marketplace })} role="switch" aria-checked={!!prefs?.opt_in_marketplace} aria-label="Share my network"
            className={`relative h-6 w-11 rounded-full transition ${prefs?.opt_in_marketplace ? 'bg-amber-500' : 'bg-slate-600'}`}>
            <span aria-hidden="true" className="absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition" style={{ left: prefs?.opt_in_marketplace ? '22px' : '2px' }} />
          </button>
        </div>
      </div>

      {/* Pause toggle */}
      <div className="rounded-xl bg-slate-900 p-5 border border-slate-700/50">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-base font-semibold text-slate-50">Temporarily hide all my listings</h2>
            <p className="text-sm text-slate-400">Pause sharing without losing your listings.</p>
          </div>
          <button onClick={() => setPrefs({ ...prefs, is_paused: !prefs.is_paused })} role="switch" aria-checked={!!prefs?.is_paused} aria-label="Temporarily hide listings"
            className={`relative h-6 w-11 rounded-full transition ${prefs?.is_paused ? 'bg-amber-500' : 'bg-slate-600'}`}>
            <span aria-hidden="true" className="absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition" style={{ left: prefs?.is_paused ? '22px' : '2px' }} />
          </button>
        </div>
      </div>

      {/* Category filters */}
      <div className="rounded-xl bg-slate-900 p-5 border border-slate-700/50">
        <h2 className="mb-1 text-base font-semibold text-slate-50">Department Filters</h2>
        <p className="mb-3 text-sm text-slate-400">Only share contacts in selected departments. Leave all unchecked to share all.</p>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          {DEPARTMENT_OPTIONS.map((dept) => (
            <label key={dept} className="flex items-center gap-2 rounded-lg border border-slate-700/50 p-2 text-sm hover:bg-slate-800">
              <input type="checkbox" checked={categoryFilters.includes(dept)} onChange={() => toggleDepartment(dept)} className="h-4 w-4 rounded border-slate-600 bg-slate-800 text-amber-500 focus:ring-amber-500" />
              <span className="text-slate-300">{dept}</span>
            </label>
          ))}
        </div>
      </div>

      {/* Excluded contacts */}
      <div className="rounded-xl bg-slate-900 p-5 border border-slate-700/50">
        <h2 className="mb-1 text-base font-semibold text-slate-50">Excluded Contacts</h2>
        <p className="mb-3 text-sm text-slate-400">Search and select contacts to exclude from the marketplace.</p>
        <input type="text" value={searchTerm} onChange={(e) => setSearchTerm(e.target.value)} placeholder="Search by name, company, or title..." aria-label="Search contacts to exclude" className={'mb-3 ' + inputClass} />
        {filteredContacts.length > 0 && (
          <div className="mb-3 max-h-48 overflow-y-auto rounded-lg border border-slate-700/50">
            {filteredContacts.slice(0, 20).map((c) => (
              <label key={c.id} className="flex items-center gap-2 border-b border-slate-700/50 px-3 py-2 text-sm last:border-0 hover:bg-slate-800">
                <input type="checkbox" checked={excludedIds.includes(c.id)} onChange={() => toggleExclude(c.id)} className="h-4 w-4 rounded border-slate-600 bg-slate-800 text-red-500 focus:ring-red-500" />
                <span className="text-slate-50">{c.full_name}</span>
                {c.current_title && <span className="text-slate-400">— {c.current_title}</span>}
                {c.current_company && <span className="text-xs text-slate-400">at {c.current_company}</span>}
              </label>
            ))}
          </div>
        )}
        {excludedIds.length > 0 && <p className="text-xs text-slate-400">{excludedIds.length} contact{excludedIds.length !== 1 ? 's' : ''} excluded</p>}
      </div>

      {/* Save */}
      <div className="flex items-center gap-3">
        <button onClick={handleSave} disabled={saving} className="rounded-lg bg-amber-500 px-6 py-2.5 text-sm font-medium text-white hover:bg-amber-400 disabled:opacity-50">
          {saving ? 'Saving...' : 'Save Settings'}
        </button>
        {saved && <span className="text-sm text-emerald-400" role="status" aria-live="polite">Settings saved!</span>}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tab: Account
// ---------------------------------------------------------------------------

function AccountTab() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  // Change password state
  const [oldPassword, setOldPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [pwLoading, setPwLoading] = useState(false);
  const [pwSuccess, setPwSuccess] = useState('');
  const [pwError, setPwError] = useState('');

  // Delete account state
  const [showDelete, setShowDelete] = useState(false);
  const [deletePassword, setDeletePassword] = useState('');
  const [deleteConfirmed, setDeleteConfirmed] = useState(false);
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [deleteError, setDeleteError] = useState('');

  const handleChangePassword = async (e) => {
    e.preventDefault();
    if (newPassword !== confirmPassword) {
      setPwError('New passwords do not match'); return;
    }
    setPwLoading(true); setPwError(''); setPwSuccess('');
    try {
      await authApi.changePassword({ old_password: oldPassword, new_password: newPassword });
      setPwSuccess('Password changed successfully.');
      setOldPassword(''); setNewPassword(''); setConfirmPassword('');
    } catch (err) {
      setPwError(err.message);
    } finally {
      setPwLoading(false);
    }
  };

  const handleDeleteAccount = async () => {
    if (!deleteConfirmed || !deletePassword) return;
    setDeleteLoading(true); setDeleteError('');
    try {
      await authApi.deleteAccount({ password: deletePassword, confirm_deletion: true });
      logout();
      navigate('/');
    } catch (err) {
      setDeleteError(err.message);
    } finally {
      setDeleteLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Account info */}
      <section className="rounded-xl bg-slate-900 p-5 border border-slate-700/50" aria-label="Account info">
        <h2 className="mb-3 text-base font-semibold text-slate-50">Account Info</h2>
        <div className="space-y-2 text-sm">
          <div className="flex items-center gap-2">
            <span className="font-medium text-slate-300">Name:</span>
            <span className="text-slate-400">{user?.full_name || '—'}</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="font-medium text-slate-300">Email:</span>
            <span className="text-slate-400">{user?.email || '—'}</span>
            {user?.email_verified ? (
              <span className="rounded-full bg-emerald-500/10 px-2 py-0.5 text-xs text-emerald-400">Verified</span>
            ) : (
              <span className="rounded-full bg-amber-500/10 px-2 py-0.5 text-xs text-amber-400">Unverified</span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <span className="font-medium text-slate-300">Account type:</span>
            <span className="text-slate-400 capitalize">{user?.user_type?.replace('_', ' ') || 'Not set'}</span>
          </div>
        </div>
      </section>

      {/* Change Password */}
      <section className="rounded-xl bg-slate-900 p-5 border border-slate-700/50" aria-label="Change password">
        <h2 className="mb-3 text-base font-semibold text-slate-50">Change Password</h2>
        <form onSubmit={handleChangePassword} className="space-y-3">
          <div>
            <label htmlFor="old-password" className="mb-1 block text-sm font-medium text-slate-300">Current password</label>
            <input id="old-password" type="password" value={oldPassword} onChange={(e) => setOldPassword(e.target.value)} className={inputClass} placeholder="Enter current password" required aria-required="true" />
          </div>
          <div>
            <label htmlFor="new-password" className="mb-1 block text-sm font-medium text-slate-300">New password</label>
            <input id="new-password" type="password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} className={inputClass} placeholder="Enter new password" required aria-required="true" />
            <PasswordStrength password={newPassword} />
          </div>
          <div>
            <label htmlFor="confirm-password" className="mb-1 block text-sm font-medium text-slate-300">Confirm new password</label>
            <input id="confirm-password" type="password" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} className={inputClass} placeholder="Confirm new password" required aria-required="true" />
          </div>
          {pwError && <p role="alert" className="rounded-md bg-red-500/10 p-2 text-sm text-red-400">{pwError}</p>}
          {pwSuccess && <p role="status" className="rounded-md bg-emerald-500/10 p-2 text-sm text-emerald-400">{pwSuccess}</p>}
          <button type="submit" disabled={pwLoading || !oldPassword || !newPassword || !confirmPassword} className="rounded-lg bg-amber-500 px-4 py-2 text-sm font-medium text-white hover:bg-amber-400 disabled:opacity-50">
            {pwLoading ? 'Changing...' : 'Change Password'}
          </button>
        </form>
      </section>

      {/* Delete Account — Danger Zone */}
      <section className="rounded-xl border-2 border-red-500/30 bg-red-500/10 p-5" aria-label="Delete account">
        <h2 className="mb-1 text-base font-semibold text-red-400">Delete Account</h2>
        <p className="mb-2 text-sm text-slate-400">Permanently delete your account, contacts, search history, and all associated data. This action cannot be undone.</p>
        <ul className="mb-3 space-y-1 text-xs text-slate-400">
          <li>All data permanently deleted (contacts, searches, applications, messages)</li>
          <li>Credits forfeited with no refund</li>
          <li>Active subscriptions must be cancelled first</li>
        </ul>

        {!showDelete ? (
          <button onClick={() => { setShowDelete(true); setDeletePassword(''); setDeleteConfirmed(false); setDeleteError(''); }}
            className="rounded-lg border border-red-500/30 px-4 py-2 text-sm font-medium text-red-400 hover:bg-red-500/20">
            Delete My Account
          </button>
        ) : (
          <div className="space-y-3">
            <label className="flex items-start gap-2 text-sm text-slate-300">
              <input type="checkbox" checked={deleteConfirmed} onChange={(e) => setDeleteConfirmed(e.target.checked)}
                className="mt-0.5 h-4 w-4 rounded border-slate-600 bg-slate-800 text-red-500 focus:ring-red-500" />
              I understand this action is permanent and my data cannot be recovered
            </label>
            <div>
              <label htmlFor="delete-password" className="mb-1 block text-sm font-medium text-slate-300">Enter your password to confirm</label>
              <input id="delete-password" type="password" value={deletePassword} onChange={(e) => setDeletePassword(e.target.value)}
                className={inputClass} placeholder="Your current password" aria-required="true" />
            </div>
            {deleteError && <p className="rounded-md bg-red-500/10 p-2 text-sm text-red-400" role="alert">{deleteError}</p>}
            <div className="flex gap-2">
              <button onClick={handleDeleteAccount} disabled={!deleteConfirmed || !deletePassword || deleteLoading}
                className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50">
                {deleteLoading ? 'Deleting...' : 'Permanently Delete'}
              </button>
              <button onClick={() => { setShowDelete(false); setDeleteConfirm(''); }}
                className="rounded-lg border border-slate-700/50 px-4 py-2 text-sm text-slate-400 hover:bg-slate-800">Cancel</button>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main SettingsPage
// ---------------------------------------------------------------------------

export default function SettingsPage() {
  const { user } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const activeTab = searchParams.get('tab') || 'profile';

  const isHolder = user?.user_type === 'network_holder' || user?.user_type === 'both';

  // Filter tabs — Sharing only visible to network holders / both
  const visibleTabs = TABS.filter((t) => t.key !== 'sharing' || isHolder);

  const switchTab = (key) => {
    setSearchParams({ tab: key }, { replace: true });
  };

  const renderTab = () => {
    switch (activeTab) {
      case 'profile': return <ProfileTab />;
      case 'privacy': return <PrivacyTab />;
      case 'sharing': return isHolder ? <SharingTab /> : <ProfileTab />;
      case 'account': return <AccountTab />;
      default: return <ProfileTab />;
    }
  };

  return (
    <div className="mx-auto max-w-4xl" role="main">
      <h1 className="mb-6 text-xl font-bold text-slate-50">Settings</h1>

      <div className="flex gap-8">
        {/* Side tab nav */}
        <nav className="w-44 shrink-0" aria-label="Settings tabs">
          <ul className="space-y-1" role="tablist">
            {visibleTabs.map((tab) => (
              <li key={tab.key}>
                <button
                  role="tab"
                  aria-selected={activeTab === tab.key}
                  aria-controls={`settings-panel-${tab.key}`}
                  onClick={() => switchTab(tab.key)}
                  className={`w-full rounded-lg px-3 py-2 text-left text-sm font-medium transition ${
                    activeTab === tab.key
                      ? 'bg-amber-500/10 text-amber-400'
                      : 'text-slate-400 hover:bg-slate-800 hover:text-slate-100'
                  }`}
                >
                  {tab.label}
                </button>
              </li>
            ))}
          </ul>
        </nav>

        {/* Tab content */}
        <div className="min-w-0 flex-1" id={`settings-panel-${activeTab}`} role="tabpanel">
          {renderTab()}
        </div>
      </div>
    </div>
  );
}
