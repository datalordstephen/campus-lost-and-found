// Session state: token + user, restored from localStorage on boot.
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api, tokenStore } from "./api/client";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => tokenStore.getUser());
  const [loading, setLoading] = useState(() => Boolean(tokenStore.get()));

  // Re-validate the stored token once at startup; a 30-minute JWT is often stale.
  useEffect(() => {
    if (!tokenStore.get()) {
      setLoading(false);
      return;
    }
    api
      .me()
      .then((fresh) => {
        setUser(fresh);
        tokenStore.setUser(fresh);
      })
      .catch(() => {
        tokenStore.clear();
        setUser(null);
      })
      .finally(() => setLoading(false));
  }, []);

  const adopt = useCallback((session) => {
    tokenStore.set(session.access_token);
    tokenStore.setUser(session.user);
    setUser(session.user);
    return session.user;
  }, []);

  const logout = useCallback(() => {
    tokenStore.clear();
    setUser(null);
  }, []);

  const refresh = useCallback(async () => {
    const fresh = await api.me();
    setUser(fresh);
    tokenStore.setUser(fresh);
    return fresh;
  }, []);

  const value = useMemo(
    () => ({ user, loading, adopt, logout, refresh }),
    [user, loading, adopt, logout, refresh],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export const useAuth = () => useContext(AuthContext);

export const HOME_FOR_ROLE = {
  student: "/student",
  security: "/security",
  admin: "/admin",
};
