import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { auth as authApi, setTokenGetter } from '../api/client';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [token, setToken] = useState(null);
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [justSignedUp, setJustSignedUp] = useState(false);

  const getToken = useCallback(() => token, [token]);

  useEffect(() => {
    setTokenGetter(getToken);
  }, [getToken]);

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

  const logout = useCallback(() => {
    setToken(null);
    setUser(null);
    setJustSignedUp(false);
  }, []);

  return (
    <AuthContext.Provider value={{ token, user, loading, login, signup, logout, refreshUser, justSignedUp, setJustSignedUp }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
