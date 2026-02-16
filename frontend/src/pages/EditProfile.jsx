import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { auth as authApi } from '../api/client';
import { useAuth } from '../context/AuthContext';

export default function EditProfile() {
  const { user } = useAuth();
  const [form, setForm] = useState({
    headline: '', current_company: '', current_title: '',
    industry: '', location: '', linkedin_url: '', bio_summary: '',
  });
  const [loading, setLoading] = useState(false);
  const [saved, setSaved] = useState(false);
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
    }).catch(() => {});
  }, []);

  const set = (key) => (e) => {
    setForm({ ...form, [key]: e.target.value });
    setSaved(false);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      await authApi.upsertProfile(form);
      setSaved(true);
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

        {error && <p className="rounded-md bg-red-50 p-2 text-sm text-red-600">{error}</p>}
        {saved && <p className="rounded-md bg-green-50 p-2 text-sm text-green-600">Profile saved!</p>}

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
