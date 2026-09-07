import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import {
  authApi, clearToken, getToken, setToken, setUnauthorizedHandler, apiError,
} from '../services/api';

const AuthContext = createContext(null);

/**
 * Does a permission list satisfy `required`?
 *
 * Mirrors the backend's `check_permissions`: "superuser" grants everything and
 * a "<resource>.*" entry covers every action on that resource. Keeping the two
 * in step means the UI hides exactly what the API would refuse.
 */
export function hasPermission(permissions, required) {
  if (!required) return true;
  if (!permissions || permissions.length === 0) return false;
  if (permissions.includes('superuser')) return true;
  if (permissions.includes(required)) return true;

  const parts = required.split('.');
  for (let i = 0; i < parts.length; i += 1) {
    if (permissions.includes(`${parts.slice(0, i + 1).join('.')}.*`)) return true;
  }
  return false;
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [status, setStatus] = useState('loading'); // loading | authenticated | anonymous
  const [config, setConfig] = useState({ auth_required: true, self_registration_enabled: false });
  const mounted = useRef(true);

  // The ref must be re-armed on mount, not only cleared on unmount: React's
  // StrictMode mounts, unmounts and remounts in development, and a ref that is
  // only ever set to false leaves every later state update silently dropped.
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);

  const signOut = useCallback(() => {
    clearToken();
    if (mounted.current) {
      setUser(null);
      setStatus('anonymous');
    }
  }, []);

  // An expired token anywhere in the app drops straight back to the sign-in
  // screen rather than leaving a dead error page behind.
  useEffect(() => {
    setUnauthorizedHandler(() => {
      if (mounted.current) {
        setUser(null);
        setStatus('anonymous');
      }
    });
    return () => setUnauthorizedHandler(null);
  }, []);

  const refresh = useCallback(async () => {
    try {
      const { data } = await authApi.config();
      if (mounted.current) setConfig(data);

      // With enforcement off the API is open, so there is nothing to sign in to.
      if (data && data.auth_required === false) {
        if (mounted.current) {
          setUser(null);
          setStatus('authenticated');
        }
        return;
      }
    } catch {
      /* fall through to the token check; the sign-in screen handles the rest */
    }

    if (!getToken()) {
      if (mounted.current) setStatus('anonymous');
      return;
    }

    try {
      const { data } = await authApi.me();
      if (mounted.current) {
        setUser(data);
        setStatus('authenticated');
      }
    } catch {
      clearToken();
      if (mounted.current) {
        setUser(null);
        setStatus('anonymous');
      }
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const signIn = useCallback(async (username, password) => {
    const { data } = await authApi.login(username, password);
    setToken(data.access_token);
    try {
      const me = await authApi.me();
      if (mounted.current) {
        setUser(me.data);
        setStatus('authenticated');
      }
      return me.data;
    } catch (err) {
      clearToken();
      throw new Error(apiError(err));
    }
  }, []);

  const value = useMemo(() => ({
    user,
    status,
    config,
    signIn,
    signOut,
    refresh,
    permissions: user?.permissions || [],
    isAdmin: Boolean(user?.is_superuser) || (user?.permissions || []).includes('superuser'),
    // With auth enforcement disabled there is no user object, so treat every
    // capability as granted rather than hiding controls that would work.
    can: (permission) => (
      config?.auth_required === false
        ? true
        : hasPermission(user?.permissions, permission)
    ),
  }), [user, status, config, signIn, signOut, refresh]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used inside an AuthProvider');
  return context;
}
