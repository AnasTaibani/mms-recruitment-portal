import { useCallback, useEffect, useState } from "react";
import { api, cleanParams, errMsg } from "@/lib/api";
import { toast } from "sonner";

export function useFetch(path, params = {}, enabled = true) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const key = JSON.stringify(params);
  const reload = useCallback(async () => {
    if (!enabled || !path) { setLoading(false); return; }
    setLoading(true);
    try {
      const r = await api.get(path, { params: cleanParams(JSON.parse(key)) });
      setData(r.data);
    } catch (e) {
      toast.error(errMsg(e));
    } finally {
      setLoading(false);
    }
  }, [path, key, enabled]);
  useEffect(() => { reload(); }, [reload]);
  return { data, loading, reload, setData };
}

export async function act(fn, success) {
  try {
    const r = await fn();
    if (success) toast.success(success);
    return r?.data ?? true;
  } catch (e) {
    toast.error(errMsg(e));
    throw e;
  }
}
