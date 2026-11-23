import { useState } from "react";
import { inr } from "./api";

type Pt = { price: string; cycle: number };
type C = { o: number; h: number; l: number; c: number };
const UP = "#19c37d", DOWN = "#ff4d5e";

export function Line({ p }: { p: number[] }) {
  const mn = Math.min(...p), mx = Math.max(...p), r = mx - mn || 1;
  const xy = p.map((y, i) => [(i / (p.length - 1)) * 300, 8 + (1 - (y - mn) / r) * 84]);
  const line = xy.map((q) => q.join(",")).join(" "), c = p[p.length - 1] >= p[0] ? UP : DOWN, last = xy[xy.length - 1];
  return (
    <svg viewBox="0 0 300 110" className="w-full h-48" preserveAspectRatio="none">
      <defs><linearGradient id="lg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor={c} stopOpacity=".35" /><stop offset="1" stopColor={c} stopOpacity="0" /></linearGradient></defs>
      <polygon fill="url(#lg)" points={`0,110 ${line} 300,110`} />
      <polyline fill="none" stroke={c} strokeWidth="1.8" strokeLinejoin="round" points={line} vectorEffect="non-scaling-stroke" />
      <circle cx={last[0]} cy={last[1]} r="3" fill={c} />
    </svg>
  );
}

function Candles({ cs, sel, setSel }: { cs: C[]; sel: number | null; setSel: (i: number | null) => void }) {
  const W = 330, AX = 48, CW = W - AX, H = 190, PAD = 10;
  const hi = Math.max(...cs.map((x) => x.h)), lo = Math.min(...cs.map((x) => x.l)), pad = (hi - lo || hi * 0.01) * 0.08;
  const mx = hi + pad, mn = lo - pad, y = (v: number) => PAD + (1 - (v - mn) / (mx - mn)) * (H - 2 * PAD);
  const step = CW / cs.length, bw = Math.max(2, Math.min(14, step * 0.68));
  const last = cs[cs.length - 1], lc = last.c >= last.o ? UP : DOWN;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" onClick={() => setSel(null)}>
      {[0, 1, 2, 3, 4].map((i) => { const v = mn + ((mx - mn) * i) / 4, yy = y(v); return (
        <g key={i}><line x1="0" x2={CW} y1={yy} y2={yy} style={{ stroke: "rgb(var(--line))" }} strokeWidth=".6" strokeDasharray="2 3" />
          <text x={CW + 4} y={yy + 3} fontSize="8.5" style={{ fill: "rgb(var(--mute))" }}>{v.toFixed(2)}</text></g>); })}
      {cs.map((k, i) => {
        const up = k.c >= k.o, col = up ? UP : DOWN, cx = i * step + step / 2, top = y(Math.max(k.o, k.c)), bh = Math.max(1.4, Math.abs(y(k.o) - y(k.c)));
        return (
          <g key={i} onClick={(e) => { e.stopPropagation(); setSel(i); }} opacity={sel === null || sel === i ? 1 : 0.45}>
            <line x1={cx} x2={cx} y1={y(k.h)} y2={y(k.l)} stroke={col} strokeWidth="1.2" />
            <rect x={cx - bw / 2} y={top} width={bw} height={bh} fill={col} rx="1" />
            <rect x={cx - step / 2} y="0" width={step} height={H} fill="transparent" />
          </g>);
      })}
      <line x1="0" x2={CW} y1={y(last.c)} y2={y(last.c)} stroke={lc} strokeWidth=".8" strokeDasharray="3 3" />
      <rect x={CW + 1} y={y(last.c) - 8} width={AX - 2} height="16" rx="3" fill={lc} />
      <text x={CW + 4} y={y(last.c) + 3.5} fontSize="9" fontWeight="700" fill="#000">{last.c.toFixed(2)}</text>
    </svg>
  );
}

export default function Chart({ pts, cycleMin }: { pts: Pt[]; cycleMin: number }) {
  const [mode, setMode] = useState<"candle" | "line">("candle");
  const [k, setK] = useState(1);
  const [sel, setSel] = useState<number | null>(null);
  const p = pts.map((x) => Number(x.price));
  if (p.length < 2) return <div className="h-48 grid place-items-center text-sm text-mute text-center px-6">Chart appears after a few market cycles</div>;
  const all: C[] = [];
  for (let i = 0; i < p.length; i += k) {
    const g = p.slice(i, i + k), o = i > 0 ? p[i - 1] : g[0];
    all.push({ o, c: g[g.length - 1], h: Math.max(o, ...g), l: Math.min(o, ...g) });
  }
  const cs = all.slice(-48), cur = cs[sel ?? cs.length - 1], chg = cur.o ? (cur.c / cur.o - 1) * 100 : 0;
  const tf = (n: number) => { const m = n * cycleMin; return m >= 60 ? `${m / 60}h` : `${m}m`; };
  const btn = (on: boolean) => `px-2.5 py-1 rounded-lg text-xs font-semibold ${on ? "bg-acc text-white" : "bg-card2 text-mute"}`;
  return (
    <div className="mt-3">
      <div className="flex items-center justify-between mb-2">
        <div className="flex gap-1.5">{[1, 3, 6, 12].map((n) => <button key={n} className={btn(k === n && mode === "candle")} onClick={() => { setMode("candle"); setK(n); setSel(null); }}>{tf(n)}</button>)}</div>
        <button className={btn(mode === "line")} onClick={() => setMode(mode === "line" ? "candle" : "line")}>Line</button>
      </div>
      {mode === "candle" && <div className="text-[11px] flex flex-wrap gap-x-3 gap-y-0.5 text-mute mb-1">
        <span>O <b className="text-ink">{cur.o.toFixed(2)}</b></span><span>H <b className="text-ink">{cur.h.toFixed(2)}</b></span>
        <span>L <b className="text-ink">{cur.l.toFixed(2)}</b></span><span>C <b className="text-ink">{cur.c.toFixed(2)}</b></span>
        <b className={chg >= 0 ? "text-up" : "text-down"}>{chg >= 0 ? "+" : ""}{chg.toFixed(2)}%</b></div>}
      {mode === "candle" ? <Candles cs={cs} sel={sel} setSel={setSel} /> : <Line p={p} />}
      <div className="text-[10px] text-mute mt-1">{mode === "candle" ? `Each candle = ${tf(k)} · tap a candle for details` : `${p.length} cycles`}</div>
    </div>
  );
}
