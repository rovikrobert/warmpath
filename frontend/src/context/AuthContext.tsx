import { createContext, useCallback, useContext, useEffect, useState, ReactNode } from 'react';
import { useAuth as useClerkAuth, useUser as useClerkUser } from '@clerk/clerk-react';
import { auth as authApi, setTokenGetter } from '../api/client';
import { identifyUser, resetAnalytics } from '../utils/analytics';

interface AuthContextType {
  token: string | null;
  user: any;
  clerkUser: any;
  loading: boolean;
  logout: () => Promise<void>;
  refreshUser: () => Promise<any>;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const { getToken, isSignedIn, isLoaded: authLoaded, signOut } = useClerkAuth();
  const { user: clerkUser, isLoaded: userLoaded } = useClerkUser();
  const [user, setUser] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [clerkTimedOut, setClerkTimedOut] = useState(false);

  // Wire up the API client to use Clerk tokens
  useEffect(() => {
    setTokenGetter(() => getToken());
  }, [getToken]);

  // If Clerk doesn't initialize within 10 seconds, stop blocking the app.
  // This handles cases like production keys on localhost, network failures, etc.
  useEffect(() => {
    if (authLoaded && userLoaded) return;
    const timer = setTimeout(() => {
      if (!authLoaded || !userLoaded) {
        console.warn('Clerk failed to initialize within 10s — continuing without auth');
        setClerkTimedOut(true);
        setLoading(false);
      }
    }, 10_000);
    return () => clearTimeout(timer);
  }, [authLoaded, userLoaded]);

  // Fetch backend user profile when Clerk auth state changes
  useEffect(() => {
    if (clerkTimedOut) return;
    if (!authLoaded || !userLoaded) return;

    if (isSignedIn && clerkUser) {
      authApi.me()
        .then((res) => {
          setUser(res.data);
          identifyUser(res.data.id, { email: res.data.email });
          setLoading(false);
        })
        .catch((err) => {
          setUser(null);
          // If backend returned 401 (user not found / deleted) while Clerk
          // thinks we're signed in, clear the stale Clerk session so the
          // user sees the sign-up page instead of a broken onboarding flow.
          if (err?.status === 401) {
            signOut();
          }
          setLoading(false);
        });
    } else {
      setUser(null);
      resetAnalytics();
      setLoading(false);
    }
  }, [isSignedIn, clerkUser, authLoaded, userLoaded, signOut, clerkTimedOut]);

  const refreshUser = useCallback(async () => {
    const res = await authApi.me();
    setUser(res.data);
    return res.data;
  }, []);

  const logout = useCallback(async () => {
    await signOut();
    setUser(null);
    resetAnalytics();
  }, [signOut]);

  const token = isSignedIn ? 'clerk-managed' : null;

  return (
    <AuthContext.Provider value={{ token, user, clerkUser, loading, logout, refreshUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}

export function BypassAuthProvider({ children }: { children: ReactNode }) {
  const [user] = useState<any>({
    id: 'e2e-user',
    full_name: 'E2E User',
    email: 'e2e@example.com',
    onboarding_complete: true,
    intent: 'find_referrals',
  });

  return (
    <AuthContext.Provider
      value={{
        token: null,
        user,
        clerkUser: null,
        loading: false,
        logout: async () => {},
        refreshUser: async () => user,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}
