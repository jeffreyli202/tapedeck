import { describe, expect, it } from "vitest";

import { describeSymbol } from "./format";
import { aggregate, ema, etDay, sessionVwap, toChartTime } from "./indicators";
import type { Bar } from "./types";

// 2024-03-15 09:30 America/New_York (EDT, UTC-4)
const OPEN = Date.UTC(2024, 2, 15, 13, 30) / 1000;
const bar = (i: number, o: number, h: number, l: number, c: number, v = 100): Bar => ({
  t: OPEN + i * 60,
  o,
  h,
  l,
  c,
  v,
  vw: null,
});

describe("toChartTime", () => {
  it("shifts UTC to New York wall clock", () => {
    expect(toChartTime(OPEN)).toBe(Date.UTC(2024, 2, 15, 9, 30) / 1000);
    expect(etDay(OPEN)).toBe("2024-03-15");
  });
});

describe("aggregate", () => {
  it("rolls minutes into 5-minute buckets aligned to the open", () => {
    const bars = [bar(0, 10, 11, 9, 10.5), bar(1, 10.5, 12, 10, 11), bar(4, 11, 11.5, 8, 9), bar(5, 9, 9.5, 8.5, 9.2)];
    const out = aggregate(bars, 5);
    expect(out).toHaveLength(2);
    expect(out[0]).toMatchObject({ t: OPEN, o: 10, h: 12, l: 8, c: 9, v: 300 });
    expect(out[1]).toMatchObject({ t: OPEN + 300, o: 9, c: 9.2 });
  });

  it("does not mutate the input", () => {
    const bars = [bar(0, 1, 2, 0.5, 1.5), bar(1, 1.5, 3, 1, 2)];
    aggregate(bars, 5);
    expect(bars[0].h).toBe(2);
  });
});

describe("indicators", () => {
  it("seeds EMA with an SMA", () => {
    const out = ema([1, 2, 3, 4], 3);
    expect(out.slice(0, 2)).toEqual([null, null]);
    expect(out[2]).toBe(2);
    expect(out[3]).toBeCloseTo(3);
  });

  it("resets VWAP each day", () => {
    const nextDay = { ...bar(0, 50, 50, 50, 50), t: OPEN + 86400 };
    const vw = sessionVwap([bar(0, 10, 10, 10, 10), bar(1, 20, 20, 20, 20), nextDay]);
    expect(vw[1]).toBe(15);
    expect(vw[2]).toBe(50);
  });
});

describe("describeSymbol", () => {
  it("formats OCC symbols", () => {
    expect(describeSymbol("SPY240315C00512500")).toBe("SPY Mar 15 512.5 C");
    expect(describeSymbol("SPY")).toBe("SPY");
  });
});
