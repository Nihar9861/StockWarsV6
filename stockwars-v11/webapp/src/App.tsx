import { useState } from "react";
import { api, inr, pct, haptic } from "./api";
import { useLoad } from "./hooks";
import Business from "./Business";
import { Icon, Logo } from "./Icons";
import { useTheme } from "./theme";
import { useT } from "./i18n";
import Settings from "./Settings";
import Rewards from "./Rewards";
import { Perf, HistoryView, DealsView, AlertSheet, OrdersView } from "./Portfolio";
import Arena from "./Arena";
import Chart from "./Chart";

type Stock = { ticker: string; name: string; price: string; prev: string; risk: string };
type Mkt = { status: string; cycle: number; index: string; fee_pct: string; cycle_minutes: number; stocks: Stock[] };
type Holding = { ticker: string; qty: string; avg: string; price: string; value: string; pnl: string; pnl_pct: string };
type Me = { debt: string; cash: string; invested: string; market_value: string; unrealized: string; realized: string; net_worth: string; holdings: Holding[] };
type News = { id: number; headline: string; description: string; severity: string; impact: number; remaining: number; duration: number; status: string; scope: string[] };
type Row = { rank: number; name: string; net_worth: string; me: boolean };
type Pt = { price: string; cycle: number };

const card = "bg-card border border-line rounded-2xl p-3.5";
const col = (n: number) => (n >= 0 ? "text-up" : "text-down");
const hue = (t: string) => [...t].reduce((a, c) => a + c.charCodeAt(0) * 17, 0) % 360;

const Avatar = ({ t, size = 42 }: { t: string; size?: number }) => (
  <div style={{ width: size, height: size, background: `linear-gradient(135deg,hsl(${hue(t)} 70% 48%),hsl(${(hue(t) + 45) % 360} 70% 28%))` }} className="rounded-xl grid place-items-center text-[12px] font-bold shrink-0">{t.slice(0, 2)}</div>
);
const Chg = ({ v }: { v: number }) => (
  <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${v >= 0 ? "bg-up/15 text-up" : "bg-down/15 text-down"}`}>{v >= 0 ? "+" : ""}{v.toFixed(2)}%</span>
);
const Title = ({ children, right }: { children: React.ReactNode; right?: React.ReactNode }) => (
  <div className="flex justify-between items-center mt-5 mb-2 px-1"><h2 className="text-[15px] font-bold tracking-tight">{children}</h2>{right}</div>
);

const Skeleton = () => (
  <div className="p-3 space-y-3 max-w-md mx-auto">
    <div className="skel h-8 w-40" /><div className="skel h-36" /><div className="grid grid-cols-2 gap-3"><div className="skel h-20" /><div className="skel h-20" /></div>
    {[0, 1, 2, 3].map((i) => <div key={i} className="skel h-16" />)}
  </div>
);

function TradeSheet({ s, side, fee, held, onClose, onDone }: { s: Stock; side: "BUY" | "SELL"; fee: number; held: number; onClose: () => void; onDone: () => void }) {
  const [qty, setQty] = useState("1");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [key] = useState(() => crypto.randomUUID());
  const buy = side === "BUY";
  const [mode, setMode] = useState<"market" | "limit">("market");
  const [lp, setLp] = useState((Number(s.price) * (buy ? 0.97 : 1.03)).toFixed(2));
  const [days, setDays] = useState("1");
  const px = mode === "limit" ? Number(lp) || 0 : Number(s.price);
  const q = Math.max(0, parseInt(qty) || 0), val = q * px, f = val * fee;
  const go = async () => {
    setBusy(true); setMsg("");
    try {
      if (mode === "limit") await api("/orders", { ticker: s.ticker, side, qty: q, price: lp, days: Number(days) });
      else await api("/trade", { ticker: s.ticker, side, qty: q, key });
      haptic(); onDone(); onClose();
    }
    catch (e) { setMsg((e as Error).message); setBusy(false); }
  };
  return (
    <div className="fixed inset-0 bg-black/70 flex items-end z-30" onClick={onClose}>
      <div className="sheet glass border-t border-line w-full rounded-t-3xl p-5 space-y-4 max-w-md mx-auto" onClick={(e) => e.stopPropagation()}>
        <div className="w-10 h-1 rounded-full bg-line mx-auto" />
        <div className="flex items-center gap-3"><Avatar t={s.ticker} /><div><div className="font-bold">{buy ? "Buy" : "Sell"} {s.ticker}</div><div className="text-xs text-mute">Market price {inr(s.price)}</div></div></div>
        <div className="grid grid-cols-2 gap-1 p-1 bg-card2 rounded-xl">{(["market", "limit"] as const).map((m) => <button key={m} onClick={() => setMode(m)} className={`py-1.5 rounded-lg text-sm font-semibold ${mode === m ? "bg-acc text-white" : "text-mute"}`}>{m === "market" ? "Market" : "Limit"}</button>)}</div>
        {mode === "limit" && <div className="space-y-2">
          <div className="grid grid-cols-2 gap-2"><div><div className="text-[11px] text-mute mb-1">{buy ? "Buy when price ≤" : "Sell when price ≥"}</div><input type="number" step="0.01" value={lp} onChange={(e) => setLp(e.target.value)} className="w-full bg-card2 border border-line rounded-xl p-2.5 font-bold" /></div>
            <div><div className="text-[11px] text-mute mb-1">Valid for</div><select value={days} onChange={(e) => setDays(e.target.value)} className="w-full bg-card2 border border-line rounded-xl p-2.5">{[1, 2, 3, 7].map((d) => <option key={d} value={d}>{d} day{d > 1 ? "s" : ""}</option>)}</select></div></div>
          <div className="text-[11px] text-mute">Now {inr(s.price)}. The order fills automatically when the price reaches your limit — even if you are away. You get a Telegram message.</div></div>}
        <div className="flex items-center gap-2">
          <button className="w-12 h-12 rounded-xl bg-card2 text-xl" onClick={() => setQty(String(Math.max(1, q - 1)))}>−</button>
          <input type="number" min={1} value={qty} onChange={(e) => setQty(e.target.value)} className="flex-1 text-center bg-card2 border border-line rounded-xl h-12 text-xl font-bold" />
          <button className="w-12 h-12 rounded-xl bg-card2 text-xl" onClick={() => setQty(String(q + 1))}>+</button>
        </div>
        <div className="flex gap-2">{[10, 100, 1000].map((n) => <button key={n} className="flex-1 py-1.5 rounded-lg bg-card2 text-sm text-mute" onClick={() => setQty(String(n))}>{n}</button>)}
          {!buy && <button className="flex-1 py-1.5 rounded-lg bg-acc/20 text-acc text-sm" onClick={() => setQty(String(held))}>Max</button>}</div>
        <div className="bg-card2 rounded-xl p-3 text-sm space-y-1">
          <div className="flex justify-between text-mute"><span>Value</span><span>{inr(val)}</span></div>
          <div className="flex justify-between text-mute"><span>Fee ({(fee * 100).toFixed(2)}%)</span><span>{inr(f)}</span></div>
          <div className="flex justify-between font-bold text-base pt-1 border-t border-line"><span>{buy ? "Total" : "You receive"}</span><span>{inr(buy ? val + f : val - f)}</span></div>
        </div>
        {msg && <div className="text-down text-sm">{msg}</div>}
        <button disabled={busy || q < 1} onClick={go} className={`w-full py-3.5 rounded-xl font-bold text-black disabled:opacity-40 ${buy ? "bg-up text-black" : "bg-down text-white"}`}>{busy ? "Placing order…" : mode === "limit" ? "Place limit order" : `Confirm ${buy ? "Buy" : "Sell"}`}</button>
      </div>
    </div>
  );
}

function StockPage({ s, mkt, me, back, refresh, watching, onWatch }: { s: Stock; mkt: Mkt; me: Me | null; back: () => void; refresh: () => void; watching: boolean; onWatch: () => void }) {
  const { t } = useT();
  const [alertOpen, setAlertOpen] = useState(false);
  const { data: hist } = useLoad<Pt[]>(`/stock/${s.ticker}/history`);
  const [side, setSide] = useState<"BUY" | "SELL" | null>(null);
  const h = me?.holdings.find((x) => x.ticker === s.ticker);
  const open = mkt.status === "OPEN", ch = pct(Number(s.price), Number(s.prev));
  const v = (hist ?? []).map((p) => Number(p.price));
  return (
    <div className="space-y-3 fade">
      <button onClick={back} className="flex items-center gap-1 text-mute text-sm"><Icon n="back" size={18} /> {t("Back")}</button>
      <div className="flex items-center gap-3"><Avatar t={s.ticker} size={48} /><div><div className="font-bold text-lg leading-tight">{s.ticker}</div><div className="text-xs text-mute">{s.name}</div></div>
        <span className="ml-auto text-xs px-2 py-1 rounded-full bg-card2 text-mute">Risk {s.risk}</span>
        <button onClick={onWatch} aria-label="Watchlist" className={`w-9 h-9 rounded-full grid place-items-center border border-line ${watching ? "bg-gold/20 text-gold" : "bg-card text-mute"}`}><Icon n="star" size={17} /></button>
        <button onClick={() => setAlertOpen(true)} aria-label="Alert" className="w-9 h-9 rounded-full grid place-items-center border border-line bg-card text-mute"><Icon n="bell" size={17} /></button></div>
      <div className={card}>
        <div className="flex items-end gap-3"><div className="text-3xl font-extrabold tracking-tight">{inr(s.price)}</div><Chg v={ch} /></div>
        <Chart pts={hist ?? []} cycleMin={mkt.cycle_minutes} />
        {v.length > 1 && <div className="flex justify-between text-xs text-mute mt-2"><span>Low {inr(Math.min(...v))}</span><span>{v.length} cycles</span><span>High {inr(Math.max(...v))}</span></div>}
      </div>
      {h && <div className={card + " grid grid-cols-3 text-center"}>
        <div><div className="text-xs text-mute">Holding</div><b>{h.qty}</b></div>
        <div><div className="text-xs text-mute">Avg price</div><b>{inr(h.avg)}</b></div>
        <div><div className="text-xs text-mute">P/L</div><b className={col(Number(h.pnl))}>{inr(h.pnl)}</b></div></div>}
      {!open && <div className="text-center text-sm text-gold bg-gold/10 rounded-xl py-2">Market is {mkt.status} — trading disabled</div>}
      <div className="grid grid-cols-2 gap-3">
        <button disabled={!open} onClick={() => setSide("BUY")} className="bg-up text-black py-3.5 rounded-xl font-bold disabled:opacity-30">{t("Buy")}</button>
        <button disabled={!open || !h} onClick={() => setSide("SELL")} className="bg-down text-white py-3.5 rounded-xl font-bold disabled:opacity-30">{t("Sell")}</button>
      </div>
      {alertOpen && <AlertSheet ticker={s.ticker} price={s.price} onClose={() => setAlertOpen(false)} />}
      {side && <TradeSheet s={s} side={side} fee={Number(mkt.fee_pct)} held={Number(h?.qty ?? 0)} onClose={() => setSide(null)} onDone={refresh} />}
    </div>
  );
}

const sev: Record<string, string> = { NORMAL: "bg-acc/15 text-acc", STRONG: "bg-gold/15 text-gold", EXCEPTIONAL: "bg-down/15 text-down" };
const NewsItem = ({ n }: { n: News }) => (
  <div className={card + " fade"}>
    <div className="flex justify-between items-center"><span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${sev[n.severity] ?? sev.NORMAL}`}>{n.severity}</span>
      <span className={`text-[10px] ${n.status === "ACTIVE" ? "text-up" : "text-mute"}`}>{n.status}</span></div>
    <div className="font-bold mt-2">{n.headline}</div>
    <div className="text-sm text-mute mt-0.5">{n.description}</div>
    <div className="flex gap-2 mt-2 text-xs"><span className={`font-semibold ${col(n.impact)}`}>{n.impact >= 0 ? "+" : ""}{(n.impact * 100).toFixed(2)}% / cycle</span><span className="text-mute">{n.remaining}/{n.duration} cycles</span><span className="text-mute truncate">{n.scope.join(", ")}</span></div>
  </div>
);

export default function App() {
  const { pref, setPref } = useTheme();
  const { t } = useT();
  const [showSet, setShowSet] = useState(false);
  const [pf, setPf] = useState("hold");
  const [rk, setRk] = useState("board");
  const [tab, setTab] = useState("home");
  const [sel, setSel] = useState<Stock | null>(null);
  const [q, setQ] = useState("");
  const { data: mkt, err, reload: rm } = useLoad<Mkt>("/market");
  const { data: me, err: meErr, reload: rme } = useLoad<Me>("/me");
  const { data: news } = useLoad<News[]>("/news");
  const { data: board } = useLoad<Row[]>("/leaderboard");
  const { data: wl, reload: rw } = useLoad<string[]>("/watchlist");
  const toggleWatch = async (tk: string) => { try { await api("/watchlist/" + tk, {}); rw(); } catch { /* ignore */ } };
  const refresh = () => { rm(); rme(); };
  if (meErr) return <div className="p-10 text-center space-y-3"><div className="mx-auto w-fit"><Logo /></div><div className="font-bold">Waiting for approval</div><div className="text-sm text-mute">{meErr}<br />Register in the bot and wait for an admin to approve you.</div></div>;
  if (!mkt || !me) return err ? <div className="p-8 text-center text-mute">{err}</div> : <Skeleton />;
  const chg = (s: Stock) => pct(Number(s.price), Number(s.prev));
  const mv = [...mkt.stocks].sort((a, b) => chg(b) - chg(a));
  const open = mkt.status === "OPEN";
  const Row = ({ s }: { s: Stock }) => (
    <button onClick={() => setSel(s)} className={card + " w-full flex items-center gap-3 text-left fade"}>
      <Avatar t={s.ticker} />
      <div className="min-w-0 flex-1"><div className="font-bold leading-tight">{s.ticker}</div><div className="text-xs text-mute truncate">{s.name}</div></div>
      <div className="text-right"><div className="font-semibold">{inr(s.price)}</div><Chg v={chg(s)} /></div>
    </button>
  );
  const nw = Number(me.net_worth), pnl = Number(me.unrealized) + Number(me.realized);
  const segs = me.holdings.map((h) => ({ t: h.ticker, v: Number(h.value) }));
  const tot = Number(me.cash) + segs.reduce((a, x) => a + x.v, 0) || 1;
const Seg = ({ items, val, set }: { items: [string, string][]; val: string; set: (v: string) => void }) => (
    <div className={`grid gap-1 p-1 bg-card border border-line rounded-2xl`} style={{ gridTemplateColumns: `repeat(${items.length},1fr)` }}>
      {items.map(([k, l]) => <button key={k} onClick={() => set(k)} className={`py-2 rounded-xl text-sm font-semibold ${val === k ? "bg-acc text-white" : "text-mute"}`}>{l}</button>)}</div>);
  let body;
  if (sel) body = <StockPage s={mkt.stocks.find((x) => x.ticker === sel.ticker) ?? sel} mkt={mkt} me={me} back={() => setSel(null)} refresh={refresh} watching={wl?.includes(sel.ticker) ?? false} onWatch={() => toggleWatch(sel.ticker)} />;
  else if (tab === "home") body = (
    <div className="fade">
      <div className="rounded-3xl p-5 relative overflow-hidden" style={{ background: "linear-gradient(135deg,#1c3a8a 0%,#2a5bd7 45%,#10a370 120%)" }}>
        <div className="text-xs text-white/70">{t("Total net worth")}</div>
        <div className="text-[32px] font-extrabold tracking-tight leading-tight">{inr(nw)}</div>
        <div className="mt-1 text-sm"><span className={`px-2 py-0.5 rounded-full font-semibold ${pnl >= 0 ? "bg-white/20" : "bg-black/30"}`}>{pnl >= 0 ? "+" : ""}{inr(pnl)} P/L</span></div>
        <div className="grid grid-cols-2 gap-3 mt-4 text-sm"><div><div className="text-white/60 text-xs">{t("Cash")}</div><b>{inr(me.cash)}</b></div><div><div className="text-white/60 text-xs">{t("Invested")}</div><b>{inr(me.market_value)}</b></div></div>
        {Number(me.debt) > 0 && <div className="mt-2 text-xs bg-black/25 rounded-lg px-2 py-1 w-fit">Debt {inr(me.debt)}</div>}
      </div>
      <div className="grid grid-cols-2 gap-3 mt-3">
        <div className={card}><div className="text-xs text-mute">STOCK WARS INDEX</div><div className="text-xl font-extrabold">{mkt.index}</div></div>
        <div className={card}><div className="text-xs text-mute">Cycle {mkt.cycle}</div><div className={`text-lg font-extrabold ${open ? "text-up" : "text-gold"}`}>{mkt.status}</div></div>
      </div>
      {(wl?.length ?? 0) > 0 && <><Title>{t("Watchlist")}</Title><div className="space-y-2">{mkt.stocks.filter((x) => wl!.includes(x.ticker)).map((x) => <Row key={x.ticker} s={x} />)}</div></>}
      <Title>{t("Top gainers")}</Title><div className="space-y-2">{mv.slice(0, 3).map((s) => <Row key={s.ticker} s={s} />)}</div>
      <Title>{t("Top losers")}</Title><div className="space-y-2">{mv.slice(-3).reverse().map((s) => <Row key={s.ticker} s={s} />)}</div>
      <Title right={<button className="text-xs text-acc" onClick={() => setTab("news")}>{t("See all")}</button>}>{t("Latest news")}</Title>
      <div className="space-y-2">{(news ?? []).slice(0, 2).map((n) => <NewsItem key={n.id} n={n} />)}{news?.length === 0 && <div className="text-sm text-mute px-1">No news yet.</div>}</div>
    </div>
  );
  else if (tab === "market") body = (
    <div className="space-y-2 fade">
      <div className="relative"><span className="absolute left-3 top-3 text-mute"><Icon n="search" size={18} /></span>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("Search stocks")} className="w-full bg-card border border-line rounded-2xl py-3 pl-10 pr-3" /></div>
      {mkt.stocks.filter((s) => (s.ticker + s.name).toLowerCase().includes(q.toLowerCase())).map((s) => <Row key={s.ticker} s={s} />)}
    </div>
  );
  else if (tab === "portfolio") body = (
    <div className="space-y-3 fade">
      <Seg items={[["hold", t("Holdings")], ["orders", "Orders"], ["hist", t("History")], ["deals", t("Deals")]]} val={pf} set={setPf} />
      {pf === "orders" ? <OrdersView onChange={refresh} /> : pf === "hist" ? <HistoryView /> : pf === "deals" ? <DealsView tickers={mkt.stocks.map((x) => x.ticker)} onChange={refresh} /> : <>
      <Perf />
      <div className={card}>
        <div className="text-xs text-mute">{t("Portfolio value")}</div><div className="text-2xl font-extrabold">{inr(me.market_value)}</div>
        <div className="flex h-2.5 rounded-full overflow-hidden mt-3 bg-card2">
          {segs.map((x) => <div key={x.t} style={{ width: `${(x.v / tot) * 100}%`, background: `hsl(${hue(x.t)} 70% 50%)` }} />)}
          <div style={{ width: `${(Number(me.cash) / tot) * 100}%` }} className="bg-gray-600" />
        </div>
        <div className="flex flex-wrap gap-x-3 gap-y-1 mt-2 text-xs text-mute">{segs.map((x) => <span key={x.t}><i className="inline-block w-2 h-2 rounded-full mr-1" style={{ background: `hsl(${hue(x.t)} 70% 50%)` }} />{x.t}</span>)}<span><i className="inline-block w-2 h-2 rounded-full mr-1 bg-gray-600" />Cash</span></div>
        <div className="grid grid-cols-3 gap-2 mt-3 text-center text-sm">
          <div><div className="text-xs text-mute">Invested</div><b>{inr(me.invested)}</b></div>
          <div><div className="text-xs text-mute">Unrealized</div><b className={col(Number(me.unrealized))}>{inr(me.unrealized)}</b></div>
          <div><div className="text-xs text-mute">Realized</div><b className={col(Number(me.realized))}>{inr(me.realized)}</b></div></div>
      </div>
      {me.holdings.length === 0 && <div className="text-center text-mute py-10">No holdings yet.<br /><button className="text-acc mt-2" onClick={() => setTab("market")}>Browse market</button></div>}
      {me.holdings.map((h) => (
        <button key={h.ticker} onClick={() => setSel(mkt.stocks.find((s) => s.ticker === h.ticker)!)} className={card + " w-full flex items-center gap-3 text-left"}>
          <Avatar t={h.ticker} />
          <div className="flex-1"><div className="font-bold">{h.ticker} <span className="text-xs text-mute font-normal">×{h.qty}</span></div><div className="text-xs text-mute">avg {inr(h.avg)}</div></div>
          <div className="text-right"><div className="font-semibold">{inr(h.value)}</div><div className={`text-xs ${col(Number(h.pnl))}`}>{inr(h.pnl)} ({Number(h.pnl_pct).toFixed(1)}%)</div></div>
        </button>))}
      </>}
    </div>
  );
  else if (tab === "business") body = <Business onChange={refresh} />;
  else if (tab === "arena") body = <Arena stocks={mkt.stocks} status={mkt.status} onChange={refresh} />;
  else if (tab === "news") body = <div className="space-y-2">{(news ?? []).map((n) => <NewsItem key={n.id} n={n} />)}{news?.length === 0 && <div className="text-center text-mute py-10">No news yet.</div>}</div>;
  else {
    const medal = ["#f5b94a", "#b8c2d1", "#c8814a"];
    body = <div className="space-y-2 fade"><Seg items={[["board", t("Leaderboard")], ["rew", t("Rewards")]]} val={rk} set={setRk} />{rk === "rew" ? <Rewards onChange={refresh} /> : (board ?? []).map((r) => (
      <div key={r.rank} className={card + " flex items-center gap-3 " + (r.me ? "border-acc bg-acc/10" : "")}>
        <div className="w-8 h-8 rounded-full grid place-items-center font-extrabold text-sm" style={r.rank <= 3 ? { background: medal[r.rank - 1], color: "#000" } : { background: "rgb(var(--line))" }}>{r.rank}</div>
        <div className="flex-1 font-semibold truncate">{r.name}{r.me && <span className="text-acc text-xs ml-1">you</span>}</div><b>{inr(r.net_worth)}</b></div>))}</div>;
  }
  const tabs = [["home", "home", "Home"], ["market", "chart", "Market"], ["portfolio", "pie", "Portfolio"], ["arena", "swords", "Arena"], ["business", "build", "Business"], ["news", "news", "News"], ["board", "trophy", "Ranks"]];
  return (
    <div className="min-h-screen pb-28 px-3 max-w-md mx-auto">
      <header className="flex items-center gap-2.5 py-3">
        <Logo /><div className="font-extrabold tracking-tight leading-tight">STOCK<span className="text-acc">WARS</span></div>
        <button onClick={() => setShowSet(true)} aria-label="Settings" className="ml-auto w-9 h-9 rounded-full bg-card border border-line grid place-items-center text-mute"><Icon n="gear" size={18} /></button>
        <div className="flex items-center gap-2 text-xs font-semibold px-2.5 py-1 rounded-full bg-card border border-line">
          <span className="relative flex w-2 h-2"><span className={`absolute inset-0 rounded-full ${open ? "bg-up" : "bg-gold"}`} style={{ animation: open ? "ping2 1.6s infinite" : "none" }} /><span className={`relative w-2 h-2 rounded-full ${open ? "bg-up" : "bg-gold"}`} /></span>{mkt.status}</div>
      </header>
      {body}
      {showSet && <Settings pref={pref} setPref={setPref} onClose={() => setShowSet(false)} />}
      <nav className="fixed bottom-3 inset-x-3 max-w-md mx-auto glass border border-line rounded-3xl flex justify-around py-2 px-1 z-20 shadow-2xl" style={{ marginBottom: "env(safe-area-inset-bottom)" }}>
        {tabs.map(([k, ic, l]) => { const on = tab === k && !sel; return (
          <button key={k} onClick={() => { setSel(null); setTab(k); haptic(); }} className={`flex flex-col items-center gap-0.5 px-1.5 py-1.5 rounded-2xl text-[9.5px] font-semibold ${on ? "text-acc bg-acc/15" : "text-mute"}`}>
            <Icon n={ic} size={21} w={on ? 2.2 : 1.7} />{t(l)}</button>); })}
      </nav>
    </div>
  );
}
