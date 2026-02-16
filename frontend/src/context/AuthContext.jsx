import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { auth as authApi, setAuthFailureHandler, setTokenGetter, setTokenSetter } from '../api/client';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [token, setToken] = useState(null);
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [justSignedUp, setJustSignedUp] = useState(false);
  const bootAttempted = useRef(false);

  // Keep the API client's token getter in sync
  const getToken = useCallback(() => token, [token]);

  useEffect(() => {
    setTokenGetter(getToken);
  }, [getToken]);

  // Wire up the token setter so the 401 interceptor can update state
  useEffect(() => {
    setTokenSetter((newToken) => {
      setToken(newToken);
      setTokenGetter(() => newToken);
    });
    setAuthFailureHandler(() => {
      setToken(null);
      setUser(null);
      setJustSignedUp(false);
    });
  }, []);

  // On boot: try to restore session via refresh token cookie
  useEffect(() => {
    if (bootAttempted.current) return;
    bootAttempted.current = true;

    const base = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';
    fetch(`${base}/api/v1/auth/refresh`, {
      method: 'POST',
      credentials: 'include',
    })
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        const newToken = data?.data?.access_token;
        if (newToken) {
          setToken(newToken);
          setTokenGetter(() => newToken);
        } else {
          setLoading(false);
        }
      })
      .catch(() => setLoading(false));
  }, []);

  // Fetch user when token changes
  useEffect(() => {
    if (token && !user) {
      authApi.me().then(res => {
        setUser(res.data);
        setLoading(false);
      }).catch(() => {
        setToken(null);
        setLoading(false);
      });
    } else if (!token) {
      setLoading(false);
    }
  }, [token, user]);

  const refreshUser = useCallback(async () => {
    const res = await authApi.me();
    setUser(res.data);
    return res.data;
  }, []);

  const login = useCallback(async (credentials) => {
    const res = await authApi.login(credentials);
    const newToken = res.data.access_token;
    setToken(newToken);
    setTokenGetter(() => newToken);
    const me = await authApi.me();
    setUser(me.data);
    setJustSignedUp(false);
    return me.data;
  }, []);

  const signup = useCallback(async (body) => {
    const res = await authApi.signup(body);
    const newToken = res.data.access_token;
    setToken(newToken);
    setTokenGetter(() => newToken);
    const me = await authApi.me();
    setUser(me.data);
    setJustSignedUp(true);
    return me.data;
  }, []);

  const loginWithLinkedIn = useCallback(async (tokenData) => {
    const newToken = tokenData.access_token;
    setToken(newToken);
    setTokenGetter(() => newToken);
    const me = await authApi.me();
    setUser(me.data);
    setJustSignedUp(tokenData.is_new_user);
    return me.data;
  }, []);

  const logout = useCallback(() => {
    setToken(null);
    setUser(null);
    setJustSignedUp(false);
  }, []);

  return (
    <AuthContext.Provider value={{ token, user, loading, login, signup, loginWithLinkedIn, logout, refreshUser, justSignedUp, setJustSignedUp }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
