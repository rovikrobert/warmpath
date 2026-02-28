import { SignIn, SignUp } from '@clerk/clerk-react';
import { useEffect, useState } from 'react';
import SourceTag from '../components/ui/SourceTag';
import { SOURCES } from '../utils/sources';
import useDocumentTitle from '../hooks/useDocumentTitle';

function hashIndicatesSignup() {
  const h = window.location.hash;
  // Match #sign-up and any Clerk sub-routes (#/sign-up/verify-email-address, etc.)
  // so the SignUp component stays mounted through multi-step flows like email verification.
  return h === '#sign-up' || h.startsWith('#sign-up/') || h.startsWith('#/sign-up');
}

export default function AuthPage() {
  useDocumentTitle('Sign In');
  const [isSignup, setIsSignup] = useState(hashIndicatesSignup);

  useEffect(() => {
    const onHashChange = () => setIsSignup(hashIndicatesSignup());
    window.addEventListener('hashchange', onHashChange);
    return () => window.removeEventListener('hashchange', onHashChange);
  }, []);

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4" role="main">
      <div className="w-full max-w-md">
        <div className="mb-8 text-center">
          <h1 className="text-3xl font-bold text-foreground">
            <span className="text-primary">~</span> WarmPath
          </h1>
          <p className="mt-2 text-lg font-medium text-secondary-foreground">
            Get referred to your dream job
          </p>
          <p className="mt-1 text-sm text-muted-foreground">
            Employee referrals convert at {SOURCES.COLD_VS_REFERRAL.claim} for cold applications.{' '}
            <SourceTag source={SOURCES.COLD_VS_REFERRAL.source} label={SOURCES.COLD_VS_REFERRAL.label} />
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
                  card: 'bg-card border border-border shadow-none',
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
                  card: 'bg-card border border-border shadow-none',
                },
              }}
            />
          )}
        </div>
      </div>
    </div>
  );
}
