import { useEffect, useState } from "react";
export type Pref = "auto" | "light" | "dark";
const tg = (window as any).Telegram?.WebApp;
const KEY = "sw-theme";
const sys = (): "light" | "dark" => tg?.colorScheme ?? (matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark");
const load = (): Pref => { try { return (localStorage.getItem(KEY) as Pref) || "auto"; } catch { return "auto"; } };

export function useTheme() {
  const [pref, setPref] = useState<Pref>(load);
  useEffect(() => {
    const apply = () => {
      const t = pref === "auto" ? sys() : pref;
      document.documentElement.dataset.theme = t;
      const c = t === "light" ? "#f3f5fa" : "#070a10";
      try { tg?.setHeaderColor(c); tg?.setBackgroundColor(c); } catch { /* old clients */ }
    };
    apply();
    try { localStorage.setItem(KEY, pref); } catch { /* storage blocked */ }
    tg?.onEvent?.("themeChanged", apply);
    return () => tg?.offEvent?.("themeChanged", apply);
  }, [pref]);
  return { pref, setPref };
}
