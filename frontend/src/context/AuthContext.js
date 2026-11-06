import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api } from "@/lib/api";

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
    setUser(r.data);
    await loadRef();
    return r.data;
  };
  const logout = async () => {
    await api.post("/auth/logout").catch(() => {});
    setUser(false);
  };
  const can = (p) => !!user && user.permissions?.includes(p);
  const list = (type, all = false) => masters.filter((m) => m.type === type && (all || m.active));
  const mname = (id) => masters.find((m) => m.id === id)?.name;

  return (
    <AuthCtx.Provider value={{ user, setUser, login, logout, can, meta, masters, list, mname, reloadRef: loadRef }}>
      {children}
    </AuthCtx.Provider>
  );
}

export const useAuth = () => useContext(AuthCtx);
