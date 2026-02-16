import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { api } from '../api/client';

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
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
      <div className="w-full max-w-md text-center">
        <h1 className="text-3xl font-bold text-slate-900 mb-2">
          <span className="text-amber-500">~</span> WarmPath
        </h1>

        {status === 'loading' && (
          <div className="mt-8">
            <div className="mx-auto h-8 w-8 animate-spin rounded-full border-4 border-amber-500 border-t-transparent" />
            <p className="mt-4 text-slate-600">Verifying your email...</p>
          </div>
        )}

        {status === 'success' && (
          <div className="mt-8 rounded-xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
            <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-green-100 text-green-600 text-2xl">
              {'\u2713'}
            </div>
            <h2 className="text-lg font-semibold text-slate-900">{message}</h2>
            <p className="mt-2 text-sm text-slate-500">You can now access all marketplace features.</p>
            <Link
              to="/"
              className="mt-4 inline-block rounded-lg bg-amber-500 px-6 py-2.5 text-sm font-medium text-white hover:bg-amber-600"
            >
              Go to Login
            </Link>
          </div>
        )}

        {status === 'error' && (
          <div className="mt-8 rounded-xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
            <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-red-100 text-red-600 text-2xl">
              !
            </div>
            <h2 className="text-lg font-semibold text-slate-900">Verification Failed</h2>
            <p className="mt-2 text-sm text-slate-500">{message}</p>
            <Link
              to="/"
              className="mt-4 inline-block rounded-lg bg-amber-500 px-6 py-2.5 text-sm font-medium text-white hover:bg-amber-600"
            >
              Go to Login
            </Link>
          </div>
        )}
      </div>
    </div>
  );
}
