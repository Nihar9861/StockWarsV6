declare global { interface Window { Telegram?: any } }
const tg = window.Telegram?.WebApp;
tg?.ready(); tg?.expand();
export async function api<T>(path: string, body?: unknown): Promise<T> {
  const r = await fetch("/api" + path, {
    method: body ? "POST" : "GET",
    headers: { "x-init-data": tg?.initData ?? "", "content-type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail ?? `Error ${r.status}`);
  return r.json();
}
export const inr = (x: number | string) => "₹" + Number(x).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
export const pct = (a: number, b: number) => (b ? (a / b - 1) * 100 : 0);
export const haptic = () => tg?.HapticFeedback?.impactOccurred("light");
