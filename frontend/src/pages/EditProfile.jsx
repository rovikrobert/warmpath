import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { auth as authApi, contacts as contactsApi } from '../api/client';
import { useAuth } from '../context/AuthContext';

const EMPTY_ENTRY = { company: '', title: '', start_date: '', end_date: '', is_current: false };

function ResumePreviewModal({ data, onApply, onClose }) {
  if (!data) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="mx-4 w-full max-w-lg max-h-[80vh] overflow-y-auto rounded-xl bg-white p-6 shadow-xl">
        <h3 className="text-lg font-bold text-slate-900">Resume Preview</h3>
        <p className="mt-1 text-sm text-slate-500">Review parsed data before applying to your profile.</p>
        <div className="mt-4 space-y-3 text-sm">
          {data.headline && <div><span className="font-medium text-slate-700">Headline:</span> {data.headline}</div>}
          {data.current_title && <div><span className="font-medium text-slate-700">Title:</span> {data.current_title}</div>}
          {data.current_company && <div><span className="font-medium text-slate-700">Company:</span> {data.current_company}</div>}
          {data.industry && <div><span className="font-medium text-slate-700">Industry:</span> {data.industry}</div>}
          {data.location && <div><span className="font-medium text-slate-700">Location:</span> {data.location}</div>}
          {data.bio_summary && <div><span className="font-medium text-slate-700">Summary:</span> {data.bio_summary}</div>}
          {data.work_history?.length > 0 && (
            <div>
              <span className="font-medium text-slate-700">Work History:</span>
              <ul className="mt-1 space-y-1 pl-4">
                {data.work_history.map((w, i) => (
                  <li key={i} className="text-slate-600">
                    {w.title} at {w.company} ({w.start_date || '?'} - {w.end_date || 'Present'})
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
        <div className="mt-5 flex gap-3">
          <button onClick={onClose} className="flex-1 rounded-lg border border-slate-300 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50">
            Cancel
          </button>
          <button onClick={() => onApply(data)} className="flex-1 rounded-lg bg-amber-500 py-2 text-sm font-medium text-white hover:bg-amber-600">
            Apply to Profile
          </button>
        </div>
      </div>
    </div>
  );
}

export default function EditProfile() {
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

  const inputClass = 'w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500';

  return (
    <div className="mx-auto max-w-2xl">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold text-slate-900">Edit Profile</h1>
        <button
          onClick={() => navigate('/dashboard')}
          className="text-sm text-amber-600 hover:text-amber-700"
        >
          &larr; Back to Dashboard
        </button>
      </div>

      {/* Import Profile Card */}
      <div className="mb-6 rounded-xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
        <h2 className="text-sm font-semibold text-slate-900">Import Profile</h2>
        <p className="mt-1 text-xs text-slate-500">Pre-fill your profile from a resume or LinkedIn.</p>
        <div className="mt-3 flex gap-3">
          <div>
            <input ref={resumeRef} type="file" accept=".pdf" onChange={handleResumeUpload} className="hidden" />
            <button
              type="button"
              onClick={() => resumeRef.current?.click()}
              disabled={importLoading === 'resume'}
              className="rounded-lg border border-amber-500 px-4 py-2 text-sm font-medium text-amber-600 hover:bg-amber-50 disabled:opacity-50"
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

      <form onSubmit={handleSubmit} className="space-y-4 rounded-xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
        <p className="text-sm text-slate-500">
          Your profile is used as context when AI drafts intro messages on your behalf.
        </p>

        <div>
          <label className="mb-1 block text-sm font-medium text-slate-700">Headline</label>
          <input type="text" value={form.headline} onChange={set('headline')} className={inputClass} placeholder="B2B GTM Leader | Field Marketing..." />
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">Title</label>
            <input type="text" value={form.current_title} onChange={set('current_title')} className={inputClass} placeholder="Managing Director" />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">Company</label>
            <input type="text" value={form.current_company} onChange={set('current_company')} className={inputClass} placeholder="Acme Corp" />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">Industry</label>
            <input type="text" value={form.industry} onChange={set('industry')} className={inputClass} placeholder="Professional Services" />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">Location</label>
            <input type="text" value={form.location} onChange={set('location')} className={inputClass} placeholder="Singapore" />
          </div>
        </div>

        <div>
          <label className="mb-1 block text-sm font-medium text-slate-700">LinkedIn URL</label>
          <input type="url" value={form.linkedin_url} onChange={set('linkedin_url')} className={inputClass} placeholder="https://linkedin.com/in/yourname" />
        </div>

        <div>
          <label className="mb-1 block text-sm font-medium text-slate-700">Bio summary</label>
          <textarea value={form.bio_summary} onChange={set('bio_summary')} rows={3} className={inputClass} placeholder="What you do and who you help..." />
        </div>

        {/* Work History */}
        <div className="border-t border-slate-200 pt-4">
          <div className="mb-3 flex items-center justify-between">
            <div>
              <h3 className="text-sm font-semibold text-slate-900">Work History</h3>
              <p className="text-xs text-slate-500">Helps match you with contacts at your former companies.</p>
            </div>
            <button
              type="button"
              onClick={addWorkEntry}
              className="rounded-md border border-amber-500 px-3 py-1 text-xs font-medium text-amber-600 hover:bg-amber-50"
            >
              Add another
            </button>
          </div>

          {workHistory.length === 0 && (
            <div className="rounded-lg border border-dashed border-slate-300 p-4 text-center">
              <p className="text-sm text-slate-500">No work history added yet.</p>
              <button type="button" onClick={addWorkEntry} className="mt-2 text-sm font-medium text-amber-600 hover:text-amber-700">
                Add your first role
              </button>
            </div>
          )}

          <div className="space-y-3">
            {workHistory.map((entry, i) => (
              <div key={i} className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="mb-1 block text-xs font-medium text-slate-700">Company</label>
                    <input
                      type="text"
                      value={entry.company}
                      onChange={(e) => updateWorkEntry(i, 'company', e.target.value)}
                      className={inputClass}
                      placeholder="Company name"
                    />
                  </div>
                  <div>
                    <label className="mb-1 block text-xs font-medium text-slate-700">Title / Role</label>
                    <input
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
                    <label className="mb-1 block text-xs font-medium text-slate-700">Start date</label>
                    <input
                      type="month"
                      value={entry.start_date}
                      onChange={(e) => updateWorkEntry(i, 'start_date', e.target.value)}
                      className={inputClass}
                    />
                  </div>
                  <div>
                    <label className="mb-1 block text-xs font-medium text-slate-700">End date</label>
                    {entry.is_current ? (
                      <p className="py-2 text-sm text-slate-500">Present</p>
                    ) : (
                      <input
                        type="month"
                        value={entry.end_date}
                        onChange={(e) => updateWorkEntry(i, 'end_date', e.target.value)}
                        className={inputClass}
                      />
                    )}
                  </div>
                </div>
                <div className="mt-2 flex items-center justify-between">
                  <label className="flex items-center gap-2 text-xs text-slate-600">
                    <input
                      type="checkbox"
                      checked={entry.is_current}
                      onChange={(e) => updateWorkEntry(i, 'is_current', e.target.checked)}
                      className="h-3.5 w-3.5 rounded border-slate-300 text-amber-500 focus:ring-amber-500"
                    />
                    I currently work here
                  </label>
                  <button
                    type="button"
                    onClick={() => removeWorkEntry(i)}
                    className="text-xs text-red-500 hover:text-red-600"
                  >
                    Remove
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>

        {error && <p className="rounded-md bg-red-50 p-2 text-sm text-red-600">{error}</p>}
        {saved && <p className="rounded-md bg-green-50 p-2 text-sm text-green-600">Profile saved!</p>}
        {matchFeedback && <p className="rounded-md bg-blue-50 p-2 text-sm text-blue-700">{matchFeedback}</p>}

        <button
          type="submit"
          disabled={loading}
          className="w-full rounded-lg bg-amber-500 py-2.5 text-sm font-medium text-white hover:bg-amber-600 disabled:opacity-50"
        >
          {loading ? 'Saving...' : 'Save Profile'}
        </button>
      </form>

      {/* Danger Zone */}
      <div className="mt-8 rounded-xl border-2 border-red-200 bg-white p-6 shadow-sm">
        <h2 className="text-lg font-bold text-red-700">Danger Zone</h2>
        <p className="mt-1 text-sm text-slate-600">
          Permanently delete your account and all associated data. This action cannot be undone.
        </p>
        <ul className="mt-3 space-y-1 text-xs text-slate-500">
          <li>All data permanently deleted (contacts, searches, applications, messages)</li>
          <li>Credits forfeited with no refund</li>
          <li>Re-registration will not include welcome bonus credits</li>
          <li>Active subscriptions must be cancelled first</li>
        </ul>
        <button
          type="button"
          onClick={() => { setShowDeleteModal(true); setDeletePassword(''); setDeleteConfirmed(false); setDeleteError(''); }}
          className="mt-4 rounded-lg border border-red-300 bg-red-50 px-4 py-2 text-sm font-medium text-red-700 hover:bg-red-100"
        >
          Delete my account
        </button>
      </div>

      {/* Delete Confirmation Modal */}
      {showDeleteModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="mx-4 w-full max-w-md rounded-xl bg-white p-6 shadow-xl">
            <h3 className="text-lg font-bold text-red-700">Delete Account</h3>
            <p className="mt-2 text-sm text-slate-600">
              This will permanently delete your account, all contacts, search history, applications,
              and credits. This cannot be undone.
            </p>

            <label className="mt-4 flex items-start gap-2 text-sm text-slate-700">
              <input
                type="checkbox"
                checked={deleteConfirmed}
                onChange={(e) => setDeleteConfirmed(e.target.checked)}
                className="mt-0.5 h-4 w-4 rounded border-slate-300 text-red-500 focus:ring-red-500"
              />
              I understand this action is permanent and my data cannot be recovered
            </label>

            <div className="mt-4">
              <label className="mb-1 block text-sm font-medium text-slate-700">
                Enter your password to confirm
              </label>
              <input
                type="password"
                value={deletePassword}
                onChange={(e) => setDeletePassword(e.target.value)}
                className={inputClass}
                placeholder="Your current password"
              />
            </div>

            {deleteError && (
              <p className="mt-3 rounded-md bg-red-50 p-2 text-sm text-red-600">{deleteError}</p>
            )}

            <div className="mt-5 flex gap-3">
              <button
                type="button"
                onClick={() => setShowDeleteModal(false)}
                className="flex-1 rounded-lg border border-slate-300 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
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
