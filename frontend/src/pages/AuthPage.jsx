import { useState } from 'react';
import { useAuth } from '../context/AuthContext';

export default function AuthPage() {
  const { login, signup } = useAuth();
  const [isSignup, setIsSignup] = useState(false);
  const [form, setForm] = useState({
    email: '', password: '', full_name: '',
    headline: '', current_company: '', current_title: '',
    industry: '', location: '', linkedin_url: '', bio_summary: '',
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const set = (key) => (e) => setForm({ ...form, [key]: e.target.value });

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      if (isSignup) {
        const body = { email: form.email, password: form.password, full_name: form.full_name };
        // Include optional profile fields if filled
        ['headline', 'current_company', 'current_title', 'industry', 'location', 'linkedin_url', 'bio_summary']
          .forEach((k) => { if (form[k]) body[k] = form[k]; });
        await signup(body);
      } else {
        await login({ email: form.email, password: form.password });
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const inputClass = 'w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500';

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
      <div className="w-full max-w-md">
        <div className="mb-8 text-center">
          <h1 className="text-3xl font-bold text-slate-900">
            <span className="text-amber-500">~</span> WarmPath
          </h1>
          <p className="mt-2 text-sm text-slate-500">
            Turn your network into your pipeline
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4 rounded-xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
          <div className="flex rounded-lg bg-slate-100 p-1">
            <button
              type="button"
              onClick={() => { setIsSignup(false); setError(''); }}
              className={`flex-1 rounded-md py-2 text-sm font-medium transition ${
                !isSignup ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-700'
              }`}
            >
              Log in
            </button>
            <button
              type="button"
              onClick={() => { setIsSignup(true); setError(''); }}
              className={`flex-1 rounded-md py-2 text-sm font-medium transition ${
                isSignup ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-700'
              }`}
            >
              Sign up
            </button>
          </div>

          {isSignup && (
            <div>
              <label className="mb-1 block text-sm font-medium text-slate-700">Full Name</label>
              <input type="text" value={form.full_name} onChange={set('full_name')} className={inputClass} placeholder="Jane Smith" required />
            </div>
          )}

          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">Email</label>
            <input type="email" value={form.email} onChange={set('email')} className={inputClass} placeholder="you@company.com" required />
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">Password</label>
            <input type="password" value={form.password} onChange={set('password')} className={inputClass} placeholder="••••••••" required />
          </div>

          {isSignup && (
            <>
              <hr className="border-slate-200" />
              <p className="text-xs text-slate-400">Optional — helps AI draft better intros</p>

              <div>
                <label className="mb-1 block text-sm font-medium text-slate-700">Headline</label>
                <input type="text" value={form.headline} onChange={set('headline')} className={inputClass} placeholder="B2B GTM Leader | Field Marketing..." />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="mb-1 block text-sm font-medium text-slate-700">Title</label>
                  <input type="text" value={form.current_title} onChange={set('current_title')} className={inputClass} placeholder="Managing Director" />
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium text-slate-700">Company</label>
                  <input type="text" value={form.current_company} onChange={set('current_company')} className={inputClass} placeholder="Acme Corp" />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
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
                <label className="mb-1 block text-sm font-medium text-slate-700">Bio</label>
                <textarea value={form.bio_summary} onChange={set('bio_summary')} rows={2} className={inputClass} placeholder="What you do and who you help..." />
              </div>
            </>
          )}

          {error && <p className="rounded-md bg-red-50 p-2 text-sm text-red-600">{error}</p>}

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-lg bg-amber-500 py-2.5 text-sm font-medium text-white hover:bg-amber-600 disabled:opacity-50"
          >
            {loading ? 'Please wait...' : isSignup ? 'Create Account' : 'Log In'}
          </button>
        </form>
      </div>
    </div>
  );
}
