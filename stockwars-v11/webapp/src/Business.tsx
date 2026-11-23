import { useState } from "react";
import { api, inr, haptic } from "./api";
import { useLoad } from "./hooks";

const card = "bg-card border border-line rounded-2xl p-3.5 fade";
const inp = "w-full bg-card2 border border-line rounded-xl p-3 text-sm";
type Co = { id: number; name: string; ticker: string; price: string; total_shares: number; founder_shares: number; reputation: number; growth: number; cash: string; listing: string; status: string; valuation: string; age_h: number; ipo: { id: number; status: string } | null };
type Meta = { sectors: { id: number; name: string }[]; rules: Record<string, string | number>; upgrades: { key: string; name: string; cost: number; cooldown_h: number; rep: number; growth: number; risk: number }[] };
type Ipo = { id: number; ticker: string; name: string; status: string; price: string; public_shares: number; min_sub: number; max_sub: number; closes_at: string | null; allocated: number; mine: boolean; my_sub: number | null; my_alloc: number | null };

function useAct(done: () => void) {
  const [msg, setMsg] = useState(""); const [busy, setBusy] = useState(false);
  const run = async (path: string, body: object) => {
    setBusy(true); setMsg("");
    try { const r = await api<any>(path, { ...body, key: crypto.randomUUID() }); haptic(); done(); setMsg(r?.success === false ? "Upgrade failed — small effect only" : "✅ Done"); }
    catch (e) { setMsg("❌ " + (e as Error).message); } finally { setBusy(false); }
  };
  return { msg, busy, run };
}

function Create({ meta, done }: { meta: Meta; done: () => void }) {
  const [f, setF] = useState({ name: "", ticker: "", sector_id: meta.sectors[0]?.id ?? 1, description: "", capital: String(meta.rules.min_capital), total_shares: "100000" });
  const { msg, busy, run } = useAct(done);
  const set = (k: string) => (e: any) => setF({ ...f, [k]: e.target.value });
  return (
    <div className={card + " space-y-2"}>
      <b>Create company</b>
      <div className="text-xs text-mute">Fee {inr(String(meta.rules.company_fee))} + capital (min {inr(String(meta.rules.min_capital))}). You get all founder shares.</div>
      <input className={inp} placeholder="Company name" value={f.name} onChange={set("name")} />
      <input className={inp} placeholder="Ticker (3-5 letters)" value={f.ticker} onChange={(e) => setF({ ...f, ticker: e.target.value.toUpperCase() })} maxLength={5} />
      <select className={inp} value={f.sector_id} onChange={set("sector_id")}>{meta.sectors.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select>
      <input className={inp} placeholder="Description" value={f.description} onChange={set("description")} />
      <div className="grid grid-cols-2 gap-2"><input className={inp} type="number" placeholder="Capital" value={f.capital} onChange={set("capital")} /><input className={inp} type="number" placeholder="Total shares" value={f.total_shares} onChange={set("total_shares")} /></div>
      <button disabled={busy} className="w-full bg-acc py-2.5 rounded-xl font-semibold disabled:opacity-40" onClick={() => run("/company/create", { ...f, sector_id: Number(f.sector_id), capital: f.capital, total_shares: Number(f.total_shares) })}>Create</button>
      {msg && <div className="text-sm">{msg}</div>}
    </div>
  );
}

function IpoForm({ c, meta, done }: { c: Co; meta: Meta; done: () => void }) {
  const [f, setF] = useState({ public_shares: String(Math.floor(c.total_shares * 0.25)), price: c.price, duration_hours: "24", min_sub: "1", max_sub: "" });
  const { msg, busy, run } = useAct(done);
  const set = (k: string) => (e: any) => setF({ ...f, [k]: e.target.value });
  return (
    <div className="space-y-2 mt-2">
      <div className="text-xs text-mute">IPO fee {inr(String(meta.rules.ipo_fee))} · needs age ≥ {meta.rules.ipo_min_age_hours}h, reputation ≥ {meta.rules.ipo_min_reputation}, public ≤ {Number(meta.rules.ipo_max_public_pct) * 100}%</div>
      <div className="grid grid-cols-2 gap-2">
        <input className={inp} type="number" placeholder="Public shares" value={f.public_shares} onChange={set("public_shares")} />
        <input className={inp} type="number" placeholder="IPO price" value={f.price} onChange={set("price")} />
        <input className={inp} type="number" placeholder="Hours" value={f.duration_hours} onChange={set("duration_hours")} />
        <input className={inp} type="number" placeholder="Min / player" value={f.min_sub} onChange={set("min_sub")} />
        <input className={inp + " col-span-2"} type="number" placeholder="Max / player (default 20%)" value={f.max_sub} onChange={set("max_sub")} />
      </div>
      <button disabled={busy} className="w-full bg-up py-2.5 rounded-xl font-semibold disabled:opacity-40" onClick={() => run(`/company/${c.id}/ipo`, { public_shares: Number(f.public_shares), price: f.price, duration_hours: Number(f.duration_hours), min_sub: Number(f.min_sub), max_sub: f.max_sub ? Number(f.max_sub) : null })}>Launch IPO</button>
      {msg && <div className="text-sm">{msg}</div>}
    </div>
  );
}

function CompanyCard({ c, meta, done }: { c: Co; meta: Meta; done: () => void }) {
  const [open, setOpen] = useState(false);
  const { msg, busy, run } = useAct(done);
  return (
    <div className={card}>
      <div className="flex justify-between"><b>{c.ticker} · {c.name}</b><span className="text-xs text-mute">{c.listing}{c.ipo ? ` · IPO ${c.ipo.status}` : ""}</span></div>
      <div className="text-xs text-mute mt-1">Val {inr(c.valuation)} · Price {inr(c.price)} · Rep {c.reputation} · Growth {c.growth}% · Age {c.age_h}h<br />Founder holds {c.founder_shares.toLocaleString("en-IN")} / {c.total_shares.toLocaleString("en-IN")} · Cash {inr(c.cash)}</div>
      <button className="text-acc text-sm mt-2" onClick={() => setOpen(!open)}>{open ? "Hide" : "Manage"}</button>
      {open && <div className="mt-2 space-y-2">
        <div className="grid grid-cols-1 gap-1.5">{meta.upgrades.map((u) => (
          <button key={u.key} disabled={busy} onClick={() => run(`/company/${c.id}/upgrade`, { kind: u.key })} className="flex justify-between bg-bg border border-line rounded-xl px-3 py-2 text-sm disabled:opacity-40">
            <span>{u.name}</span><span className="text-mute">{inr(u.cost)} · {u.cooldown_h}h cd · risk {u.risk * 100}%</span></button>))}</div>
        {msg && <div className="text-sm">{msg}</div>}
        {c.listing === "LISTED" && <DivForm c={c} done={done} />}
        {c.listing === "PRIVATE" && !(c.ipo && ["OPEN", "PENDING"].includes(c.ipo.status)) && <IpoForm c={c} meta={meta} done={done} />}
      </div>}
    </div>
  );
}

function DivForm({ c, done }: { c: Co; done: () => void }) {
  const [v, setV] = useState("1");
  const { msg, busy, run } = useAct(done);
  return (
    <div className="space-y-2 mt-2">
      <div className="text-xs text-mute">Dividend per share · funded from company cash ({inr(c.cash)}), max 50% · record in 1h, paid 30m later · 1 per 24h</div>
      <div className="flex gap-2"><input className={inp} type="number" step="0.01" value={v} onChange={(e) => setV(e.target.value)} />
        <button disabled={busy} className="bg-up px-4 rounded-xl font-semibold disabled:opacity-40 whitespace-nowrap" onClick={() => run(`/company/${c.id}/dividend`, { per_share: v })}>Announce · {inr(Number(v) * c.total_shares)}</button></div>
      {msg && <div className="text-sm">{msg}</div>}
    </div>
  );
}

type LoanSt = { credit_score: number; max_amount: string; blocked: boolean; rate_per_day: string; late_fee_pct: string; debt: string; loan: { id: number; principal: string; outstanding: string; due_at: string; late: boolean } | null };
type Divs = { received: { ticker: string; shares: number; amount: string; paid: boolean }[]; upcoming: { ticker: string; per_share: string; pay_at: string; status: string }[] };

function Bank({ done }: { done: () => void }) {
  const { data: st, reload } = useLoad<LoanSt>("/loan");
  const { data: dv } = useLoad<Divs>("/dividends");
  const [amt, setAmt] = useState("100000"); const [days, setDays] = useState("7"); const [rep, setRep] = useState("");
  const { msg, busy, run } = useAct(() => { reload(); done(); });
  if (!st) return <div className="space-y-3"><div className="skel h-24" /><div className="skel h-40" /></div>;
  const interest = Number(amt) * Number(st.rate_per_day) * Number(days);
  return (
    <div className="space-y-3">
      <div className={card}><div className="flex justify-between"><b className="text-base">Bank</b><span className="text-sm">Credit score <b>{st.credit_score}</b></span></div>
        <div className="text-xs text-mute mt-1">Max loan {inr(st.max_amount)} · {(Number(st.rate_per_day) * 100).toFixed(1)}%/day · late fee {(Number(st.late_fee_pct) * 100)}% · default after 3 days overdue (cash seized, credit score hit)</div>
        {st.blocked && <div className="text-down text-sm mt-1">Defaulted debt outstanding — clear it to borrow again.</div>}</div>
      {st.loan ? (
        <div className={card + " space-y-2"}>
          <div>Outstanding <b>{inr(st.loan.outstanding)}</b> <span className="text-xs text-mute">of {inr(st.loan.principal)} principal</span></div>
          <div className="text-xs text-mute">Due {new Date(st.loan.due_at).toLocaleString()}{st.loan.late ? " · LATE FEE ADDED" : ""}</div>
          <div className="flex gap-2"><input className={inp} type="number" placeholder="Amount" value={rep} onChange={(e) => setRep(e.target.value)} />
            <button disabled={busy || !rep} className="bg-up px-4 rounded-xl font-semibold disabled:opacity-40" onClick={() => run("/loan/repay", { amount: rep })}>Repay</button>
            <button disabled={busy} className="bg-card border border-line px-3 rounded-xl" onClick={() => run("/loan/repay", { amount: st.loan!.outstanding })}>All</button></div>
        </div>
      ) : !st.blocked && (
        <div className={card + " space-y-2"}><b>Take a loan</b>
          <div className="grid grid-cols-2 gap-2"><input className={inp} type="number" value={amt} onChange={(e) => setAmt(e.target.value)} /><select className={inp} value={days} onChange={(e) => setDays(e.target.value)}>{[1, 3, 7, 14].map((d) => <option key={d} value={d}>{d} days</option>)}</select></div>
          <div className="text-xs text-mute">Repay {inr(Number(amt) + interest)} (interest {inr(interest)}). Debt reduces your net worth.</div>
          <button disabled={busy} className="w-full bg-acc py-2.5 rounded-xl font-semibold disabled:opacity-40" onClick={() => run("/loan/take", { amount: amt, days: Number(days) })}>Borrow</button></div>
      )}
      {msg && <div className="text-sm">{msg}</div>}
      <div className="font-semibold">Dividends</div>
      {dv?.upcoming.map((u, i) => <div key={i} className={card + " text-sm"}>{u.ticker} · {inr(u.per_share)}/share · {u.status} · pays {new Date(u.pay_at).toLocaleString()}</div>)}
      {dv?.received.map((r, i) => <div key={i} className={card + " text-sm flex justify-between"}><span>{r.ticker} ×{r.shares}</span><span className="text-up">{inr(r.amount)} {r.paid ? "✓" : "⏳"}</span></div>)}
      {dv && !dv.received.length && !dv.upcoming.length && <div className="text-center text-mute py-4">No dividends yet.</div>}
    </div>
  );
}

function IpoRow({ i, done }: { i: Ipo; done: () => void }) {
  const [n, setN] = useState(String(i.min_sub));
  const { msg, busy, run } = useAct(done);
  return (
    <div className={card + " space-y-1"}>
      <div className="flex justify-between"><b>{i.ticker}</b><span className="text-xs text-mute">{i.status}</span></div>
      <div className="text-xs text-mute">{i.name} · {inr(i.price)} · {i.public_shares.toLocaleString("en-IN")} shares · {i.min_sub}–{i.max_sub} per player{i.closes_at && i.status === "OPEN" ? ` · closes ${new Date(i.closes_at).toLocaleString()}` : ""}</div>
      {i.status === "CLOSED" && <div className="text-xs">Allocated {i.allocated.toLocaleString("en-IN")}{i.my_alloc != null ? ` · You got ${i.my_alloc}` : ""}</div>}
      {i.my_sub != null && i.status === "OPEN" && <div className="text-xs text-up">You subscribed for {i.my_sub} shares</div>}
      {i.status === "OPEN" && i.my_sub == null && !i.mine && (
        <div className="flex gap-2"><input className={inp} type="number" value={n} onChange={(e) => setN(e.target.value)} />
          <button disabled={busy} className="bg-up px-4 rounded-xl font-semibold disabled:opacity-40 whitespace-nowrap" onClick={() => run(`/ipo/${i.id}/subscribe`, { shares: Number(n) })}>Pay {inr(Number(n) * Number(i.price))}</button></div>)}
      {msg && <div className="text-sm">{msg}</div>}
    </div>
  );
}

export default function Business({ onChange }: { onChange: () => void }) {
  const [view, setView] = useState<"co" | "ipo" | "bank">("co");
  const { data: meta } = useLoad<Meta>("/sectors");
  const { data: cos, reload: rc } = useLoad<Co[]>("/business");
  const { data: ipos, reload: ri } = useLoad<Ipo[]>("/ipos");
  const done = () => { rc(); ri(); onChange(); };
  if (!meta || !cos) return <div className="space-y-3"><div className="skel h-24" /><div className="skel h-40" /></div>;
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-3 gap-1 p-1 bg-card border border-line rounded-2xl">{([["co", "My Companies"], ["ipo", "IPO Market"], ["bank", "Bank"]] as const).map(([k, l]) => (
        <button key={k} onClick={() => setView(k)} className={`py-2 rounded-xl text-sm font-semibold ${view === k ? "bg-acc text-white" : "text-mute"}`}>{l}</button>))}</div>
      {view === "bank" ? <Bank done={done} /> : view === "co" ? <>{cos.map((c) => <CompanyCard key={c.id} c={c} meta={meta} done={done} />)}<Create meta={meta} done={done} /></> :
        <>{(ipos ?? []).map((i) => <IpoRow key={i.id} i={i} done={done} />)}{ipos?.length === 0 && <div className="text-center text-mute py-8">No IPOs yet.</div>}</>}
    </div>
  );
}
