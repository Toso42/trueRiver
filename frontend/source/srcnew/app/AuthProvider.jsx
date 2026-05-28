import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { deleteCurrentUserAvatar, fetchCurrentUser, loginUser, logoutUser, registerUser, uploadCurrentUserAvatar } from '../api/auth';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [authState, setAuthState] = useState({
    loading: true,
    authenticated: false,
    user: null,
    error: '',
  });

  const refreshAuth = useCallback(async () => {
    setAuthState((current) => ({ ...current, loading: true, error: '' }));
    try {
      const payload = await fetchCurrentUser();
      setAuthState({
        loading: false,
        authenticated: Boolean(payload.authenticated),
        user: payload.user || null,
        error: '',
      });
      return payload;
    } catch (error) {
      setAuthState({
        loading: false,
        authenticated: false,
        user: null,
        error: error.message || 'Auth unavailable',
      });
      return null;
    }
  }, []);

  useEffect(() => {
    refreshAuth();
  }, [refreshAuth]);

  const value = useMemo(() => ({
    ...authState,
    refreshAuth,
    async login(credentials) {
      const payload = await loginUser(credentials);
      setAuthState({
        loading: false,
        authenticated: Boolean(payload.authenticated),
        user: payload.user || null,
        error: '',
      });
      return payload;
    },
    async logout() {
      const payload = await logoutUser();
      setAuthState({
        loading: false,
        authenticated: false,
        user: null,
        error: '',
      });
      return payload;
    },
    async register(payload) {
      const response = await registerUser(payload);
      setAuthState({
        loading: false,
        authenticated: Boolean(response.authenticated),
        user: response.user || null,
        error: '',
      });
      return response;
    },
    async uploadAvatar(file) {
      const response = await uploadCurrentUserAvatar(file);
      setAuthState((current) => ({
        ...current,
        loading: false,
        authenticated: Boolean(response.authenticated),
        user: response.user || current.user,
        error: '',
      }));
      return response;
    },
    async deleteAvatar() {
      const response = await deleteCurrentUserAvatar();
      setAuthState((current) => ({
        ...current,
        loading: false,
        authenticated: Boolean(response.authenticated),
        user: response.user || current.user,
        error: '',
      }));
      return response;
    },
  }), [authState, refreshAuth]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) {
    throw new Error('useAuth must be used inside AuthProvider');
  }
  return value;
}

export function useOptionalAuth() {
  return useContext(AuthContext);
}
