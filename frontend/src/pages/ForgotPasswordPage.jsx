import { useState } from 'react';
import { Link } from 'react-router-dom';
import { auth as authApi } from '../api/client';

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState('');
  const [submitted, setSubmitted] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      await authApi.forgotPassword({ email });
      setSubmitted(true);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const inputClass = 'w-full rounded-lg border border-slate-700/50 bg-slate-800 text-slate-100 placeholder-slate-500 px-3 py-2 text-sm focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500';

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-950 px-4" role="main">
      <div className="w-full max-w-md">
        <div className="mb-8 text-center">
          <h1 className="text-3xl font-bold text-slate-50">
            <span className="text-amber-500">~</span> WarmPath
          </h1>
        </div>

        {submitted ? (
          <div className="rounded-xl bg-slate-900 p-6 border border-slate-700/50 text-center" role="status" aria-live="polite">
            <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-amber-500/10 text-amber-400 text-2xl" aria-hidden="true">
              {'\u2709'}
            </div>
            <h2 className="text-lg font-semibold text-slate-50">Check your email</h2>
            <p className="mt-2 text-sm text-slate-400">
              If an account exists for <strong>{email}</strong>, we sent a password reset link.
              Check your inbox (and spam folder).
            </p>
            <Link
              to="/"
              className="mt-4 inline-block text-sm font-medium text-amber-400 hover:text-amber-300"
            >
              Back to login
            </Link>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4 rounded-xl bg-slate-900 p-6 border border-slate-700/50">
            <h2 className="text-lg font-semibold text-slate-50">Reset your password</h2>
            <p className="text-sm text-slate-400">
              Enter your email and we'll send you a link to reset your password.
            </p>

            <div>
              <label htmlFor="forgot-email" className="mb-1 block text-sm font-medium text-slate-300">Email</label>
              <input
                id="forgot-email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className={inputClass}
                placeholder="you@company.com"
                required
                aria-required="true"
              />
            </div>

            {error && <p className="rounded-md bg-red-500/10 p-2 text-sm text-red-400" role="alert" aria-live="assertive">{error}</p>}

            <button
              type="submit"
              disabled={loading}
              className="w-full rounded-lg bg-amber-500 py-2.5 text-sm font-medium text-white hover:bg-amber-400 disabled:opacity-50"
            >
              {loading ? 'Sending...' : 'Send Reset Link'}
            </button>

            <p className="text-center text-sm text-slate-400">
              <Link to="/" className="font-medium text-amber-400 hover:text-amber-300">
                Back to login
              </Link>
            </p>
          </form>
        )}
      </div>
    </div>
  );
}
