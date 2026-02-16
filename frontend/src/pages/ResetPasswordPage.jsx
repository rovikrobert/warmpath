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

  const inputClass = 'w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500';

  if (!token) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
        <div className="w-full max-w-md text-center">
          <h1 className="text-3xl font-bold text-slate-900 mb-4">
            <span className="text-amber-500">~</span> WarmPath
          </h1>
          <div className="rounded-xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
            <p className="text-slate-600">Invalid reset link. Missing token.</p>
            <Link to="/forgot-password" className="mt-4 inline-block text-sm font-medium text-amber-600 hover:text-amber-700">
              Request a new link
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
      <div className="w-full max-w-md">
        <div className="mb-8 text-center">
          <h1 className="text-3xl font-bold text-slate-900">
            <span className="text-amber-500">~</span> WarmPath
          </h1>
        </div>

        {success ? (
          <div className="rounded-xl bg-white p-6 shadow-sm ring-1 ring-slate-200 text-center">
            <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-green-100 text-green-600 text-2xl">
              {'\u2713'}
            </div>
            <h2 className="text-lg font-semibold text-slate-900">Password Reset</h2>
            <p className="mt-2 text-sm text-slate-500">Your password has been updated. You can now log in.</p>
            <Link
              to="/"
              className="mt-4 inline-block rounded-lg bg-amber-500 px-6 py-2.5 text-sm font-medium text-white hover:bg-amber-600"
            >
              Go to Login
            </Link>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4 rounded-xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
            <h2 className="text-lg font-semibold text-slate-900">Set new password</h2>

            <div>
              <label className="mb-1 block text-sm font-medium text-slate-700">New Password</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className={inputClass}
                placeholder="Enter new password"
                required
              />
              <PasswordStrength password={password} />
            </div>

            <div>
              <label className="mb-1 block text-sm font-medium text-slate-700">Confirm Password</label>
              <input
                type="password"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                className={inputClass}
                placeholder="Confirm new password"
                required
              />
            </div>

            {error && <p className="rounded-md bg-red-50 p-2 text-sm text-red-600">{error}</p>}

            <button
              type="submit"
              disabled={loading}
              className="w-full rounded-lg bg-amber-500 py-2.5 text-sm font-medium text-white hover:bg-amber-600 disabled:opacity-50"
            >
              {loading ? 'Resetting...' : 'Reset Password'}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
