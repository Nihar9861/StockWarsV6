import { useEffect, useState } from "react";
import { api, inr, haptic } from "./api";
import { useLoad } from "./hooks";

type Stock = { ticker: string; name: string; price: string; prev: string };
type P = { user_id: number; name: string; value: string; pct: number; pos: number; me: boolean; prize: string; xp: number; holdings: { ticker: string; qty: number }[] | null };
type D = { id: number; code: string; format: string; name: string; status: string; host_id: number; start_cash: string; duration_min: number; sectors: string[]; ends_at: string | null; max_players: number; min_players: number; players: P[]; me: { cash: string; holdings: { ticker: string; qty: number; avg: string; price: string; value: string }[] } | null };
type A = { stats: { played: number; wins: number; win_rate: number; best_profit: string; trophies: number; xp: number }; active: number | null; lobbies: { id: number; code: string; name: string; host: string; players: number; max: number; sectors: string[]; start_cash: string; duration_min: number }[]; history: { id: number; name: string; code: string; rank: number; value: string; pct: number; prize: string; xp: number }[] };

const card = "bg-card border border-line rounded-2xl p-3.5 fade";
const inp = "w-full bg-card2 border border-line rounded-xl p-3 text-sm";
const medal = ["#f5b94a", "#b8c2d1", "#c8814a"];
const FORMATS: [string, string][] = [["QUICK", "Quick · 30 min · ₹5L"], ["DAILY", "Daily · 24 h · ₹10L"], ["WEEKLY", "Weekly · 7 days · ₹50L"], ["SECTOR", "Sector · 24 h · ₹10L"]];

function useCountdown(end: string | null) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(t); }, []);
  if (!end) return "";
  const s = Math.max(0, Math.floor((new Date(end).getTime() - now) / 1000)), h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
  return `${h ? h + "h " : ""}${m}m ${String(s % 60).padStart(2, "0")}s`;
}

function Board({ players, final }: { players: P[]; final: boolean }) {
  return (
    <div className="space-y-2">{players.map((p) => (
      <div key={p.user_id} className={`${card} flex items-center gap-3 ${p.me ? "border-acc bg-acc/10" : ""}`}>
        <div className="w-8 h-8 rounded-full grid place-items-center font-extrabold text-sm shrink-0" style={p.pos <= 3 ? { background: medal[p.pos - 1], color: "#000" } : { background: "rgb(var(--line))" }}>{p.pos}</div>
        <div className="flex-1 min-w-0"><div className="font-semibold truncate">{p.name}{p.me && <span className="text-acc text-xs ml-1">you</span>}</div>
          {final && p.holdings ? <div className="text-[11px] text-mute truncate">{p.holdings.map((h) => `${h.ticker}×${h.qty}`).join(", ") || "cash only"}</div> : <div className="text-[11px] text-mute">holdings hidden</div>}</div>
        <div className="text-right"><div className="font-bold">{inr(p.value)}</div><div className={`text-xs font-semibold ${p.pct >= 0 ? "text-up" : "text-down"}`}>{p.pct >= 0 ? "+" : ""}{p.pct.toFixed(2)}%</div>
          {final && (p.xp > 0 || Number(p.prize) > 0) && <div className="text-[10px] text-gold">+{p.xp} XP{Number(p.prize) > 0 ? ` · +${inr(p.prize)}` : ""}</div>}</div>
      </div>))}</div>
  );
}

function TradeSheet({ stocks, d, side, onClose, onDone }: { stocks: Stock[]; d: D; side: "BUY" | "SELL"; onClose: () => void; onDone: () => void }) {
  const list = side === "SELL" ? stocks.filter((s) => d.me?.holdings.some((h) => h.ticker === s.ticker)) : stocks;
  const [tk, setTk] = useState(list[0]?.ticker ?? "");
  const [qty, setQty] = useState("1"); const [msg, setMsg] = useState(""); const [busy, setBusy] = useState(false); const [key] = useState(() => crypto.randomUUID());
  const s = stocks.find((x) => x.ticker === tk);
  const q = Math.max(0, parseInt(qty) || 0), val = q * Number(s?.price ?? 0);
  const go = async () => {
    setBusy(true); setMsg("");
    try { await api("/battle/trade", { ticker: tk, side, qty: q, key }); haptic(); onDone(); onClose(); } catch (e) { setMsg((e as Error).message); setBusy(false); }
  };
  return (
    <div className="fixed inset-0 bg-black/70 flex items-end z-30" onClick={onClose}>
      <div className="sheet glass border-t border-line w-full rounded-t-3xl p-5 space-y-3 max-w-md mx-auto" onClick={(e) => e.stopPropagation()}>
        <div className="w-10 h-1 rounded-full bg-line mx-auto" />
        <h2 className="font-bold text-lg">{side === "BUY" ? "Buy" : "Sell"} · battle cash {inr(d.me?.cash ?? 0)}</h2>
        {!list.length ? <div className="text-mute text-sm">Nothing to sell yet.</div> : <>
          <select className={inp} value={tk} onChange={(e) => setTk(e.target.value)}>{list.map((x) => <option key={x.ticker} value={x.ticker}>{x.ticker} — {inr(x.price)}</option>)}</select>
          <input className={inp} type="number" min={1} value={qty} onChange={(e) => setQty(e.target.value)} />
          <div className="text-sm text-mute">Value {inr(val)} + 0.25% fee</div>
          {msg && <div className="text-down text-sm">{msg}</div>}
          <button disabled={busy || q < 1} onClick={go} className={`w-full py-3 rounded-xl font-bold disabled:opacity-40 ${side === "BUY" ? "bg-up text-black" : "bg-down text-white"}`}>{busy ? "…" : `Confirm ${side === "BUY" ? "Buy" : "Sell"}`}</button></>}
      </div>
    </div>
  );
}

function Live({ id, stocks, status, onBack, onChange }: { id: number; stocks: Stock[]; status: string; onBack: () => void; onChange: () => void }) {
  const { data: d, reload } = useLoad<D>(`/battle/${id}`, 8000);
  const [side, setSide] = useState<"BUY" | "SELL" | null>(null);
  const [msg, setMsg] = useState("");
  const left = useCountdown(d?.ends_at ?? null);
  if (!d) return <div className="skel h-40" />;
  const host = d.players.find((p) => p.user_id === d.host_id);
  const act = async (path: string) => { setMsg(""); try { await api(path, {}); reload(); onChange(); if (path.endsWith("leave")) onBack(); } catch (e) { setMsg("❌ " + (e as Error).message); } };
  const iAmHost = d.players.find((p) => p.me)?.user_id === d.host_id;
  return (
    <div className="space-y-3 fade">
      <button onClick={onBack} className="text-mute text-sm">← Arena</button>
      <div className="rounded-3xl p-5" style={{ background: "linear-gradient(135deg,#5b21b6,#2563eb 70%,#0ea5a4)" }}>
        <div className="text-xs text-white/70">{d.name} · {d.status}</div>
        <div className="text-2xl font-extrabold">Room {d.code}</div>
        <div className="text-sm mt-1 text-white/90">{d.status === "LIVE" ? `⏱ ${left} left` : d.status === "FINISHED" ? "Finished" : `Waiting for players ${d.players.length}/${d.max_players} (min ${d.min_players})`}</div>
        <div className="text-xs text-white/70 mt-1">{inr(d.start_cash)} each · {d.sectors.length ? d.sectors.join(", ") : "all sectors"}</div>
      </div>
      {d.status === "LOBBY" && <div className={card + " space-y-2"}>
        <div className="text-sm text-mute">Share code <b className="text-ink tracking-widest">{d.code}</b> with friends. In the bot they use <code>/battlejoin {d.code}</code>. Host: {host?.name}.</div>
        <div className="flex gap-2">{iAmHost && <button className="flex-1 bg-up text-black py-2.5 rounded-xl font-bold" onClick={() => act("/battle/start")}>Start battle</button>}
          <button className="flex-1 bg-card2 text-mute py-2.5 rounded-xl font-semibold" onClick={() => act("/battle/leave")}>Leave</button></div></div>}
      {msg && <div className="text-sm">{msg}</div>}
      <h2 className="font-bold px-1">{d.status === "FINISHED" ? "Final result" : "Live ranking"}</h2>
      <Board players={d.players} final={d.status === "FINISHED"} />
      {d.status === "LIVE" && d.me && <>
        <div className={card}><div className="text-xs text-mute">Your battle portfolio</div><div className="font-bold">Cash {inr(d.me.cash)}</div>
          {d.me.holdings.map((h) => <div key={h.ticker} className="flex justify-between text-sm mt-1"><span>{h.ticker} ×{h.qty}</span><span>{inr(h.value)}</span></div>)}</div>
        {status !== "OPEN" && <div className="text-center text-sm text-gold bg-gold/10 rounded-xl py-2">Market is {status} — trading paused</div>}
        <div className="grid grid-cols-2 gap-3"><button disabled={status !== "OPEN"} onClick={() => setSide("BUY")} className="bg-up text-black py-3 rounded-xl font-bold disabled:opacity-30">Buy</button>
          <button disabled={status !== "OPEN"} onClick={() => setSide("SELL")} className="bg-down text-white py-3 rounded-xl font-bold disabled:opacity-30">Sell</button></div>
        <div className="text-[11px] text-mute text-center">Everyone sees the same prices. You see rankings, not what others bought — holdings are revealed at the end.</div></>}
      {side && <TradeSheet stocks={d.sectors.length ? stocks : stocks} d={d} side={side} onClose={() => setSide(null)} onDone={reload} />}
    </div>
  );
}

export default function Arena({ stocks, status, onChange }: { stocks: Stock[]; status: string; onChange: () => void }) {
  const { data, reload } = useLoad<A>("/arena", 10000);
  const [view, setView] = useState<number | null>(null);
  const [fmt, setFmt] = useState("DAILY"); const [sectors, setSectors] = useState(""); const [code, setCode] = useState(""); const [msg, setMsg] = useState("");
  if (!data) return <div className="space-y-3"><div className="skel h-24" /><div className="skel h-40" /></div>;
  const open = view ?? data.active;
  if (open) return <Live id={open} stocks={stocks} status={status} onBack={() => { setView(null); reload(); }} onChange={() => { reload(); onChange(); }} />;
  const go = async (path: string, body: object) => {
    setMsg("");
    try { const r = await api<{ id: number }>(path, body); haptic(); reload(); setView(r.id); } catch (e) { setMsg("❌ " + (e as Error).message); }
  };
  const st = data.stats;
  return (
    <div className="space-y-3 fade">
      <div className="rounded-3xl p-5" style={{ background: "linear-gradient(135deg,#5b21b6,#2563eb 70%,#0ea5a4)" }}>
        <div className="text-lg font-extrabold">⚔️ Portfolio Battle</div>
        <div className="text-sm text-white/85">Same cash, same market. 2–6 players. Best portfolio wins — holdings stay hidden until the end.</div>
        <div className="grid grid-cols-4 gap-2 mt-3 text-center text-xs">{[["Played", st.played], ["Wins", st.wins], ["Win rate", st.win_rate + "%"], ["XP", st.xp]].map(([l, v]) => <div key={l as string} className="bg-black/20 rounded-xl py-2"><div className="text-base font-extrabold">{v}</div><div className="text-white/70">{l}</div></div>)}</div>
      </div>
      <div className={card + " space-y-2"}>
        <b>Create a room</b>
        <select className={inp} value={fmt} onChange={(e) => setFmt(e.target.value)}>{FORMATS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>
        {fmt === "SECTOR" && <input className={inp} placeholder="Sectors, comma separated (e.g. Technology,Banking)" value={sectors} onChange={(e) => setSectors(e.target.value)} />}
        <button className="w-full bg-acc text-white py-2.5 rounded-xl font-bold" onClick={() => go("/battle/create", { format: fmt, sectors: sectors.split(",").map((x) => x.trim()).filter(Boolean) })}>Create room</button>
        <div className="flex gap-2"><input className={inp} placeholder="Room code" value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} maxLength={8} /><button className="bg-up text-black px-5 rounded-xl font-bold" onClick={() => go("/battle/join", { code })}>Join</button></div>
        {msg && <div className="text-sm">{msg}</div>}
      </div>
      <h2 className="font-bold px-1">Open rooms</h2>
      {data.lobbies.map((l) => (
        <div key={l.id} className={card + " flex items-center gap-3"}><div className="flex-1"><div className="font-bold">{l.name}</div><div className="text-xs text-mute">by {l.host} · {l.players}/{l.max} players · {inr(l.start_cash)}{l.sectors.length ? " · " + l.sectors.join(", ") : ""}</div></div>
          <button className="bg-up text-black px-4 py-2 rounded-xl font-bold" onClick={() => go("/battle/join", { code: l.code })}>Join</button></div>))}
      {!data.lobbies.length && <div className="text-sm text-mute px-1">No open rooms — create one and invite 3–5 friends!</div>}
      <h2 className="font-bold px-1 pt-1">Your stats</h2>
      <div className="grid grid-cols-2 gap-3"><div className={card}><div className="text-xs text-mute">Best profit</div><div className="font-bold text-up">{inr(st.best_profit)}</div></div><div className={card}><div className="text-xs text-mute">Trophies</div><div className="font-bold text-gold">{st.trophies} 🏆</div></div></div>
      <h2 className="font-bold px-1">History</h2>
      {data.history.map((h) => (
        <button key={h.id} onClick={() => setView(h.id)} className={card + " w-full flex justify-between items-center text-left"}><div><div className="font-semibold">{h.name} · {h.code}</div><div className="text-xs text-mute">+{h.xp} XP{Number(h.prize) > 0 ? ` · +${inr(h.prize)}` : ""}</div></div>
          <div className="text-right"><div className="font-bold">#{h.rank}</div><div className={`text-xs font-semibold ${h.pct >= 0 ? "text-up" : "text-down"}`}>{h.pct >= 0 ? "+" : ""}{h.pct.toFixed(1)}%</div></div></button>))}
      {!data.history.length && <div className="text-sm text-mute px-1">No battles yet.</div>}
    </div>
  );
}
