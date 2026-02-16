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

  const inputClass = 'w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500';

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
      <div className="w-full max-w-md">
        <div className="mb-8 text-center">
          <h1 className="text-3xl font-bold text-slate-900">
            <span className="text-amber-500">~</span> WarmPath
          </h1>
        </div>

        {submitted ? (
          <div className="rounded-xl bg-white p-6 shadow-sm ring-1 ring-slate-200 text-center">
            <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-amber-100 text-amber-600 text-2xl">
              {'\u2709'}
            </div>
            <h2 className="text-lg font-semibold text-slate-900">Check your email</h2>
            <p className="mt-2 text-sm text-slate-500">
              If an account exists for <strong>{email}</strong>, we sent a password reset link.
              Check your inbox (and spam folder).
            </p>
            <Link
              to="/"
              className="mt-4 inline-block text-sm font-medium text-amber-600 hover:text-amber-700"
            >
              Back to login
            </Link>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4 rounded-xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
            <h2 className="text-lg font-semibold text-slate-900">Reset your password</h2>
            <p className="text-sm text-slate-500">
              Enter your email and we'll send you a link to reset your password.
            </p>

            <div>
              <label className="mb-1 block text-sm font-medium text-slate-700">Email</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className={inputClass}
                placeholder="you@company.com"
                required
              />
            </div>

            {error && <p className="rounded-md bg-red-50 p-2 text-sm text-red-600">{error}</p>}

            <button
              type="submit"
              disabled={loading}
              className="w-full rounded-lg bg-amber-500 py-2.5 text-sm font-medium text-white hover:bg-amber-600 disabled:opacity-50"
            >
              {loading ? 'Sending...' : 'Send Reset Link'}
            </button>

            <p className="text-center text-sm text-slate-500">
              <Link to="/" className="font-medium text-amber-600 hover:text-amber-700">
                Back to login
              </Link>
            </p>
          </form>
        )}
      </div>
    </div>
  );
}
