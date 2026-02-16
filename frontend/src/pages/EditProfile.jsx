import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { auth as authApi, contacts as contactsApi } from '../api/client';
import { useAuth } from '../context/AuthContext';

const EMPTY_ENTRY = { company: '', title: '', start_date: '', end_date: '', is_current: false };

export default function EditProfile() {
  const { user } = useAuth();
  const [form, setForm] = useState({
    headline: '', current_company: '', current_title: '',
    industry: '', location: '', linkedin_url: '', bio_summary: '',
  });
  const [workHistory, setWorkHistory] = useState([]);
  const [loading, setLoading] = useState(false);
  const [saved, setSaved] = useState(false);
  const [matchFeedback, setMatchFeedback] = useState(null);
  const [error, setError] = useState('');
  const navigate = useNavigate();

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
    </div>
  );
}
