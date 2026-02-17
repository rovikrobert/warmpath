import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { auth as authApi } from '../api/client';
import { useAuth } from '../context/AuthContext';

export default function LinkedInCallback() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { loginWithLinkedIn } = useAuth();
  const [error, setError] = useState('');

  useEffect(() => {
    const code = searchParams.get('code');
    const state = searchParams.get('state');

    if (!code || !state) {
      setError('Missing authorization code or state parameter.');
      return;
    }

    // Retrieve signup form data if user came from signup flow
    const signupForm = sessionStorage.getItem('linkedin_signup_form');
    let callbackBody = { code, state };
    if (signupForm) {
      try {
        const parsed = JSON.parse(signupForm);
        callbackBody = { ...callbackBody, ...parsed };
      } catch { /* ignore */ }
      sessionStorage.removeItem('linkedin_signup_form');
    }

    authApi.linkedinCallback(callbackBody)
      .then((res) => {
        const data = res.data;
        // Store LinkedIn profile data for EditProfile pre-fill
        if (data.profile) {
          sessionStorage.setItem('linkedin_profile', JSON.stringify(data.profile));
        }
        return loginWithLinkedIn(data);
      })
      .then((user) => {
        // justSignedUp is set inside loginWithLinkedIn based on is_new_user
        const isNew = sessionStorage.getItem('linkedin_profile');
        if (isNew) {
          navigate('/onboarding');
        } else {
          navigate('/dashboard');
        }
      })
      .catch((err) => {
        setError(err.message || 'LinkedIn login failed. Please try again.');
      });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  if (error) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4" role="main">
        <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-sm ring-1 ring-slate-200 text-center" role="alert" aria-live="assertive">
          <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-red-100" aria-hidden="true">
            <svg className="h-6 w-6 text-red-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </div>
          <h2 className="text-lg font-semibold text-slate-900">Login Failed</h2>
          <p className="mt-2 text-sm text-red-600">{error}</p>
          <button
            onClick={() => navigate('/')}
            className="mt-4 rounded-lg bg-amber-500 px-4 py-2 text-sm font-medium text-white hover:bg-amber-600"
          >
            Back to Login
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50" role="main">
      <div className="text-center" role="status" aria-live="polite">
        <div className="mx-auto h-8 w-8 animate-spin rounded-full border-4 border-amber-500 border-t-transparent" role="img" aria-label="Loading" />
        <p className="mt-4 text-sm text-slate-600">Completing LinkedIn sign-in...</p>
      </div>
    </div>
  );
}
