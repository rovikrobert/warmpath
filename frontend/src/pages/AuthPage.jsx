import { SignIn, SignUp } from '@clerk/clerk-react';
import { useCallback, useEffect, useState } from 'react';

export default function AuthPage() {
  const [isSignup, setIsSignup] = useState(
    () => window.location.hash === '#sign-up',
  );

  useEffect(() => {
    const onHashChange = () =>
      setIsSignup(window.location.hash === '#sign-up');
    window.addEventListener('hashchange', onHashChange);
    return () => window.removeEventListener('hashchange', onHashChange);
  }, []);

  const toggle = useCallback(() => {
    const next = !isSignup;
    window.location.hash = next ? '#sign-up' : '';
    setIsSignup(next);
  }, [isSignup]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-950 px-4" role="main">
      <div className="w-full max-w-md">
        <div className="mb-8 text-center">
          <h1 className="text-3xl font-bold text-slate-50">
            <span className="text-amber-500">~</span> WarmPath
          </h1>
          <p className="mt-2 text-lg font-medium text-slate-300">
            Get referred to your dream job
          </p>
          <p className="mt-1 text-sm text-slate-400">
            Employee referrals convert at 40% vs 1% for cold applications.
          </p>
        </div>

        <div className="flex justify-center">
          {isSignup ? (
            <SignUp
              routing="hash"
              fallbackRedirectUrl="/coach"
              signInUrl="/"
              appearance={{
                elements: {
                  rootBox: 'w-full',
                  card: 'bg-slate-900 border border-slate-700/50 shadow-none',
                },
              }}
            />
          ) : (
            <SignIn
              routing="hash"
              fallbackRedirectUrl="/coach"
              signUpUrl="/#sign-up"
              appearance={{
                elements: {
                  rootBox: 'w-full',
                  card: 'bg-slate-900 border border-slate-700/50 shadow-none',
                },
              }}
            />
          )}
        </div>

        <div className="mt-4 text-center">
          <button
            onClick={toggle}
            className="text-sm text-amber-400 hover:text-amber-300"
          >
            {isSignup ? 'Already have an account? Sign in' : "Don't have an account? Sign up"}
          </button>
        </div>
      </div>
    </div>
  );
}
