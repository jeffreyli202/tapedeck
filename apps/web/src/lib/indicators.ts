import type { Bar } from "./types";

const etParts = new Intl.DateTimeFormat("en-US", {
  timeZone: "America/New_York",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hour12: false,
});

/** Lightweight Charts renders timestamps as UTC; shift them so the axis shows New York wall-clock time. */
export function toChartTime(t: number): number {
  const p = Object.fromEntries(etParts.formatToParts(t * 1000).map((x) => [x.type, x.value]));
  const hour = p.hour === "24" ? 0 : +p.hour;
  return Date.UTC(+p.year, +p.month - 1, +p.day, hour, +p.minute, +p.second) / 1000;
}

export function etDay(t: number): string {
  return new Date(toChartTime(t) * 1000).toISOString().slice(0, 10);
}

/** Roll 1-minute bars up to `minutes`-wide bars. A forming bucket only ever contains completed minutes. */
export function aggregate(bars: Bar[], minutes: number): Bar[] {
  if (minutes <= 1) return bars;
  const width = minutes * 60;
  const out: Bar[] = [];
  let pv = 0;
  for (const b of bars) {
    const bucket = b.t - (b.t % width);
    const last = out[out.length - 1];
    const typical = b.vw ?? (b.h + b.l + b.c) / 3;
    if (last && last.t === bucket) {
      last.h = Math.max(last.h, b.h);
      last.l = Math.min(last.l, b.l);
      last.c = b.c;
      last.v += b.v;
      pv += typical * b.v;
      last.vw = last.v ? pv / last.v : last.c;
    } else {
      pv = typical * b.v;
      out.push({ t: bucket, o: b.o, h: b.h, l: b.l, c: b.c, v: b.v, vw: typical });
    }
  }
  return out;
}

export function ema(values: number[], period: number): (number | null)[] {
  const k = 2 / (period + 1);
  const out: (number | null)[] = [];
  let prev: number | null = null;
  let seed = 0;
  values.forEach((v, i) => {
    if (i < period - 1) {
      seed += v;
      out.push(null);
      return;
    }
    if (prev === null) {
      prev = (seed + v) / period;
    } else {
      prev = v * k + prev * (1 - k);
    }
    out.push(prev);
  });
  return out;
}

/** Session VWAP, resetting at each New York trading day. */
export function sessionVwap(bars: Bar[]): number[] {
  let day = "";
  let pv = 0;
  let vol = 0;
  return bars.map((b) => {
    const d = etDay(b.t);
    if (d !== day) {
      day = d;
      pv = 0;
      vol = 0;
    }
    const typical = b.vw ?? (b.h + b.l + b.c) / 3;
    const v = b.v || 1;
    pv += typical * v;
    vol += v;
    return pv / vol;
  });
}
