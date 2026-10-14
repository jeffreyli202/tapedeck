const ET = "America/New_York";

const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });
const timeFmt = new Intl.DateTimeFormat("en-US", { timeZone: ET, hour: "2-digit", minute: "2-digit", hour12: false });
const dateTimeFmt = new Intl.DateTimeFormat("en-US", {
  timeZone: ET,
  month: "short",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});
const dateFmt = new Intl.DateTimeFormat("en-US", { timeZone: ET, weekday: "short", month: "short", day: "numeric", year: "numeric" });

export const money = (v: number | null | undefined) => (v == null ? "—" : usd.format(v));
export const signedMoney = (v: number | null | undefined) => (v == null ? "—" : `${v >= 0 ? "+" : ""}${usd.format(v)}`);
export const pct = (v: number | null | undefined, digits = 2) => (v == null ? "—" : `${(v * 100).toFixed(digits)}%`);
export const num = (v: number | null | undefined, digits = 2) => (v == null ? "—" : v.toFixed(digits));
export const etTime = (t: number) => timeFmt.format(t * 1000);
export const etDateTime = (t: number) => dateTimeFmt.format(t * 1000);
export const etDate = (t: number) => dateFmt.format(t * 1000);

export function duration(seconds: number): string {
  if (seconds <= 0) return "—";
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (d) return `${d}d ${h}h`;
  if (h) return `${h}h ${m}m`;
  return `${m}m`;
}

export const pnlClass = (v: number | null | undefined) =>
  v == null || v === 0 ? "text-muted" : v > 0 ? "text-up" : "text-down";

/** "SPY240315C00500000" -> "SPY Mar 15 500 C" */
export function describeSymbol(symbol: string): string {
  const m = symbol.match(/^([A-Z]+)(\d{2})(\d{2})(\d{2})([CP])(\d{8})$/);
  if (!m) return symbol;
  const [, root, yy, mm, dd, right, strike] = m;
  const month = new Date(Date.UTC(2000 + +yy, +mm - 1, +dd)).toLocaleString("en-US", { month: "short", timeZone: "UTC" });
  return `${root} ${month} ${+dd} ${+strike / 1000} ${right}`;
}
