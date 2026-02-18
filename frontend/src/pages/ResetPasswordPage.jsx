import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { auth as authApi } from '../api/client';
import PasswordStrength from '../components/PasswordStrength';

export default function ResetPasswordPage() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (password !== confirm) {
      setError('Passwords do not match');
      return;
    }
    setLoading(true);
    setError('');
    try {
      await authApi.resetPassword({ token, new_password: password });
      setSuccess(true);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const inputClass = 'w-full rounded-lg border border-slate-700/50 bg-slate-800 text-slate-100 placeholder-slate-500 px-3 py-2 text-sm focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500';

  if (!token) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-950 px-4" role="main">
        <div className="w-full max-w-md text-center">
          <h1 className="text-3xl font-bold text-slate-50 mb-4">
            <span className="text-amber-500">~</span> WarmPath
          </h1>
          <div className="rounded-xl bg-slate-900 p-6 border border-slate-700/50" role="alert">
            <p className="text-slate-400">Invalid reset link. Missing token.</p>
            <Link to="/forgot-password" className="mt-4 inline-block text-sm font-medium text-amber-400 hover:text-amber-300">
              Request a new link
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-950 px-4" role="main">
      <div className="w-full max-w-md">
        <div className="mb-8 text-center">
          <h1 className="text-3xl font-bold text-slate-50">
            <span className="text-amber-500">~</span> WarmPath
          </h1>
        </div>

        {success ? (
          <div className="rounded-xl bg-slate-900 p-6 border border-slate-700/50 text-center" role="status" aria-live="polite">
            <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-emerald-500/10 text-emerald-400 text-2xl" aria-hidden="true">
              {'\u2713'}
            </div>
            <h2 className="text-lg font-semibold text-slate-50">Password Reset</h2>
            <p className="mt-2 text-sm text-slate-400">Your password has been updated. You can now log in.</p>
            <Link
              to="/"
              className="mt-4 inline-block rounded-lg bg-amber-500 px-6 py-2.5 text-sm font-medium text-white hover:bg-amber-400"
            >
              Go to Login
            </Link>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4 rounded-xl bg-slate-900 p-6 border border-slate-700/50">
            <h2 className="text-lg font-semibold text-slate-50">Set new password</h2>

            <div>
              <label htmlFor="reset-new-password" className="mb-1 block text-sm font-medium text-slate-300">New Password</label>
              <input
                id="reset-new-password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className={inputClass}
                placeholder="Enter new password"
                required
                aria-required="true"
              />
              <PasswordStrength password={password} />
            </div>

            <div>
              <label htmlFor="reset-confirm-password" className="mb-1 block text-sm font-medium text-slate-300">Confirm Password</label>
              <input
                id="reset-confirm-password"
                type="password"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                className={inputClass}
                placeholder="Confirm new password"
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
              {loading ? 'Resetting...' : 'Reset Password'}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
