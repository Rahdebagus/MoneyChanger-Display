// ─── Auth Context ─────────────────────────────────────────────────────────────
//
// Holds the signed-in user and the bearer token. The token lives in
// localStorage so a page reload does not log the user out; it is short lived
// and the server can revoke it outright by bumping the account's token
// version, which is what a password change or a deactivation does.

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  TOKEN_STORAGE_KEY,
  authApi,
  branchApi,
  readStored,
  setUnauthorizedHandler,
  writeStored,
} from "../services/apiClient.js";

import { AuthContext } from "./authContext.js";

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => readStored(TOKEN_STORAGE_KEY));
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(Boolean(readStored(TOKEN_STORAGE_KEY)));

  // An admin has no per-branch assignments because they can reach every
  // branch, so user.branches is empty for them. Branch pickers still need a
  // list, which for an admin is "all branches" and for staff is exactly what
  // they were assigned.
  const [allBranches, setAllBranches] = useState([]);

  const clearSession = useCallback(() => {
    writeStored(TOKEN_STORAGE_KEY, null);
    setToken(null);
    setUser(null);
    setAllBranches([]);
    setLoading(false);
  }, []);

  const loadAdminBranches = useCallback((profile) => {
    if (profile?.role !== "admin") {
      setAllBranches([]);
      return;
    }
    branchApi
      .list()
      .then(setAllBranches)
      .catch(() => setAllBranches([]));
  }, []);

  // Any 401 anywhere in the app drops the session rather than leaving the UI
  // in a half-signed-in state.
  useEffect(() => {
    setUnauthorizedHandler(() => clearSession());
    return () => setUnauthorizedHandler(null);
  }, [clearSession]);

  // Re-validate a stored token on boot: it may have expired or been revoked
  // while the tab was closed.
  useEffect(() => {
    let cancelled = false;
    if (!token) {
      return undefined;
    }

    authApi
      .me()
      .then((profile) => {
        if (!cancelled) {
          setUser(profile);
          loadAdminBranches(profile);
          setLoading(false);
        }
      })
      .catch(() => {
        if (!cancelled) clearSession();
      });

    return () => {
      cancelled = true;
    };
  }, [token, clearSession, loadAdminBranches]);

  const login = useCallback(async (username, password) => {
    const result = await authApi.login(username, password);
    writeStored(TOKEN_STORAGE_KEY, result.access_token);
    setToken(result.access_token);
    setUser(result.user);
    return result.user;
  }, []);

  const logout = useCallback(async () => {
    try {
      await authApi.logout();
    } catch {
      /* logging out locally matters more than the server acknowledging it */
    }
    clearSession();
  }, [clearSession]);

  const value = useMemo(
    () => ({
      user,
      token,
      loading,
      isAuthenticated: Boolean(user),
      isAdmin: user?.role === "admin",
      branches: user?.role === "admin" ? allBranches : (user?.branches ?? []),
      reloadBranches: () => loadAdminBranches(user),
      login,
      logout,
      refresh: () => authApi.me().then(setUser),
    }),
    [user, token, loading, allBranches, login, logout, loadAdminBranches]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
