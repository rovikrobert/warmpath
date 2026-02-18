import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { api } from '../api/client';
import Spinner from '../components/ui/Spinner';

export default function VerifyEmailPage() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token');
  const [status, setStatus] = useState('loading');
  const [message, setMessage] = useState('');

  useEffect(() => {
    if (!token) {
      setStatus('error');
      setMessage('Missing verification token.');
      return;
    }

    api(`/api/v1/auth/verify-email?token=${encodeURIComponent(token)}`)
      .then((res) => {
        setStatus('success');
        setMessage(res.data.message);
      })
      .catch((err) => {
        setStatus('error');
        setMessage(err.message || 'Verification failed.');
      });
  }, [token]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-950 px-4" role="main">
      <div className="w-full max-w-md text-center">
        <h1 className="text-3xl font-bold text-slate-50 mb-2">
          <span className="text-amber-500">~</span> WarmPath
        </h1>

        {status === 'loading' && (
          <div className="mt-8" role="status" aria-live="polite">
            <div className="flex justify-center">
              <Spinner size="lg" />
            </div>
            <p className="mt-4 text-slate-400">Verifying your email...</p>
          </div>
        )}

        {status === 'success' && (
          <div className="mt-8 rounded-xl bg-slate-900 p-6 border border-slate-700/50" role="status" aria-live="polite">
            <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-emerald-500/10 text-emerald-400 text-2xl" aria-hidden="true">
              {'\u2713'}
            </div>
            <h2 className="text-lg font-semibold text-slate-50">{message}</h2>
            <p className="mt-2 text-sm text-slate-400">You can now access all marketplace features.</p>
            <Link
              to="/"
              className="mt-4 inline-block rounded-lg bg-amber-500 px-6 py-2.5 text-sm font-medium text-white hover:bg-amber-400"
            >
              Go to Login
            </Link>
          </div>
        )}

        {status === 'error' && (
          <div className="mt-8 rounded-xl bg-slate-900 p-6 border border-slate-700/50" role="alert" aria-live="assertive">
            <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-red-500/10 text-red-400 text-2xl" aria-hidden="true">
              !
            </div>
            <h2 className="text-lg font-semibold text-slate-50">Verification Failed</h2>
            <p className="mt-2 text-sm text-slate-400">{message}</p>
            <Link
              to="/"
              className="mt-4 inline-block rounded-lg bg-amber-500 px-6 py-2.5 text-sm font-medium text-white hover:bg-amber-400"
            >
              Go to Login
            </Link>
          </div>
        )}
      </div>
    </div>
  );
}
