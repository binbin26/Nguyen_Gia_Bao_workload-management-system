import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

import {
  getCurrentUser,
  loginRequest,
  logoutRequest,
  onSessionExpired,
} from "../services/auth_api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  // JWTs never enter React state or Web Storage. Only non-sensitive display and
  // authorization metadata returned by /me is kept in memory.
  const [user, setUser] = useState(null);
  const [isInitializing, setIsInitializing] = useState(true);

  useEffect(() => {
    let isMounted = true;

    // One-time migration cleanup from the previous Bearer/localStorage design.
    // These values are never read; removing them limits exposure after upgrade.
    try {
      localStorage.removeItem("auth_token");
      localStorage.removeItem("auth_user");
    } catch {
      // Some privacy modes disable Web Storage. Auth uses cookies and can
      // continue safely even when legacy cleanup is unavailable.
    }

    const removeSessionExpiredListener = onSessionExpired(() => setUser(null));

    getCurrentUser()
      .then((currentUser) => {
        if (isMounted) {
          setUser(currentUser);
        }
      })
      .catch(() => {
        if (isMounted) {
          setUser(null);
        }
      })
      .finally(() => {
        if (isMounted) {
          setIsInitializing(false);
        }
      });

    return () => {
      isMounted = false;
      removeSessionExpiredListener();
    };
  }, []);

  const login = useCallback(async ({ username, password }) => {
    const loggedInUser = await loginRequest({ username, password });
    setUser(loggedInUser);
    return loggedInUser;
  }, []);

  const logout = useCallback(async () => {
    try {
      await logoutRequest();
    } finally {
      // Local state is always cleared even if the network is unavailable. The
      // server-side refresh session remains bounded by its expiry in that case.
      setUser(null);
    }
  }, []);

  const value = useMemo(
    () => ({
      user,
      isAuthenticated: Boolean(user),
      isInitializing,
      login,
      logout,
    }),
    [isInitializing, login, logout, user],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used inside AuthProvider");
  }
  return context;
}
