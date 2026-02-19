import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { useAuth as useClerkAuth, useUser as useClerkUser } from '@clerk/clerk-react';
import { auth as authApi, setTokenGetter } from '../api/client';
import { identifyUser, resetAnalytics } from '../utils/analytics';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const { getToken, isSignedIn, isLoaded: authLoaded, signOut } = useClerkAuth();
  const { user: clerkUser, isLoaded: userLoaded } = useClerkUser();
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  // Wire up the API client to use Clerk tokens
  useEffect(() => {
    setTokenGetter(() => getToken());
  }, [getToken]);

  // Fetch backend user profile when Clerk auth state changes
  useEffect(() => {
    if (!authLoaded || !userLoaded) return;

    if (isSignedIn && clerkUser) {
      authApi.me()
        .then((res) => {
          setUser(res.data);
          identifyUser(res.data.id, { email: res.data.email });
          setLoading(false);
        })
        .catch(() => {
          setUser(null);
          setLoading(false);
        });
    } else {
      setUser(null);
      resetAnalytics();
      setLoading(false);
    }
  }, [isSignedIn, clerkUser, authLoaded, userLoaded]);

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
    <AuthContext.Provider value={{ token, user, loading, logout, refreshUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
