import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { auth as authApi, contacts as contactsApi } from '../api/client';
import { useAuth } from '../context/AuthContext';
import useDocumentTitle from '../hooks/useDocumentTitle';

const EMPTY_ENTRY = { company: '', title: '', start_date: '', end_date: '', is_current: false };

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
          <button onClick={onClose} className="flex-1 rounded-lg border border-slate-700/50 py-2 text-sm font-medium text-slate-300 hover:bg-slate-800">
            Cancel
          </button>
          <button onClick={() => onApply(data)} className="flex-1 rounded-lg bg-amber-500 py-2 text-sm font-medium text-white hover:bg-amber-400">
            Apply to Profile
          </button>
        </div>
      </div>
    </div>
  );
}

export default function EditProfile() {
  useDocumentTitle('Edit Profile');
  const { user, logout } = useAuth();
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
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [deletePassword, setDeletePassword] = useState('');
  const [deleteConfirmed, setDeleteConfirmed] = useState(false);
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [deleteError, setDeleteError] = useState('');
  const navigate = useNavigate();

  // Check for LinkedIn profile data from OAuth flow
  useEffect(() => {
    const stored = sessionStorage.getItem('linkedin_profile');
    if (stored) {
      try {
        const li = JSON.parse(stored);
        setForm((prev) => ({
          ...prev,
          headline: prev.headline || li.name || '',
        }));
      } catch { /* ignore */ }
      sessionStorage.removeItem('linkedin_profile');
    }
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
      setWorkHistory((prev) => [
        ...prev,
        ...data.work_history.map((w) => ({
          company: w.company || '',
          title: w.title || '',
          start_date: w.start_date || '',
          end_date: w.end_date || '',
          is_current: !w.end_date,
        })),
      ]);
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

  useEffect(() => {
    authApi.upsertProfile({}).then((res) => {
      const p = res.data;
      setForm({
        headline: p.headline || '',
        current_company: p.current_company || '',
        current_title: p.current_title || '',
        industry: p.industry || '',
        location: p.location || '',
        linkedin_url: p.linkedin_url || '',
        bio_summary: p.bio_summary || '',
      });
      if (p.work_history?.length) {
        setWorkHistory(p.work_history.map((e) => ({
          company: e.company || '',
          title: e.title || '',
          start_date: e.start_date || '',
          end_date: e.end_date || '',
          is_current: !e.end_date,
        })));
      }
    }).catch(() => {});
  }, []);

  const set = (key) => (e) => {
    setForm({ ...form, [key]: e.target.value });
    setSaved(false);
  };

  const updateWorkEntry = (index, key, value) => {
    setWorkHistory((wh) => wh.map((entry, i) =>
      i === index ? { ...entry, [key]: value } : entry
    ));
    setSaved(false);
  };

  const addWorkEntry = () => {
    setWorkHistory((wh) => [...wh, { ...EMPTY_ENTRY }]);
    setSaved(false);
  };

  const removeWorkEntry = (index) => {
    setWorkHistory((wh) => wh.filter((_, i) => i !== index));
    setSaved(false);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    setMatchFeedback(null);
    try {
      const body = {
        ...form,
        work_history: workHistory
          .filter((e) => e.company.trim())
          .map((e) => ({
            company: e.company,
            title: e.title || undefined,
            start_date: e.start_date || undefined,
            end_date: e.is_current ? undefined : (e.end_date || undefined),
          })),
      };
      const res = await authApi.upsertProfile(body);
      setSaved(true);
      // Check if work history triggered score boosts
      if (res.data?.work_history?.length > 0) {
        try {
          const contactsRes = await contactsApi.list({ per_page: 1 });
          const total = contactsRes.meta?.total ?? 0;
          if (total > 0) {
            setMatchFeedback(
              `Work history saved! Contacts at your former companies now have boosted referral scores.`
            );
          }
        } catch { /* ignore */ }
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteAccount = async () => {
    setDeleteLoading(true);
    setDeleteError('');
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

  const inputClass = 'w-full rounded-lg border border-slate-700/50 bg-slate-800 text-slate-100 placeholder-slate-500 px-3 py-2 text-sm focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500';

  return (
    <div className="mx-auto max-w-2xl" role="main">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold text-slate-50">Edit Profile</h1>
        <button
          onClick={() => navigate('/coach')}
          className="text-sm text-amber-400 hover:text-amber-300"
        >
          &larr; Back to Coach
        </button>
      </div>

      {/* Import Profile Card */}
      <div className="mb-6 rounded-xl bg-slate-900 p-6 border border-slate-700/50">
        <h2 className="text-sm font-semibold text-slate-50">Import Profile</h2>
        <p className="mt-1 text-xs text-slate-400">Pre-fill your profile from a resume or LinkedIn.</p>
        <div className="mt-3 flex gap-3">
          <div>
            <input ref={resumeRef} type="file" accept=".pdf" onChange={handleResumeUpload} className="hidden" aria-label="Upload resume PDF" />
            <button
              type="button"
              onClick={() => resumeRef.current?.click()}
              disabled={importLoading === 'resume'}
              className="rounded-lg border border-amber-500 px-4 py-2 text-sm font-medium text-amber-400 hover:bg-amber-500/10 disabled:opacity-50"
            >
              {importLoading === 'resume' ? 'Parsing...' : 'Import from Resume (PDF)'}
            </button>
          </div>
          <button
            type="button"
            onClick={handleLinkedInImport}
            disabled={importLoading === 'linkedin'}
            className="rounded-lg px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
            style={{ backgroundColor: '#0A66C2' }}
          >
            {importLoading === 'linkedin' ? 'Redirecting...' : 'Import from LinkedIn'}
          </button>
        </div>
      </div>

      <ResumePreviewModal data={resumePreview} onApply={applyResumeData} onClose={() => setResumePreview(null)} />

      <form onSubmit={handleSubmit} className="space-y-4 rounded-xl bg-slate-900 p-6 border border-slate-700/50">
        <p className="text-sm text-slate-400">
          Your profile is used as context when AI drafts intro messages on your behalf.
        </p>

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
            <button
              type="button"
              onClick={addWorkEntry}
              className="rounded-md border border-amber-500 px-3 py-1 text-xs font-medium text-amber-400 hover:bg-amber-500/10"
            >
              Add another
            </button>
          </div>

          {workHistory.length === 0 && (
            <div className="rounded-lg border border-dashed border-slate-700/50 p-4 text-center">
              <p className="text-sm text-slate-400">No work history added yet.</p>
              <button type="button" onClick={addWorkEntry} className="mt-2 text-sm font-medium text-amber-400 hover:text-amber-300">
                Add your first role
              </button>
            </div>
          )}

          <div className="space-y-3">
            {workHistory.map((entry, i) => (
              <div key={i} className="rounded-lg bg-slate-800/50 border border-slate-700/50 p-3">
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label htmlFor={`work-company-${i}`} className="mb-1 block text-xs font-medium text-slate-300">Company</label>
                    <input
                      id={`work-company-${i}`}
                      type="text"
                      value={entry.company}
                      onChange={(e) => updateWorkEntry(i, 'company', e.target.value)}
                      className={inputClass}
                      placeholder="Company name"
                    />
                  </div>
                  <div>
                    <label htmlFor={`work-title-${i}`} className="mb-1 block text-xs font-medium text-slate-300">Title / Role</label>
                    <input
                      id={`work-title-${i}`}
                      type="text"
                      value={entry.title}
                      onChange={(e) => updateWorkEntry(i, 'title', e.target.value)}
                      className={inputClass}
                      placeholder="e.g. Software Engineer"
                    />
                  </div>
                </div>
                <div className="mt-2 grid grid-cols-2 gap-3">
                  <div>
                    <label htmlFor={`work-start-${i}`} className="mb-1 block text-xs font-medium text-slate-300">Start date</label>
                    <input
                      id={`work-start-${i}`}
                      type="month"
                      value={entry.start_date}
                      onChange={(e) => updateWorkEntry(i, 'start_date', e.target.value)}
                      className={inputClass}
                    />
                  </div>
                  <div>
                    <label htmlFor={`work-end-${i}`} className="mb-1 block text-xs font-medium text-slate-300">End date</label>
                    {entry.is_current ? (
                      <p className="py-2 text-sm text-slate-400">Present</p>
                    ) : (
                      <input
                        id={`work-end-${i}`}
                        type="month"
                        value={entry.end_date}
                        onChange={(e) => updateWorkEntry(i, 'end_date', e.target.value)}
                        className={inputClass}
                      />
                    )}
                  </div>
                </div>
                <div className="mt-2 flex items-center justify-between">
                  <label className="flex items-center gap-2 text-xs text-slate-400">
                    <input
                      type="checkbox"
                      checked={entry.is_current}
                      onChange={(e) => updateWorkEntry(i, 'is_current', e.target.checked)}
                      className="h-3.5 w-3.5 rounded border-slate-600 bg-slate-800 text-amber-500 focus:ring-amber-500"
                    />
                    I currently work here
                  </label>
                  <button
                    type="button"
                    onClick={() => removeWorkEntry(i)}
                    className="text-xs text-red-400 hover:text-red-300"
                    aria-label={`Remove work history entry ${i + 1}`}
                  >
                    Remove
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>

        {error && <p className="rounded-md bg-red-500/10 p-2 text-sm text-red-400" role="alert" aria-live="assertive">{error}</p>}
        {saved && <p className="rounded-md bg-emerald-500/10 p-2 text-sm text-emerald-400" role="status" aria-live="polite">Profile saved!</p>}
        {matchFeedback && <p className="rounded-md bg-blue-500/10 p-2 text-sm text-blue-400" role="status" aria-live="polite">{matchFeedback}</p>}

        <button
          type="submit"
          disabled={loading}
          className="w-full rounded-lg bg-amber-500 py-2.5 text-sm font-medium text-white hover:bg-amber-400 disabled:opacity-50"
        >
          {loading ? 'Saving...' : 'Save Profile'}
        </button>
      </form>

      {/* Danger Zone */}
      <div className="mt-8 rounded-xl border-2 border-red-500/30 bg-red-500/10 p-6">
        <h2 className="text-lg font-bold text-red-400">Danger Zone</h2>
        <p className="mt-1 text-sm text-slate-400">
          Permanently delete your account and all associated data. This action cannot be undone.
        </p>
        <ul className="mt-3 space-y-1 text-xs text-slate-400">
          <li>All data permanently deleted (contacts, searches, applications, messages)</li>
          <li>Credits forfeited with no refund</li>
          <li>Re-registration will not include welcome bonus credits</li>
          <li>Active subscriptions must be cancelled first</li>
        </ul>
        <button
          type="button"
          onClick={() => { setShowDeleteModal(true); setDeletePassword(''); setDeleteConfirmed(false); setDeleteError(''); }}
          className="mt-4 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-2 text-sm font-medium text-red-400 hover:bg-red-500/20"
        >
          Delete my account
        </button>
      </div>

      {/* Delete Confirmation Modal */}
      {showDeleteModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" role="dialog" aria-modal="true" aria-labelledby="delete-modal-title">
          <div className="mx-4 w-full max-w-md rounded-xl bg-slate-900 p-6 shadow-xl border border-slate-700/50">
            <h3 id="delete-modal-title" className="text-lg font-bold text-red-400">Delete Account</h3>
            <p className="mt-2 text-sm text-slate-400">
              This will permanently delete your account, all contacts, search history, applications,
              and credits. This cannot be undone.
            </p>

            <label className="mt-4 flex items-start gap-2 text-sm text-slate-300">
              <input
                type="checkbox"
                checked={deleteConfirmed}
                onChange={(e) => setDeleteConfirmed(e.target.checked)}
                className="mt-0.5 h-4 w-4 rounded border-slate-600 bg-slate-800 text-red-500 focus:ring-red-500"
              />
              I understand this action is permanent and my data cannot be recovered
            </label>

            <div className="mt-4">
              <label htmlFor="delete-confirm-password" className="mb-1 block text-sm font-medium text-slate-300">
                Enter your password to confirm
              </label>
              <input
                id="delete-confirm-password"
                type="password"
                value={deletePassword}
                onChange={(e) => setDeletePassword(e.target.value)}
                className={inputClass}
                placeholder="Your current password"
                aria-required="true"
              />
            </div>

            {deleteError && (
              <p className="mt-3 rounded-md bg-red-500/10 p-2 text-sm text-red-400" role="alert" aria-live="assertive">{deleteError}</p>
            )}

            <div className="mt-5 flex gap-3">
              <button
                type="button"
                onClick={() => setShowDeleteModal(false)}
                className="flex-1 rounded-lg border border-slate-700/50 py-2 text-sm font-medium text-slate-300 hover:bg-slate-800"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleDeleteAccount}
                disabled={!deleteConfirmed || !deletePassword || deleteLoading}
                className="flex-1 rounded-lg bg-red-600 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
              >
                {deleteLoading ? 'Deleting...' : 'Delete Account'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
