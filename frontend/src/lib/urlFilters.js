import { useLocation } from "react-router-dom";

/** Initial list filters merged with ?key=value from the URL, so dashboard cards can open a pre-filtered list. */
export function useUrlDefaults(defaults = {}, allowed = []) {
  const { search } = useLocation();
  const q = new URLSearchParams(search);
  const fromUrl = Object.fromEntries(allowed.filter((k) => q.get(k)).map((k) => [k, q.get(k)]));
  return { ...defaults, ...fromUrl };
}
