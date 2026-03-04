import { useEffect, useRef, useState } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { useUser as useClerkUser } from '@clerk/clerk-react';
import { QRCodeSVG } from 'qrcode.react';
import { useAuth } from '../context/AuthContext';
import { auth as authApi, privacy as privacyApi, marketplace as mpApi, contacts as contactsApi, preferences as prefsApi } from '../api/client';
import { SOURCES } from '../utils/sources';
import SourceTag from '../components/ui/SourceTag';
import Spinner from '../components/ui/Spinner';
import useDocumentTitle from '../hooks/useDocumentTitle';

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

const inputClass = 'w-full rounded-lg border border-border bg-muted text-foreground placeholder:text-muted-foreground px-3 py-2 text-sm focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring';

// ---------------------------------------------------------------------------
// Resume Preview Modal (reused from EditProfile)
// ---------------------------------------------------------------------------

function ResumePreviewModal({ data, onApply, onClose }) {
  if (!data) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" role="dialog" aria-modal="true" aria-labelledby="resume-preview-title">
      <div className="mx-4 w-full max-w-lg max-h-[80vh] overflow-y-auto rounded-xl bg-card p-6 shadow-xl border border-border">
        <h3 id="resume-preview-title" className="text-lg font-bold text-foreground">Resume Preview</h3>
        <p className="mt-1 text-sm text-muted-foreground">Review parsed data before applying to your profile.</p>
        <div className="mt-4 space-y-3 text-sm">
          {data.headline && <div><span className="font-medium text-secondary-foreground">Headline:</span> {data.headline}</div>}
          {data.current_title && <div><span className="font-medium text-secondary-foreground">Title:</span> {data.current_title}</div>}
          {data.current_company && <div><span className="font-medium text-secondary-foreground">Company:</span> {data.current_company}</div>}
          {data.industry && <div><span className="font-medium text-secondary-foreground">Industry:</span> {data.industry}</div>}
          {data.location && <div><span className="font-medium text-secondary-foreground">Location:</span> {data.location}</div>}
          {data.bio_summary && <div><span className="font-medium text-secondary-foreground">Summary:</span> {data.bio_summary}</div>}
          {data.work_history?.length > 0 && (
            <div>
              <span className="font-medium text-secondary-foreground">Work History:</span>
              <ul className="mt-1 space-y-1 pl-4">
                {data.work_history.map((w, i) => (
                  <li key={i} className="text-muted-foreground">
                    {w.title} at {w.company} ({w.start_date || '?'} - {w.end_date || 'Present'})
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
        <div className="mt-5 flex gap-3">
          <button onClick={onClose} className="flex-1 rounded-lg border border-border py-2 text-sm font-medium text-secondary-foreground hover:bg-muted cursor-pointer transition-colors duration-200">Cancel</button>
          <button onClick={() => onApply(data)} className="flex-1 rounded-lg bg-primary py-2 text-sm font-medium text-white hover:bg-primary/90 cursor-pointer transition-colors duration-200">Apply to Profile</button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tab: Profile
// ---------------------------------------------------------------------------

function SearchFocusCard() {
  const [targetRole, setTargetRole] = useState('');
  const [targetSeniority, setTargetSeniority] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    prefsApi.getJob()
      .then((res) => {
        const p = res.data;
        setTargetRole(p.target_role || '');
        setTargetSeniority(p.target_seniority || '');
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const handleSave = async (e) => {
    e.preventDefault();
    if (!targetRole.trim()) return;
    setSaving(true);
    setError('');
    setSaved(false);
    try {
      const res = await prefsApi.upsertJob({ target_role: targetRole.trim(), target_seniority: targetSeniority.trim() || null });
      setTargetRole(res.data.target_role || '');
      setTargetSeniority(res.data.target_seniority || '');
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={handleSave} className="mb-6 surface-raised p-6">
      <h2 className="text-sm font-semibold text-foreground">Search Focus</h2>
      <p className="mt-1 text-xs text-muted-foreground">Controls what roles appear in "Hiring for" recommendations on Find Referrals.</p>
      <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div>
          <label htmlFor="search-target-role" className="mb-1 block text-sm font-medium text-secondary-foreground">Target role</label>
          <input
            id="search-target-role"
            type="text"
            value={targetRole}
            onChange={(e) => { setTargetRole(e.target.value); setSaved(false); }}
            className={inputClass}
            placeholder="e.g. Software Engineer"
            disabled={loading}
          />
        </div>
        <div>
          <label htmlFor="search-target-seniority" className="mb-1 block text-sm font-medium text-secondary-foreground">Seniority <span className="text-muted-foreground">(optional)</span></label>
          <input
            id="search-target-seniority"
            type="text"
            value={targetSeniority}
            onChange={(e) => { setTargetSeniority(e.target.value); setSaved(false); }}
            className={inputClass}
            placeholder="e.g. Senior, Staff, Lead"
            disabled={loading}
          />
        </div>
      </div>
      {error && <p className="mt-2 rounded-md bg-destructive/10 p-2 text-sm text-destructive" role="alert">{error}</p>}
      {saved && <p className="mt-2 rounded-md bg-success/10 p-2 text-sm text-success" role="status" aria-live="polite">Search focus saved!</p>}
      <button type="submit" disabled={saving || !targetRole.trim()} className="mt-3 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary/90 disabled:opacity-50">
        {saving ? 'Saving...' : 'Save'}
      </button>
    </form>
  );
}

function ProfileTab() {
  const [form, setForm] = useState({
    headline: '', current_company: '', current_title: '',
    industry: '', location: '', linkedin_url: '',
    github_url: '', portfolio_url: '', personal_site_url: '',
    bio_summary: '',
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
        github_url: p.github_url || '', portfolio_url: p.portfolio_url || '',
        personal_site_url: p.personal_site_url || '',
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
      github_url: prev.github_url,
      portfolio_url: prev.portfolio_url,
      personal_site_url: prev.personal_site_url,
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
      {/* Search Focus (target role for recommendations) */}
      <SearchFocusCard />

      {/* Import Profile Card */}
      <div className="mb-6 surface-raised p-6">
        <h2 className="text-sm font-semibold text-foreground">Import Profile</h2>
        <p className="mt-1 text-xs text-muted-foreground">Pre-fill your profile from a resume or LinkedIn.</p>
        <div className="mt-3 flex flex-col gap-3 sm:flex-row">
          <div>
            <input ref={resumeRef} type="file" accept=".pdf" onChange={handleResumeUpload} className="hidden" aria-label="Upload resume PDF" />
            <button type="button" onClick={() => resumeRef.current?.click()} disabled={importLoading === 'resume'} className="w-full sm:w-auto rounded-lg border border-primary px-4 py-2 text-sm font-medium text-primary hover:bg-primary/10 disabled:opacity-50">
              {importLoading === 'resume' ? 'Parsing...' : 'Import from Resume (PDF)'}
            </button>
          </div>
          <button type="button" onClick={handleLinkedInImport} disabled={importLoading === 'linkedin'} className="w-full sm:w-auto rounded-lg bg-info px-4 py-2 text-sm font-medium text-white hover:bg-info/90 cursor-pointer transition-colors duration-200 disabled:opacity-50">
            {importLoading === 'linkedin' ? 'Redirecting...' : 'Import from LinkedIn'}
          </button>
        </div>
      </div>

      <ResumePreviewModal data={resumePreview} onApply={applyResumeData} onClose={() => setResumePreview(null)} />

      <form onSubmit={handleSubmit} className="space-y-4 surface-raised p-6">
        <p className="text-sm text-muted-foreground">Your profile is used as context when AI drafts intro messages on your behalf.</p>

        <div>
          <label htmlFor="profile-headline" className="mb-1 block text-sm font-medium text-secondary-foreground">Headline</label>
          <input id="profile-headline" type="text" value={form.headline} onChange={set('headline')} className={inputClass} placeholder="B2B GTM Leader | Field Marketing..." />
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label htmlFor="profile-title" className="mb-1 block text-sm font-medium text-secondary-foreground">Title</label>
            <input id="profile-title" type="text" value={form.current_title} onChange={set('current_title')} className={inputClass} placeholder="Managing Director" />
          </div>
          <div>
            <label htmlFor="profile-company" className="mb-1 block text-sm font-medium text-secondary-foreground">Company</label>
            <input id="profile-company" type="text" value={form.current_company} onChange={set('current_company')} className={inputClass} placeholder="Acme Corp" />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label htmlFor="profile-industry" className="mb-1 block text-sm font-medium text-secondary-foreground">Industry</label>
            <input id="profile-industry" type="text" value={form.industry} onChange={set('industry')} className={inputClass} placeholder="Professional Services" />
          </div>
          <div>
            <label htmlFor="profile-location" className="mb-1 block text-sm font-medium text-secondary-foreground">Location</label>
            <input id="profile-location" type="text" value={form.location} onChange={set('location')} className={inputClass} placeholder="Singapore" />
          </div>
        </div>

        <div>
          <label htmlFor="profile-linkedin-url" className="mb-1 block text-sm font-medium text-secondary-foreground">LinkedIn URL</label>
          <input id="profile-linkedin-url" type="url" value={form.linkedin_url} onChange={set('linkedin_url')} className={inputClass} placeholder="https://linkedin.com/in/yourname" />
        </div>

        <div>
          <label htmlFor="profile-github-url" className="mb-1 block text-sm font-medium text-secondary-foreground">GitHub</label>
          <input id="profile-github-url" type="url" value={form.github_url} onChange={set('github_url')} className={inputClass} placeholder="https://github.com/yourname" />
        </div>

        <div>
          <label htmlFor="profile-portfolio-url" className="mb-1 block text-sm font-medium text-secondary-foreground">Portfolio</label>
          <input id="profile-portfolio-url" type="url" value={form.portfolio_url} onChange={set('portfolio_url')} className={inputClass} placeholder="https://yourportfolio.dev" />
        </div>

        <div>
          <label htmlFor="profile-personal-site-url" className="mb-1 block text-sm font-medium text-secondary-foreground">Personal site</label>
          <input id="profile-personal-site-url" type="url" value={form.personal_site_url} onChange={set('personal_site_url')} className={inputClass} placeholder="https://yoursite.com" />
        </div>

        <div>
          <label htmlFor="profile-bio" className="mb-1 block text-sm font-medium text-secondary-foreground">Bio summary</label>
          <textarea id="profile-bio" value={form.bio_summary} onChange={set('bio_summary')} rows={3} className={inputClass} placeholder="What you do and who you help..." />
        </div>

        {/* Work History */}
        <div className="border-t border-border pt-4">
          <div className="mb-3 flex items-center justify-between">
            <div>
              <h3 className="text-sm font-semibold text-foreground">Work History</h3>
              <p className="text-xs text-muted-foreground">Helps match you with contacts at your former companies.</p>
            </div>
            <button type="button" onClick={addWorkEntry} className="rounded-md border border-primary px-3 py-1 text-xs font-medium text-primary hover:bg-primary/10">Add another</button>
          </div>

          {workHistory.length === 0 && (
            <div className="rounded-lg border border-dashed border-border p-4 text-center">
              <p className="text-sm text-muted-foreground">No work history added yet.</p>
              <button type="button" onClick={addWorkEntry} className="mt-2 text-sm font-medium text-primary hover:text-primary">Add your first role</button>
            </div>
          )}

          <div className="space-y-3">
            {workHistory.map((entry, i) => (
              <div key={i} className="rounded-lg bg-muted/50 border border-border p-3">
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <div>
                    <label htmlFor={`work-company-${i}`} className="mb-1 block text-xs font-medium text-secondary-foreground">Company</label>
                    <input id={`work-company-${i}`} type="text" value={entry.company} onChange={(e) => updateWorkEntry(i, 'company', e.target.value)} className={inputClass} placeholder="Company name" />
                  </div>
                  <div>
                    <label htmlFor={`work-title-${i}`} className="mb-1 block text-xs font-medium text-secondary-foreground">Title / Role</label>
                    <input id={`work-title-${i}`} type="text" value={entry.title} onChange={(e) => updateWorkEntry(i, 'title', e.target.value)} className={inputClass} placeholder="e.g. Software Engineer" />
                  </div>
                </div>
                <div className="mt-2 grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <div>
                    <label htmlFor={`work-start-${i}`} className="mb-1 block text-xs font-medium text-secondary-foreground">Start date</label>
                    <input id={`work-start-${i}`} type="month" value={entry.start_date} onChange={(e) => updateWorkEntry(i, 'start_date', e.target.value)} className={inputClass} />
                  </div>
                  <div>
                    <label htmlFor={`work-end-${i}`} className="mb-1 block text-xs font-medium text-secondary-foreground">End date</label>
                    {entry.is_current ? (
                      <p className="py-2 text-sm text-muted-foreground">Present</p>
                    ) : (
                      <input id={`work-end-${i}`} type="month" value={entry.end_date} onChange={(e) => updateWorkEntry(i, 'end_date', e.target.value)} className={inputClass} />
                    )}
                  </div>
                </div>
                <div className="mt-2 flex items-center justify-between">
                  <label className="flex items-center gap-2 text-xs text-muted-foreground">
                    <input type="checkbox" checked={entry.is_current} onChange={(e) => updateWorkEntry(i, 'is_current', e.target.checked)} className="h-3.5 w-3.5 rounded border-border bg-muted text-primary focus:ring-ring" />
                    I currently work here
                  </label>
                  <button type="button" onClick={() => removeWorkEntry(i)} className="text-xs text-destructive hover:text-destructive/80 cursor-pointer transition-colors duration-200" aria-label={`Remove work history entry ${i + 1}`}>Remove</button>
                </div>
              </div>
            ))}
          </div>
        </div>

        {error && <p className="rounded-md bg-destructive/10 p-2 text-sm text-destructive" role="alert" aria-live="assertive">{error}</p>}
        {saved && <p className="rounded-md bg-success/10 p-2 text-sm text-success" role="status" aria-live="polite">Profile saved!</p>}
        {matchFeedback && <p className="rounded-md bg-info/10 p-2 text-sm text-info" role="status" aria-live="polite">{matchFeedback}</p>}

        <button type="submit" disabled={loading} className="w-full rounded-lg bg-primary py-2.5 text-sm font-medium text-white hover:bg-primary/90 disabled:opacity-50">
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
      {error && <div role="alert" aria-live="polite" className="rounded-lg bg-destructive/10 p-3 text-sm text-destructive">{error}</div>}

      {/* Data Export */}
      <section className="surface-raised p-5" aria-label="Data export">
        <h2 className="mb-1 text-base font-semibold text-foreground">Download My Data</h2>
        <p className="mb-3 text-sm text-muted-foreground">Export all your personal data as a JSON file.</p>
        <button onClick={handleExport} disabled={exporting} className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary/90 disabled:opacity-50">
          {exporting ? 'Preparing...' : exportDone ? 'Download Again' : 'Download My Data'}
        </button>
        {exportDone && <p className="mt-2 text-xs text-success" role="status">Download started.</p>}
      </section>

      {/* Processing Restriction */}
      <section className="surface-raised p-5" aria-label="Processing restriction">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-base font-semibold text-foreground">Restrict Processing</h2>
            <p className="text-sm text-muted-foreground">Limit how we process your data. Some features may be unavailable.</p>
          </div>
          <button onClick={handleToggleRestrict} disabled={togglingRestrict} role="switch" aria-checked={restricted} aria-label="Restrict data processing"
            className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full transition-colors duration-200 ${restricted ? 'bg-primary' : 'bg-muted-foreground'} disabled:opacity-50`}>
            <span className={`inline-block h-5 w-5 transform rounded-full bg-white shadow transition-transform duration-200 ${restricted ? 'translate-x-5' : 'translate-x-0.5'} mt-0.5`} />
          </button>
        </div>
      </section>

      {/* Marketing Preferences */}
      <section className="surface-raised p-5" aria-label="Marketing preferences">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-base font-semibold text-foreground">Marketing Communications</h2>
            <p className="text-sm text-muted-foreground">{marketingOptedOut ? 'You have opted out of marketing emails.' : 'Receive product updates and tips.'}</p>
          </div>
          <button onClick={handleToggleMarketing} disabled={togglingMarketing} role="switch" aria-checked={!marketingOptedOut} aria-label="Marketing communications"
            className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full transition-colors duration-200 ${!marketingOptedOut ? 'bg-primary' : 'bg-muted-foreground'} disabled:opacity-50`}>
            <span className={`inline-block h-5 w-5 transform rounded-full bg-white shadow transition-transform duration-200 ${!marketingOptedOut ? 'translate-x-5' : 'translate-x-0.5'} mt-0.5`} />
          </button>
        </div>
      </section>

      {/* Consent Records */}
      <section className="surface-raised p-5" aria-label="Consent records">
        <h2 className="mb-3 text-base font-semibold text-foreground">Consent Records</h2>
        {consentRecords.length === 0 ? (
          <p className="text-sm text-muted-foreground">No consent records on file.</p>
        ) : (
          <div className="space-y-2">
            {consentRecords.map((record, i) => (
              <div key={record.id || i} className="flex items-center justify-between rounded-lg border border-border p-3">
                <div>
                  <p className="text-sm font-medium text-foreground">{record.processing_activity || record.activity}</p>
                  <p className="text-xs text-muted-foreground">
                    {record.status || (record.consented ? 'Consented' : 'Withdrawn')}
                    {record.created_at && ` — ${new Date(record.created_at).toLocaleDateString()}`}
                  </p>
                </div>
                <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${record.consented || record.status === 'granted' ? 'bg-success/10 text-success' : 'bg-muted/50 text-muted-foreground'}`}>
                  {record.consented || record.status === 'granted' ? 'Active' : 'Withdrawn'}
                </span>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Formal Data Request */}
      <section className="surface-raised p-5" aria-label="Formal data request">
        <h2 className="mb-1 text-base font-semibold text-foreground">Formal Data Request</h2>
        <p className="mb-3 text-sm text-muted-foreground">Submit a formal data subject access request (DSAR).</p>
        <form onSubmit={handleDataRequest} className="space-y-3">
          <div>
            <label htmlFor="request-type" className="mb-1 block text-sm font-medium text-secondary-foreground">Request type</label>
            <select id="request-type" value={requestType} onChange={(e) => setRequestType(e.target.value)} className={inputClass}>
              {REQUEST_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
            </select>
          </div>
          <div>
            <label htmlFor="request-details" className="mb-1 block text-sm font-medium text-secondary-foreground">Details <span className="text-muted-foreground">(optional)</span></label>
            <textarea id="request-details" value={requestDetails} onChange={(e) => setRequestDetails(e.target.value)} placeholder="Any specific details..." rows={3} className={inputClass} />
          </div>
          <div>
            <label htmlFor="request-regulation" className="mb-1 block text-sm font-medium text-secondary-foreground">Regulation</label>
            <select id="request-regulation" value={requestRegulation} onChange={(e) => setRequestRegulation(e.target.value)} className={inputClass}>
              {REGULATION_OPTIONS.map((r) => <option key={r} value={r}>{r}</option>)}
            </select>
          </div>
          {requestSuccess && <p role="status" className="rounded-md bg-success/10 p-2 text-sm text-success">{requestSuccess}</p>}
          <button type="submit" disabled={submittingRequest} className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary/90 disabled:opacity-50">
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
  const [prefs, setPrefs] = useState<any>(null);
  const [contacts, setContacts] = useState([]);
  const [excludedIds, setExcludedIds] = useState([]);
  const [categoryFilters, setCategoryFilters] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState('');
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
    setSaving(true); setSaved(false); setError('');
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
    } catch (err) { setError(err.message || 'Failed to save settings'); }
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
      {error && <div role="alert" aria-live="assertive" className="rounded-lg bg-destructive/10 p-3 text-sm text-destructive">{error}</div>}

      {/* Privacy explainer */}
      <div className="rounded-lg border border-info/30 bg-info/10 p-4">
        <h3 className="mb-1 text-sm font-semibold text-info">How marketplace sharing works</h3>
        <p className="text-sm text-info">
          Candidates see <strong>role level and department only</strong> — never names or contact details.
          When someone requests an intro, you see their profile and choose whether to introduce them.
        </p>
      </div>

      {/* Share toggle */}
      <div className="surface-raised p-5">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-base font-semibold text-foreground">Share my network on the marketplace</h2>
            <p className="text-sm text-muted-foreground">
              {prefs?.opt_in_marketplace
                ? <>Your contacts are visible (anonymized) to candidates. Referral bonus ({SOURCES.REFERRAL_BONUS_RANGE.claim}) goes to you. <SourceTag source={SOURCES.REFERRAL_BONUS_RANGE.source} label={SOURCES.REFERRAL_BONUS_RANGE.label} /></>
                : <>Enable sharing to capture referral bonuses ({SOURCES.REFERRAL_BONUS_RANGE.claim} per hire) and earn credits. <SourceTag source={SOURCES.REFERRAL_BONUS_RANGE.source} label={SOURCES.REFERRAL_BONUS_RANGE.label} /></>}
            </p>
          </div>
          <button onClick={() => setPrefs({ ...prefs, opt_in_marketplace: !prefs.opt_in_marketplace })} role="switch" aria-checked={!!prefs?.opt_in_marketplace} aria-label="Share my network"
            className={`relative h-6 w-11 rounded-full transition ${prefs?.opt_in_marketplace ? 'bg-primary' : 'bg-muted-foreground'}`}>
            <span aria-hidden="true" className="absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition" style={{ left: prefs?.opt_in_marketplace ? '22px' : '2px' }} />
          </button>
        </div>
      </div>

      {/* Pause toggle */}
      <div className="surface-raised p-5">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-base font-semibold text-foreground">Temporarily hide all my listings</h2>
            <p className="text-sm text-muted-foreground">Pause sharing without losing your listings.</p>
          </div>
          <button onClick={() => setPrefs({ ...prefs, is_paused: !prefs.is_paused })} role="switch" aria-checked={!!prefs?.is_paused} aria-label="Temporarily hide listings"
            className={`relative h-6 w-11 rounded-full transition ${prefs?.is_paused ? 'bg-primary' : 'bg-muted-foreground'}`}>
            <span aria-hidden="true" className="absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition" style={{ left: prefs?.is_paused ? '22px' : '2px' }} />
          </button>
        </div>
      </div>

      {/* Category filters */}
      <div className="surface-raised p-5">
        <h2 className="mb-1 text-base font-semibold text-foreground">Department Filters</h2>
        <p className="mb-3 text-sm text-muted-foreground">Only share contacts in selected departments. Leave all unchecked to share all.</p>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          {DEPARTMENT_OPTIONS.map((dept) => (
            <label key={dept} className="flex items-center gap-2 rounded-lg border border-border p-2 text-sm hover:bg-muted">
              <input type="checkbox" checked={categoryFilters.includes(dept)} onChange={() => toggleDepartment(dept)} className="h-4 w-4 rounded border-border bg-muted text-primary focus:ring-ring" />
              <span className="text-secondary-foreground">{dept}</span>
            </label>
          ))}
        </div>
      </div>

      {/* Excluded contacts */}
      <div className="surface-raised p-5">
        <h2 className="mb-1 text-base font-semibold text-foreground">Excluded Contacts</h2>
        <p className="mb-3 text-sm text-muted-foreground">Search and select contacts to exclude from the marketplace.</p>
        <input type="text" value={searchTerm} onChange={(e) => setSearchTerm(e.target.value)} placeholder="Search by name, company, or title..." aria-label="Search contacts to exclude" className={'mb-3 ' + inputClass} />
        {filteredContacts.length > 0 && (
          <div className="mb-3 max-h-48 overflow-y-auto rounded-lg border border-border">
            {filteredContacts.slice(0, 20).map((c) => (
              <label key={c.id} className="flex items-center gap-2 border-b border-border px-3 py-2 text-sm last:border-0 hover:bg-muted">
                <input type="checkbox" checked={excludedIds.includes(c.id)} onChange={() => toggleExclude(c.id)} className="h-4 w-4 rounded border-border bg-muted text-destructive focus:ring-destructive" />
                <span className="text-foreground">{c.full_name}</span>
                {c.current_title && <span className="text-muted-foreground">— {c.current_title}</span>}
                {c.current_company && <span className="text-xs text-muted-foreground">at {c.current_company}</span>}
              </label>
            ))}
          </div>
        )}
        {excludedIds.length > 0 && <p className="text-xs text-muted-foreground">{excludedIds.length} contact{excludedIds.length !== 1 ? 's' : ''} excluded</p>}
      </div>

      {/* Save */}
      <div className="flex items-center gap-3">
        <button onClick={handleSave} disabled={saving} className="rounded-lg bg-primary px-6 py-2.5 text-sm font-medium text-white hover:bg-primary/90 disabled:opacity-50">
          {saving ? 'Saving...' : 'Save Settings'}
        </button>
        {saved && <span className="text-sm text-success" role="status" aria-live="polite">Settings saved!</span>}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Section: Password (within Account tab)
// ---------------------------------------------------------------------------

function PasswordSection({ clerkUser }) {
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  if (!clerkUser?.passwordEnabled) return null;

  const mismatch = confirmPassword && newPassword !== confirmPassword;
  const tooShort = newPassword && newPassword.length < 8;

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (mismatch || tooShort || !currentPassword || !newPassword) return;
    setSaving(true);
    setError('');
    setSuccess('');
    try {
      await clerkUser.updatePassword({ currentPassword, newPassword });
      setSuccess('Password updated.');
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
    } catch (err) {
      setError(err.errors?.[0]?.longMessage || err.message || 'Failed to update password.');
    } finally {
      setSaving(false);
    }
  };

  const inputClass = 'w-full rounded-lg border border-border bg-muted px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring';

  return (
    <section className="surface-raised p-5" aria-label="Password">
      <h2 className="mb-3 text-base font-semibold text-foreground">Password</h2>
      <form onSubmit={handleSubmit} className="space-y-3 max-w-sm">
        <div>
          <label htmlFor="current-pw" className="mb-1 block text-xs font-medium text-muted-foreground">Current password</label>
          <input id="current-pw" type="password" value={currentPassword} onChange={(e) => setCurrentPassword(e.target.value)}
            className={inputClass} autoComplete="current-password" />
        </div>
        <div>
          <label htmlFor="new-pw" className="mb-1 block text-xs font-medium text-muted-foreground">New password</label>
          <input id="new-pw" type="password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)}
            className={inputClass} autoComplete="new-password" />
          {tooShort && <p className="mt-1 text-xs text-primary">Must be at least 8 characters</p>}
        </div>
        <div>
          <label htmlFor="confirm-pw" className="mb-1 block text-xs font-medium text-muted-foreground">Confirm new password</label>
          <input id="confirm-pw" type="password" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)}
            className={inputClass} autoComplete="new-password" />
          {mismatch && <p className="mt-1 text-xs text-destructive">Passwords do not match</p>}
        </div>
        {error && <p className="rounded-md bg-destructive/10 p-2 text-sm text-destructive" role="alert">{error}</p>}
        {success && <p className="rounded-md bg-success/10 p-2 text-sm text-success" role="status">{success}</p>}
        <button type="submit" disabled={saving || mismatch || tooShort || !currentPassword || !newPassword || !confirmPassword}
          className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary/90 disabled:opacity-50">
          {saving ? 'Updating...' : 'Update Password'}
        </button>
      </form>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Section: Two-Factor Authentication (within Account tab)
// ---------------------------------------------------------------------------

function TwoFactorSection({ clerkUser }) {
  const [step, setStep] = useState('idle');
  const [totp, setTotp] = useState(null);
  const [code, setCode] = useState('');
  const [backupCodes, setBackupCodes] = useState(null);
  const [error, setError] = useState('');
  const [copied, setCopied] = useState(false);

  const startSetup = async () => {
    setError('');
    try {
      const resource = await clerkUser.createTOTP();
      setTotp(resource);
      setStep('qr');
    } catch (err) {
      setError(err.errors?.[0]?.longMessage || err.message || 'Failed to start 2FA setup.');
    }
  };

  const verifyCode = async () => {
    setError('');
    try {
      await clerkUser.verifyTOTP({ code });
      const backup = await clerkUser.createBackupCode();
      setBackupCodes(backup);
      setStep('backup');
    } catch (err) {
      setError(err.errors?.[0]?.longMessage || err.message || 'Invalid code. Try again.');
    }
  };

  const disable2FA = async () => {
    setError('');
    setStep('disabling');
    try {
      await clerkUser.disableTOTP();
      setStep('idle');
      setTotp(null);
      setCode('');
      setBackupCodes(null);
    } catch (err) {
      setError(err.errors?.[0]?.longMessage || err.message || 'Failed to disable 2FA.');
      setStep('idle');
    }
  };

  const copyBackupCodes = () => {
    if (backupCodes?.codes) {
      navigator.clipboard.writeText(backupCodes.codes.join('\n'));
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const isEnabled = clerkUser?.totpEnabled;

  return (
    <section className="surface-raised p-5" aria-label="Two-factor authentication">
      <div className="mb-3 flex items-center gap-3">
        <h2 className="text-base font-semibold text-foreground">Two-Factor Authentication</h2>
        {isEnabled ? (
          <span className="rounded-full bg-success/10 px-2 py-0.5 text-xs font-medium text-success">Enabled</span>
        ) : (
          <span className="rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">Not set up</span>
        )}
      </div>

      {error && <p className="mb-3 rounded-md bg-destructive/10 p-2 text-sm text-destructive" role="alert">{error}</p>}

      {step === 'idle' && !isEnabled && (
        <div>
          <p className="mb-3 text-sm text-muted-foreground">Add an extra layer of security with an authenticator app.</p>
          <button onClick={startSetup}
            className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary/90">
            Enable 2FA
          </button>
        </div>
      )}

      {step === 'idle' && isEnabled && (
        <div>
          <p className="mb-3 text-sm text-muted-foreground">Your account is protected with an authenticator app.</p>
          <button onClick={disable2FA}
            className="rounded-lg border border-destructive/30 px-4 py-2 text-sm font-medium text-destructive hover:bg-destructive/20 cursor-pointer transition-colors duration-200">
            Disable 2FA
          </button>
        </div>
      )}

      {step === 'disabling' && (
        <p className="text-sm text-muted-foreground">Disabling...</p>
      )}

      {step === 'qr' && totp && (
        <div className="space-y-4">
          <p className="text-sm text-muted-foreground">Scan this QR code with your authenticator app (Google Authenticator, Authy, 1Password, etc.):</p>
          <div className="inline-block rounded-lg bg-white p-3">
            <QRCodeSVG value={totp.uri || ''} size={180} />
          </div>
          <details className="text-xs text-muted-foreground">
            <summary className="cursor-pointer hover:text-muted-foreground">Can&apos;t scan? Use manual entry</summary>
            <code className="mt-1 block break-all rounded bg-muted p-2 text-secondary-foreground">{totp.uri}</code>
          </details>
          <button onClick={() => setStep('verify')}
            className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary/90">
            Next: Verify Code
          </button>
        </div>
      )}

      {step === 'verify' && (
        <div className="space-y-3 max-w-xs">
          <p className="text-sm text-muted-foreground">Enter the 6-digit code from your authenticator app:</p>
          <input type="text" inputMode="numeric" maxLength={6} value={code}
            onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
            className="w-full rounded-lg border border-border bg-muted px-3 py-2 text-center text-lg tracking-widest text-foreground focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring"
            placeholder="000000" autoFocus />
          <button onClick={verifyCode} disabled={code.length !== 6}
            className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary/90 disabled:opacity-50">
            Verify
          </button>
        </div>
      )}

      {step === 'backup' && backupCodes && (
        <div className="space-y-3">
          <p className="text-sm text-success font-medium">2FA enabled successfully!</p>
          <p className="text-sm text-muted-foreground">Save these backup codes somewhere safe. Each code can only be used once.</p>
          <div className="rounded-lg bg-muted p-3">
            <ul className="grid grid-cols-2 gap-1 text-sm font-mono text-secondary-foreground">
              {backupCodes.codes.map((c, i) => <li key={i}>{c}</li>)}
            </ul>
          </div>
          <div>
            <button onClick={copyBackupCodes}
              className="rounded-lg border border-border px-4 py-2 text-sm text-secondary-foreground hover:bg-muted">
              {copied ? 'Copied!' : 'Copy All'}
            </button>
            <button onClick={() => { setStep('idle'); setTotp(null); setCode(''); setBackupCodes(null); }}
              className="ml-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary/90">
              Done
            </button>
          </div>
        </div>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Section: Connected Accounts (within Account tab)
// ---------------------------------------------------------------------------

const OAUTH_PROVIDERS = [
  { strategy: 'oauth_google', label: 'Google', icon: 'G' },
  { strategy: 'oauth_linkedin_oidc', label: 'LinkedIn', icon: 'in' },
];

function ConnectedAccountsSection({ clerkUser }) {
  const [error, setError] = useState('');
  const [connecting, setConnecting] = useState(null);

  const connected = clerkUser?.externalAccounts || [];

  const normalizeProvider = (strategy) => strategy.replace('oauth_', '').replace('_oidc', '');

  const isConnected = (strategy) =>
    connected.some((a) => a.provider === normalizeProvider(strategy));

  const handleConnect = async (strategy) => {
    setError('');
    setConnecting(strategy);
    try {
      const res = await clerkUser.createExternalAccount({
        strategy,
        redirectUrl: window.location.origin + '/settings?tab=account',
      });
      if (res?.verification?.externalVerificationRedirectURL) {
        window.location.href = res.verification.externalVerificationRedirectURL.href;
      }
    } catch (err) {
      setError(err.errors?.[0]?.longMessage || err.message || 'Failed to connect account.');
      setConnecting(null);
    }
  };

  const handleDisconnect = async (account) => {
    setError('');
    try {
      await account.destroy();
    } catch (err) {
      setError(err.errors?.[0]?.longMessage || err.message || 'Failed to disconnect account.');
    }
  };

  return (
    <section className="surface-raised p-5" aria-label="Connected accounts">
      <h2 className="mb-3 text-base font-semibold text-foreground">Connected Accounts</h2>

      {error && <p className="mb-3 rounded-md bg-destructive/10 p-2 text-sm text-destructive" role="alert">{error}</p>}

      <div className="space-y-3">
        {connected.map((account) => (
          <div key={account.id} className="flex items-center justify-between rounded-lg border border-border bg-muted/50 px-4 py-3">
            <div className="flex items-center gap-3">
              <span className="flex h-8 w-8 items-center justify-center rounded-full bg-muted text-xs font-bold text-secondary-foreground">
                {account.provider === 'google' ? 'G' : account.provider === 'linkedin' || account.provider === 'linkedin_oidc' ? 'in' : account.provider.charAt(0).toUpperCase()}
              </span>
              <div>
                <p className="text-sm font-medium text-foreground capitalize">{account.provider.replace('_oidc', '')}</p>
                <p className="text-xs text-muted-foreground">{account.emailAddress || ''}</p>
              </div>
            </div>
            <button onClick={() => handleDisconnect(account)}
              className="rounded-lg border border-border px-3 py-1.5 text-xs text-muted-foreground hover:border-destructive/30 hover:text-destructive cursor-pointer transition-colors duration-200">
              Disconnect
            </button>
          </div>
        ))}

        {OAUTH_PROVIDERS.filter((p) => !isConnected(p.strategy)).map((provider) => (
          <div key={provider.strategy} className="flex items-center justify-between rounded-lg border border-dashed border-border px-4 py-3">
            <div className="flex items-center gap-3">
              <span className="flex h-8 w-8 items-center justify-center rounded-full bg-muted text-xs font-bold text-muted-foreground">
                {provider.icon}
              </span>
              <p className="text-sm text-muted-foreground">{provider.label}</p>
            </div>
            <button onClick={() => handleConnect(provider.strategy)}
              disabled={connecting === provider.strategy}
              className="rounded-lg border border-primary/30 px-3 py-1.5 text-xs font-medium text-primary hover:bg-primary/10 disabled:opacity-50">
              {connecting === provider.strategy ? 'Connecting...' : 'Connect'}
            </button>
          </div>
        ))}
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Tab: Account
// ---------------------------------------------------------------------------

function AccountTab() {
  const { user, logout } = useAuth();
  const { user: clerkUser } = useClerkUser();
  const navigate = useNavigate();

  // Delete account state
  const [showDelete, setShowDelete] = useState(false);
  const [deleteConfirmed, setDeleteConfirmed] = useState(false);
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [deleteError, setDeleteError] = useState('');

  const handleDeleteAccount = async () => {
    if (!deleteConfirmed) return;
    setDeleteLoading(true); setDeleteError('');
    try {
      await authApi.deleteAccount({ confirm_deletion: true });
      logout();
      navigate('/');
    } catch (err) {
      setDeleteError(err.message);
    } finally {
      setDeleteLoading(false);
    }
  };

  const primaryEmail = clerkUser?.primaryEmailAddress;

  return (
    <div className="space-y-6">
      {/* Account info — sourced from Clerk */}
      <section className="surface-raised p-5" aria-label="Account info">
        <h2 className="mb-3 text-base font-semibold text-foreground">Account Info</h2>
        <div className="flex items-start gap-4">
          {clerkUser?.imageUrl && (
            <img src={clerkUser.imageUrl} alt="" className="h-12 w-12 rounded-full border border-border" />
          )}
          <div className="space-y-2 text-sm">
            <div className="flex items-center gap-2">
              <span className="font-medium text-secondary-foreground">Name:</span>
              <span className="text-muted-foreground">{clerkUser?.fullName || '—'}</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="font-medium text-secondary-foreground">Email:</span>
              <span className="text-muted-foreground">{primaryEmail?.emailAddress || '—'}</span>
              {primaryEmail?.verification?.status === 'verified' ? (
                <span className="rounded-full bg-success/10 px-2 py-0.5 text-xs text-success">Verified</span>
              ) : (
                <span className="rounded-full bg-primary/10 px-2 py-0.5 text-xs text-primary">Unverified</span>
              )}
            </div>
            <div className="flex items-center gap-2">
              <span className="font-medium text-secondary-foreground">Intent:</span>
              <span className="text-muted-foreground capitalize">{user?.intent?.replace('_', ' ') || 'Not set'}</span>
            </div>
          </div>
        </div>
      </section>

      {/* Password — only if user has password auth enabled */}
      <PasswordSection clerkUser={clerkUser} />

      {/* Two-factor authentication */}
      <TwoFactorSection clerkUser={clerkUser} />

      {/* Connected accounts (Google, LinkedIn) */}
      <ConnectedAccountsSection clerkUser={clerkUser} />

      {/* Delete Account — Danger Zone */}
      <section className="rounded-xl border-2 border-destructive/30 bg-destructive/10 p-5" aria-label="Delete account">
        <h2 className="mb-1 text-base font-semibold text-destructive">Delete Account</h2>
        <p className="mb-2 text-sm text-muted-foreground">Permanently delete your account, contacts, search history, and all associated data. This action cannot be undone.</p>
        <ul className="mb-3 space-y-1 text-xs text-muted-foreground">
          <li>All data permanently deleted (contacts, searches, applications, messages)</li>
          <li>Credits forfeited with no refund</li>
          <li>Active subscriptions must be cancelled first</li>
        </ul>

        {!showDelete ? (
          <button onClick={() => { setShowDelete(true); setDeleteConfirmed(false); setDeleteError(''); }}
            className="rounded-lg border border-destructive/30 px-4 py-2 text-sm font-medium text-destructive hover:bg-destructive/20 cursor-pointer transition-colors duration-200">
            Delete My Account
          </button>
        ) : (
          <div className="space-y-3">
            <label className="flex items-start gap-2 text-sm text-secondary-foreground">
              <input type="checkbox" checked={deleteConfirmed} onChange={(e) => setDeleteConfirmed(e.target.checked)}
                className="mt-0.5 h-4 w-4 rounded border-border bg-muted text-destructive focus:ring-destructive" />
              I understand this action is permanent and my data cannot be recovered
            </label>
            {deleteError && <p className="rounded-md bg-destructive/10 p-2 text-sm text-destructive" role="alert">{deleteError}</p>}
            <div className="flex gap-2">
              <button onClick={handleDeleteAccount} disabled={!deleteConfirmed || deleteLoading}
                className="rounded-lg bg-destructive px-4 py-2 text-sm font-medium text-white hover:bg-destructive/90 cursor-pointer transition-colors duration-200 disabled:opacity-50">
                {deleteLoading ? 'Deleting...' : 'Permanently Delete'}
              </button>
              <button onClick={() => setShowDelete(false)}
                className="rounded-lg border border-border px-4 py-2 text-sm text-muted-foreground hover:bg-muted">Cancel</button>
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
  useDocumentTitle('Settings');
  const { user } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const activeTab = searchParams.get('tab') || 'profile';

  // All tabs visible to all users (action-based identity — no role gating)
  const visibleTabs = TABS;

  const switchTab = (key) => {
    setSearchParams({ tab: key }, { replace: true });
  };

  const renderTab = () => {
    switch (activeTab) {
      case 'profile': return <ProfileTab />;
      case 'privacy': return <PrivacyTab />;
      case 'sharing': return <SharingTab />;
      case 'account': return <AccountTab />;
      default: return <ProfileTab />;
    }
  };

  return (
    <div className="mx-auto max-w-4xl" role="main">
      <h1 className="page-title mb-6">Settings</h1>

      <div className="flex flex-col gap-6 sm:flex-row sm:gap-8">
        {/* Side tab nav */}
        <nav className="w-full sm:w-44 sm:shrink-0" aria-label="Settings tabs">
          <ul className="relative flex gap-1 overflow-x-auto scrollbar-none sm:flex-col sm:space-y-1 sm:gap-0" role="tablist">
            {visibleTabs.map((tab) => (
              <li key={tab.key}>
                <button
                  role="tab"
                  aria-selected={activeTab === tab.key}
                  aria-controls={`settings-panel-${tab.key}`}
                  onClick={() => switchTab(tab.key)}
                  className={`whitespace-nowrap rounded-lg px-3 py-2 text-left text-sm font-medium transition sm:w-full ${
                    activeTab === tab.key
                      ? 'bg-primary/10 text-primary'
                      : 'text-muted-foreground hover:bg-muted hover:text-foreground'
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
