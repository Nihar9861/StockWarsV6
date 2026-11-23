import { useState } from "react";
import { api, inr } from "./api";
import { useLoad } from "./hooks";
import { Line } from "./Chart";
import { useT } from "./i18n";

const card = "bg-card border border-line rounded-2xl p-3.5 fade";
const inp = "w-full bg-card2 border border-line rounded-xl p-3 text-sm";
const chip = (on: boolean) => `px-3 py-1 rounded-lg text-xs font-semibold ${on ? "bg-acc text-white" : "bg-card2 text-mute"}`;
const col = (n: number) => (n >= 0 ? "text-up" : "text-down");

export function Perf() {
  const { t } = useT();
  const [rg, setRg] = useState("7d");
  const { data } = useLoad<{ t: string; v: string }[]>("/performance?range=" + rg);
  const v = (data ?? []).map((x) => Number(x.v)), chg = v.length > 1 ? v[v.length - 1] - v[0] : 0;
  return (
    <div className={card}>
      <div className="flex justify-between items-center mb-2">
        <div><div className="text-xs text-mute">Performance</div><div className={`font-extrabold ${col(chg)}`}>{chg >= 0 ? "+" : ""}{inr(chg)}</div></div>
        <div className="flex gap-1">{[["today", "Today"], ["7d", "7 days"], ["30d", "30 days"], ["all", "All time"]].map(([k, l]) => <button key={k} className={chip(rg === k)} onClick={() => setRg(k)}>{t(l)}</button>)}</div></div>
      {v.length > 1 ? <Line p={v} /> : <div className="h-32 grid place-items-center text-sm text-mute text-center">Chart fills in as snapshots are saved (every ~15 min while the market is open)</div>}
    </div>
  );
}

type Tr = { ticker: string; side: string; qty: number; price: string; value: string; fee: string; at: string };
export function HistoryView() {
  const { t } = useT();
  const { data } = useLoad<Tr[]>("/trades");
  const [f, setF] = useState("ALL");
  const rows = (data ?? []).filter((x) => f === "ALL" || x.side === f);
  return (
    <div className="space-y-2">
      <div className="flex gap-1.5">{["ALL", "BUY", "SELL"].map((k) => <button key={k} className={chip(f === k)} onClick={() => setF(k)}>{k === "ALL" ? t("All") : k === "BUY" ? t("Buy") : t("Sell")}</button>)}</div>
      {rows.map((x, i) => (
        <div key={i} className={card + " flex justify-between items-center"}>
          <div><div className="font-bold"><span className={x.side === "BUY" ? "text-up" : "text-down"}>{x.side}</span> {x.ticker} ×{x.qty}</div><div className="text-xs text-mute">{new Date(x.at).toLocaleString()}</div></div>
          <div className="text-right text-sm"><div>{inr(x.value)}</div><div className="text-xs text-mute">@ {inr(x.price)} · fee {inr(x.fee)}</div></div></div>))}
      {!rows.length && <div className="text-center text-mute py-10">{t("No trades yet.")}</div>}
    </div>
  );
}

type Deal = { id: number; kind: string; ticker: string; my_side: string; qty: number; price: string; status: string; other: string; mine: boolean; expires_at: string };
export function DealsView({ tickers, onChange }: { tickers: string[]; onChange: () => void }) {
  const { t } = useT();
  const { data, reload } = useLoad<Deal[]>("/deals");
  const [f, setF] = useState({ to: "", ticker: tickers[0] ?? "", side: "SELL", qty: "1", price: "", takeover: false });
  const [msg, setMsg] = useState("");
  const run = async (path: string, body: object = {}) => {
    setMsg("");
    try { await api(path, body); setMsg("✅ Done"); reload(); onChange(); } catch (e) { setMsg("❌ " + (e as Error).message); }
  };
  return (
    <div className="space-y-3">
      <div className={card + " space-y-2"}>
        <b>{t("New deal")}</b>
        <div className="text-xs text-mute">Sell or buy shares directly with another player (price within ±10% of market, 0.25% fee each side, max 3 deals per pair per day). Takeover: bid ≥10% above market for a founder's entire stake — you must end up with ≥51%.</div>
        <input className={inp} placeholder="Player ID or @username" value={f.to} onChange={(e) => setF({ ...f, to: e.target.value })} />
        <div className="grid grid-cols-2 gap-2">
          <select className={inp} value={f.ticker} onChange={(e) => setF({ ...f, ticker: e.target.value })}>{tickers.map((x) => <option key={x}>{x}</option>)}</select>
          <select className={inp} disabled={f.takeover} value={f.takeover ? "BUY" : f.side} onChange={(e) => setF({ ...f, side: e.target.value })}><option value="SELL">I sell</option><option value="BUY">I buy</option></select>
          {!f.takeover && <input className={inp} type="number" placeholder="Quantity" value={f.qty} onChange={(e) => setF({ ...f, qty: e.target.value })} />}
          <input className={inp} type="number" step="0.01" placeholder="Price / share" value={f.price} onChange={(e) => setF({ ...f, price: e.target.value })} />
        </div>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={f.takeover} onChange={(e) => setF({ ...f, takeover: e.target.checked })} /> Takeover bid</label>
        <button className="w-full bg-acc text-white py-2.5 rounded-xl font-semibold" onClick={() => run("/deals", { to: f.to, ticker: f.ticker, side: f.side, qty: Number(f.qty) || 0, price: f.price || "0", takeover: f.takeover })}>Send offer</button>
        {msg && <div className="text-sm">{msg}</div>}
      </div>
      {(data ?? []).map((d) => (
        <div key={d.id} className={card + " space-y-1"}>
          <div className="flex justify-between"><b>{d.kind === "TAKEOVER" ? "Takeover" : d.my_side === "SELL" ? "Sell" : "Buy"} {d.ticker}{d.qty ? ` ×${d.qty}` : " (all founder shares)"}</b><span className={`text-xs ${d.status === "OPEN" ? "text-gold" : d.status === "ACCEPTED" ? "text-up" : "text-mute"}`}>{d.status}</span></div>
          <div className="text-xs text-mute">with {d.other} · {inr(d.price)}/share · {d.mine ? "you offered" : "offered to you"}</div>
          {d.status === "OPEN" && <div className="flex gap-2 pt-1">
            {!d.mine && <button className="flex-1 bg-up text-black py-2 rounded-xl font-bold" onClick={() => run(`/deals/${d.id}/accept`)}>{t("Accept")}</button>}
            <button className="flex-1 bg-card2 text-mute py-2 rounded-xl font-semibold" onClick={() => run(`/deals/${d.id}/cancel`)}>{t("Cancel")}</button></div>}
        </div>))}
    </div>
  );
}

type Al = { id: number; ticker: string; target: string; direction: string; price: string };
export function AlertSheet({ ticker, price, onClose }: { ticker: string; price: string; onClose: () => void }) {
  const { t } = useT();
  const { data, reload } = useLoad<Al[]>("/alerts");
  const [v, setV] = useState(String((Number(price) * 1.05).toFixed(2)));
  const [msg, setMsg] = useState("");
  const add = async () => { setMsg(""); try { await api("/alerts", { ticker, target: v }); reload(); } catch (e) { setMsg((e as Error).message); } };
  const del = async (id: number) => { await api(`/alerts/${id}/delete`, {}); reload(); };
  return (
    <div className="fixed inset-0 bg-black/70 flex items-end z-30" onClick={onClose}>
      <div className="sheet glass border-t border-line w-full rounded-t-3xl p-5 space-y-3 max-w-md mx-auto" onClick={(e) => e.stopPropagation()}>
        <div className="w-10 h-1 rounded-full bg-line mx-auto" />
        <h2 className="font-bold text-lg">{t("Price alerts")} · {ticker}</h2>
        <div className="text-xs text-mute">Now {inr(price)}. You get a Telegram message when the price crosses your target.</div>
        <div className="flex gap-2"><input className={inp} type="number" step="0.01" value={v} onChange={(e) => setV(e.target.value)} /><button className="bg-acc text-white px-4 rounded-xl font-bold" onClick={add}>{t("Create")}</button></div>
        {msg && <div className="text-down text-sm">{msg}</div>}
        {(data ?? []).filter((a) => a.ticker === ticker).map((a) => (
          <div key={a.id} className="flex justify-between items-center bg-card2 rounded-xl px-3 py-2 text-sm"><span>{a.direction === "ABOVE" ? "≥" : "≤"} {inr(a.target)}</span><button className="text-down" onClick={() => del(a.id)}>{t("Delete")}</button></div>))}
      </div>
    </div>
  );
}

type Ord = { id: number; ticker: string; side: string; qty: number; limit: string; price: string; status: string; reason: string; fill: string | null; expires_at: string };
export function OrdersView({ onChange }: { onChange: () => void }) {
  const { data, reload } = useLoad<Ord[]>("/orders");
  const cancel = async (id: number) => { await api(`/orders/${id}/cancel`, {}); reload(); onChange(); };
  const colr: Record<string, string> = { OPEN: "text-gold", FILLED: "text-up", FAILED: "text-down" };
  return (
    <div className="space-y-2">
      <div className="text-xs text-mute px-1">Limit orders fill automatically when the price reaches your limit. Place one from any stock page → Buy/Sell → Limit.</div>
      {(data ?? []).map((o) => (
        <div key={o.id} className={card + " space-y-1"}>
          <div className="flex justify-between"><b><span className={o.side === "BUY" ? "text-up" : "text-down"}>{o.side}</span> {o.ticker} ×{o.qty}</b><span className={`text-xs font-semibold ${colr[o.status] ?? "text-mute"}`}>{o.status}</span></div>
          <div className="text-xs text-mute">Limit {inr(o.limit)} · now {inr(o.price)}{o.fill ? ` · filled @ ${inr(o.fill)}` : ""}{o.reason ? ` · ${o.reason}` : ""}</div>
          {o.status === "OPEN" && <button className="w-full bg-card2 text-mute py-1.5 rounded-xl text-sm font-semibold" onClick={() => cancel(o.id)}>Cancel order</button>}
        </div>))}
      {!data?.length && <div className="text-center text-mute py-10">No orders yet.</div>}
    </div>
  );
}
