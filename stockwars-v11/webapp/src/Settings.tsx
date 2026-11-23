import { useEffect, useState } from "react";
import { api } from "./api";
import { useT } from "./i18n";
import { Pref } from "./theme";

const MODES: [string, string][] = [["MAJOR", "Major only"], ["ALL", "All"], ["COMPANY", "Company news"], ["SECTOR", "Sector news"], ["NONE", "Off"]];
export default function Settings({ pref, setPref, onClose }: { pref: Pref; setPref: (p: Pref) => void; onClose: () => void }) {
  const { t, lang, setLang } = useT();
  const [mode, setMode] = useState("MAJOR");
  useEffect(() => { api<{ notify_mode: string }>("/settings").then((r) => setMode(r.notify_mode)).catch(() => {}); }, []);
  const pick = (m: string) => { setMode(m); api("/settings", { notify_mode: m }).catch(() => {}); };
  const seg = (on: boolean) => `flex-1 py-2 rounded-xl text-sm font-semibold ${on ? "bg-acc text-white" : "bg-card2 text-mute"}`;
  return (
    <div className="fixed inset-0 bg-black/70 flex items-end z-30" onClick={onClose}>
      <div className="sheet glass border-t border-line w-full rounded-t-3xl p-5 space-y-4 max-w-md mx-auto" onClick={(e) => e.stopPropagation()}>
        <div className="w-10 h-1 rounded-full bg-line mx-auto" />
        <h2 className="font-bold text-lg">{t("Settings")}</h2>
        <div><div className="text-xs text-mute mb-1.5">{t("Theme")}</div><div className="flex gap-2">{(["auto", "light", "dark"] as Pref[]).map((p) => <button key={p} className={seg(pref === p)} onClick={() => setPref(p)}>{t(p[0].toUpperCase() + p.slice(1))}</button>)}</div></div>
        <div><div className="text-xs text-mute mb-1.5">{t("Language")}</div><div className="flex gap-2"><button className={seg(lang === "en")} onClick={() => setLang("en")}>English</button><button className={seg(lang === "hi")} onClick={() => setLang("hi")}>हिन्दी</button></div></div>
        <div><div className="text-xs text-mute mb-1.5">{t("Notifications")}</div><div className="flex flex-wrap gap-2">{MODES.map(([k, l]) => <button key={k} className={seg(mode === k) + " flex-none px-3"} onClick={() => pick(k)}>{t(l)}</button>)}</div></div>
      </div>
    </div>
  );
}
