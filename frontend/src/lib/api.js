import axios from "axios";
import { format, parseISO } from "date-fns";

export const api = axios.create({ baseURL: `${process.env.REACT_APP_BACKEND_URL}/api`, withCredentials: true });

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
        await refreshing;
        refreshing = null;
        return api(cfg);
      } catch (e) {
        refreshing = null;
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
