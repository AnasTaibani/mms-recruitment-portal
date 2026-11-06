import axios from "axios";
import { format, parseISO } from "date-fns";

export const api = axios.create({ baseURL: `${process.env.REACT_APP_BACKEND_URL || ""}/api`, withCredentials: true });

// Login tokens are kept here as well as in cookies, and sent as headers, so sign-in
// keeps working when the browser blocks the cookies (e.g. API on another domain).
const TOKEN_KEY = "mms_tokens";
export const tokens = {
  get() { try { return JSON.parse(localStorage.getItem(TOKEN_KEY)) || {}; } catch { return {}; } },
  set(d) { try { if (d?.access_token) localStorage.setItem(TOKEN_KEY, JSON.stringify({ access_token: d.access_token, refresh_token: d.refresh_token })); } catch { /* storage unavailable */ } },
  clear() { try { localStorage.removeItem(TOKEN_KEY); } catch { /* storage unavailable */ } },
};
api.interceptors.request.use((cfg) => {
  const t = tokens.get();
  if (t.access_token) cfg.headers.Authorization = `Bearer ${t.access_token}`;
  if (t.refresh_token && cfg.url === "/auth/refresh") cfg.headers["X-Refresh-Token"] = t.refresh_token;
  return cfg;
});

let refreshing = null;
api.interceptors.response.use(
  (r) => r,
  async (error) => {
    const cfg = error.config || {};
    const url = cfg.url || "";
    if (error.response?.status === 401 && !cfg._retry && !url.startsWith("/auth/")) {
      cfg._retry = true;
      try {
        refreshing = refreshing || api.post("/auth/refresh");
        const res = await refreshing;
        tokens.set(res.data);
        refreshing = null;
        return api(cfg);
      } catch (e) {
        refreshing = null;
        tokens.clear();
        window.dispatchEvent(new Event("mms:logout"));
      }
    }
    return Promise.reject(error);
  }
);

export function errMsg(e) {
  const d = e?.response?.data?.detail;
  if (!d) return e?.message || "Something went wrong";
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map((x) => x?.msg || JSON.stringify(x)).join(" ");
  if (d.message) return d.message;
  return String(d);
}

export async function download(path, params = {}) {
  const res = await api.get(path, { params, responseType: "blob" });
  const cd = res.headers["content-disposition"] || "";
  const name = (cd.match(/filename="?([^"]+)"?/) || [])[1] || "download";
  const url = URL.createObjectURL(res.data);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

export const lakhs = (n) => (n === null || n === undefined || n === "" ? "—" : `₹${Number(n).toFixed(2)} L`);
export const fmtDate = (d) => {
  if (!d) return "—";
  try { return format(parseISO(d), "dd MMM yyyy"); } catch { return d; }
};
export const fmtDateTime = (d) => {
  if (!d) return "—";
  try { return format(parseISO(d), "dd MMM yyyy, HH:mm"); } catch { return d; }
};
export const num = (n, suffix = "") => (n === null || n === undefined ? "N/A" : `${n}${suffix}`);
export const cleanParams = (o) => Object.fromEntries(Object.entries(o).filter(([, v]) => v !== "" && v !== null && v !== undefined && v !== "__all"));
