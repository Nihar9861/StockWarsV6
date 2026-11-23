import { useState } from "react";
import { api, inr, haptic } from "./api";
import { useLoad } from "./hooks";
import { useT } from "./i18n";

type R = { rank: string; daily: { claimable: boolean; streak: number; amount: string }; missions: { key: string; title: string; target: number; reward: number; progress: number; done: boolean; claimed: boolean }[]; badges: { key: string; title: string; earned: boolean }[] };
const card = "bg-card border border-line rounded-2xl p-3.5 fade";

export default function Rewards({ onChange }: { onChange: () => void }) {
  const { t } = useT();
  const { data: r, reload } = useLoad<R>("/rewards");
  const [msg, setMsg] = useState("");
  if (!r) return <div className="skel h-40" />;
  const act = async (path: string) => {
    setMsg("");
    try { const x = await api<{ amount: string }>(path, {}); haptic(); setMsg("✅ +" + inr(x.amount)); reload(); onChange(); } catch (e) { setMsg("❌ " + (e as Error).message); }
  };
  return (
    <div className="space-y-3">
      <div className={card + " flex items-center justify-between"}><div><div className="text-xs text-mute">Rank</div><div className="text-xl font-extrabold">{r.rank}</div></div>
        <div className="text-right"><div className="text-xs text-mute">{t("Streak")}</div><div className="text-xl font-extrabold">{r.daily.streak} <span className="text-sm text-mute">days</span></div></div></div>
      <div className={card + " flex items-center justify-between"}>
        <div><div className="font-bold">{t("Daily reward")}</div><div className="text-xs text-mute">{inr(r.daily.amount)} · bigger every day (7-day streak)</div></div>
        <button disabled={!r.daily.claimable} onClick={() => act("/rewards/daily")} className="bg-up text-black px-4 py-2 rounded-xl font-bold disabled:opacity-40">{r.daily.claimable ? t("Claim") : "Done"}</button></div>
      {msg && <div className="text-sm px-1">{msg}</div>}
      <h2 className="font-bold px-1 pt-2">{t("Missions")}</h2>
      {r.missions.map((m) => (
        <div key={m.key} className={card}>
          <div className="flex justify-between items-center"><div><div className="font-semibold">{m.title}</div><div className="text-xs text-mute">Reward {inr(m.reward)} · {m.progress}/{m.target}</div></div>
            <button disabled={!m.done || m.claimed} onClick={() => act("/rewards/mission/" + m.key)} className="bg-acc text-white px-3 py-1.5 rounded-xl text-sm font-bold disabled:opacity-40">{m.claimed ? "Done" : t("Claim")}</button></div>
          <div className="h-1.5 rounded-full bg-card2 mt-2 overflow-hidden"><div className="h-full bg-acc" style={{ width: `${(m.progress / m.target) * 100}%` }} /></div>
        </div>))}
      <h2 className="font-bold px-1 pt-2">{t("Badges")}</h2>
      <div className="grid grid-cols-3 gap-2">{r.badges.map((b) => (
        <div key={b.key} className={`rounded-2xl p-2.5 text-center text-[11px] font-semibold border ${b.earned ? "bg-gold/15 border-gold/40 text-gold" : "bg-card border-line text-mute opacity-60"}`}>
          <div className="text-xl mb-0.5">{b.earned ? "★" : "☆"}</div>{b.title}</div>))}</div>
    </div>
  );
}
