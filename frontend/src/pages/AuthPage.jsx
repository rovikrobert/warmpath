import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { auth as authApi } from '../api/client';
import { useAuth } from '../context/AuthContext';
import PasswordStrength from '../components/PasswordStrength';

export default function AuthPage() {
  const { login, signup } = useAuth();
  const navigate = useNavigate();
  const [isSignup, setIsSignup] = useState(false);
  const [form, setForm] = useState({ email: '', password: '', full_name: '' });
  const [loading, setLoading] = useState(false);
  const [linkedinLoading, setLinkedinLoading] = useState(false);
  const [error, setError] = useState('');

  const set = (key) => (e) => setForm({ ...form, [key]: e.target.value });

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      if (isSignup) {
        await signup({ email: form.email, password: form.password, full_name: form.full_name });
        navigate('/onboarding');
      } else {
        await login({ email: form.email, password: form.password });
        navigate('/dashboard');
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleLinkedIn = async () => {
    setLinkedinLoading(true);
    setError('');
    try {
      const res = await authApi.linkedinAuthorize();
      window.location.href = res.data.url;
    } catch (err) {
      setError(err.message);
      setLinkedinLoading(false);
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
          <p className="mt-2 text-lg font-medium text-slate-700">
            Get referred to your dream job
          </p>
          <p className="mt-1 text-sm text-slate-500">
            Employee referrals convert at 40% vs 1% for cold applications.
            Stop applying into the black hole.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4 rounded-xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
          <button
            type="button"
            onClick={handleLinkedIn}
            disabled={linkedinLoading}
            className="flex w-full items-center justify-center gap-2 rounded-lg py-2.5 text-sm font-medium text-white disabled:opacity-50"
            style={{ backgroundColor: '#0A66C2' }}
          >
            <svg className="h-5 w-5" viewBox="0 0 24 24" fill="currentColor">
              <path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433a2.062 2.062 0 01-2.063-2.065 2.064 2.064 0 112.063 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z" />
            </svg>
            {linkedinLoading ? 'Redirecting...' : 'Continue with LinkedIn'}
          </button>

          <div className="relative">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-slate-200" />
            </div>
            <div className="relative flex justify-center text-xs">
              <span className="bg-white px-2 text-slate-400">or</span>
            </div>
          </div>

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
            {isSignup && <PasswordStrength password={form.password} />}
            {!isSignup && (
              <div className="mt-1 text-right">
                <Link to="/forgot-password" className="text-xs text-amber-600 hover:text-amber-700">Forgot password?</Link>
              </div>
            )}
          </div>

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
