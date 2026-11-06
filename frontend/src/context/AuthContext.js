import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, tokens } from "@/lib/api";

const AuthCtx = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [meta, setMeta] = useState(null);
  const [masters, setMasters] = useState([]);

  const loadRef = useCallback(async () => {
    const [m, ms] = await Promise.all([api.get("/meta"), api.get("/masters")]);
    setMeta(m.data);
    setMasters(ms.data);
  }, []);

  useEffect(() => {
    api.get("/auth/me").then((r) => { setUser(r.data); loadRef(); }).catch(() => setUser(false));
    const out = () => setUser(false);
    window.addEventListener("mms:logout", out);
    return () => window.removeEventListener("mms:logout", out);
  }, [loadRef]);

  const login = async (email, password) => {
    const r = await api.post("/auth/login", { email, password });
    tokens.set(r.data);
    const { access_token, refresh_token, ...u } = r.data;
    setUser(u);
    await loadRef();
    return u;
  };
  const logout = async () => {
    await api.post("/auth/logout").catch(() => {});
    tokens.clear();
    setUser(false);
  };

  return (
    <AuthCtx.Provider value={{ user, setUser, login, logout, can, meta, masters, list, mname, reloadRef: loadRef }}>
      {children}
    </AuthCtx.Provider>
  );
}

export const useAuth = () => useContext(AuthCtx);
