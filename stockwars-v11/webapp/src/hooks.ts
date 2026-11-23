import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
export function useLoad<T>(path: string, ms = 30000) {
  const [data, set] = useState<T | null>(null);
  const [err, setErr] = useState("");
  const load = useCallback(() => { api<T>(path).then(set).catch((e) => setErr(e.message)); }, [path]);
  useEffect(() => { load(); const t = setInterval(load, ms); return () => clearInterval(t); }, [load, ms]);
  return { data, err, reload: load };
}
