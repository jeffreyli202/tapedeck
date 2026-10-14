"use client";

import {
  CandlestickSeries,
  ColorType,
  CrosshairMode,
  HistogramSeries,
  LineSeries,
  createChart,
  createSeriesMarkers,
  type IChartApi,
  type IPriceLine,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type SeriesMarker,
  type Time,
  type UTCTimestamp,
} from "lightweight-charts";
import { forwardRef, useEffect, useImperativeHandle, useMemo, useRef } from "react";

import { describeSymbol } from "@/lib/format";
import { aggregate, ema, sessionVwap, toChartTime } from "@/lib/indicators";
import type { Bar, Fill, Order, Position } from "@/lib/types";

const UP = "#26a69a";
const DOWN = "#ef5350";

export type ChartHandle = { screenshot: () => string | null };

type Props = {
  bars: Bar[];
  epoch: number;
  timeframe: number;
  symbol: string;
  fills: Fill[];
  orders: Order[];
  positions: Position[];
};

const ts = (t: number) => toChartTime(t) as UTCTimestamp;

export const ReplayChart = forwardRef<ChartHandle, Props>(function ReplayChart(
  { bars, epoch, timeframe, symbol, fills, orders, positions },
  ref,
) {
  const container = useRef<HTMLDivElement>(null);
  const chart = useRef<IChartApi | null>(null);
  const candles = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volume = useRef<ISeriesApi<"Histogram"> | null>(null);
  const vwap = useRef<ISeriesApi<"Line"> | null>(null);
  const ema20 = useRef<ISeriesApi<"Line"> | null>(null);
  const markers = useRef<ISeriesMarkersPluginApi<Time> | null>(null);
  const lines = useRef<IPriceLine[]>([]);
  const drawn = useRef({ epoch: -1, timeframe: 0, count: 0 });

  useImperativeHandle(ref, () => ({
    screenshot: () => chart.current?.takeScreenshot().toDataURL("image/png") ?? null,
  }));

  useEffect(() => {
    if (!container.current) return;
    const c = createChart(container.current, {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: "#121722" }, textColor: "#8a94a8", fontSize: 11 },
      grid: { vertLines: { color: "#1b2333" }, horzLines: { color: "#1b2333" } },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: "#263042" },
      timeScale: { borderColor: "#263042", timeVisible: true, secondsVisible: false, rightOffset: 8 },
    });
    candles.current = c.addSeries(CandlestickSeries, {
      upColor: UP,
      downColor: DOWN,
      borderVisible: false,
      wickUpColor: UP,
      wickDownColor: DOWN,
    });
    volume.current = c.addSeries(HistogramSeries, { priceScaleId: "vol", priceFormat: { type: "volume" }, lastValueVisible: false, priceLineVisible: false });
    c.priceScale("vol").applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
    vwap.current = c.addSeries(LineSeries, { color: "#f5a524", lineWidth: 2, priceLineVisible: false, lastValueVisible: false, title: "VWAP" });
    ema20.current = c.addSeries(LineSeries, { color: "#7aa2f7", lineWidth: 1, priceLineVisible: false, lastValueVisible: false, title: "EMA 20" });
    markers.current = createSeriesMarkers(candles.current, []);
    chart.current = c;
    return () => {
      c.remove();
      chart.current = null;
    };
  }, []);

  const agg = useMemo(() => aggregate(bars, timeframe), [bars, timeframe]);

  useEffect(() => {
    if (!candles.current || !agg.length) return;
    const vw = sessionVwap(agg);
    const e = ema(agg.map((b) => b.c), 20);
    const d = drawn.current;
    const incremental = d.epoch === epoch && d.timeframe === timeframe && agg.length >= d.count && d.count > 0;
    const from = incremental ? Math.max(0, d.count - 1) : 0;
    const slice = agg.slice(from);

    const candleData = slice.map((b) => ({ time: ts(b.t), open: b.o, high: b.h, low: b.l, close: b.c }));
    const volData = slice.map((b) => ({ time: ts(b.t), value: b.v, color: b.c >= b.o ? "#26a69a55" : "#ef535055" }));
    const vwData = slice.map((b, i) => ({ time: ts(b.t), value: vw[from + i] }));
    const emaData = slice.flatMap((b, i) => (e[from + i] == null ? [] : [{ time: ts(b.t), value: e[from + i] as number }]));

    if (incremental) {
      candleData.forEach((p) => candles.current!.update(p));
      volData.forEach((p) => volume.current!.update(p));
      vwData.forEach((p) => vwap.current!.update(p));
      emaData.forEach((p) => ema20.current!.update(p));
    } else {
      candles.current.setData(candleData);
      volume.current!.setData(volData);
      vwap.current!.setData(vwData);
      ema20.current!.setData(emaData);
      chart.current?.timeScale().scrollToRealTime();
    }
    drawn.current = { epoch, timeframe, count: agg.length };
  }, [agg, epoch, timeframe]);

  useEffect(() => {
    if (!markers.current) return;
    const width = timeframe * 60;
    const list: SeriesMarker<Time>[] = fills
      .filter((f) => f.price_source !== "settlement")
      .map((f) => {
        const isOption = f.symbol !== symbol;
        const buy = f.side === "buy";
        return {
          time: ts(f.t - (f.t % width)),
          position: buy ? "belowBar" : "aboveBar",
          shape: buy ? "arrowUp" : "arrowDown",
          color: buy ? UP : DOWN,
          text: isOption ? `${describeSymbol(f.symbol).split(" ").slice(-2).join("")} ${f.price.toFixed(2)}` : `${f.qty}@${f.price.toFixed(2)}`,
        };
      });
    list.sort((a, b) => (a.time as number) - (b.time as number));
    markers.current.setMarkers(list);
  }, [fills, timeframe, symbol]);

  useEffect(() => {
    const series = candles.current;
    if (!series) return;
    lines.current.forEach((l) => series.removePriceLine(l));
    lines.current = [];
    const stock = positions.find((p) => p.symbol === symbol);
    if (stock) {
      lines.current.push(
        series.createPriceLine({ price: stock.avg_cost, color: "#e6e9ef", lineStyle: 2, lineWidth: 1, title: `avg ${stock.qty > 0 ? "L" : "S"} ${Math.abs(stock.qty)}` }),
      );
    }
    for (const o of orders) {
      if (o.status !== "open" || o.symbol !== symbol) continue;
      const price = o.type === "limit" ? o.limit_price : o.stop_price;
      if (price == null) continue;
      lines.current.push(
        series.createPriceLine({
          price,
          color: o.tag === "stop_loss" || o.type === "stop" ? DOWN : UP,
          lineStyle: 1,
          lineWidth: 1,
          title: `${o.tag ?? o.type} ${o.side} ${o.qty}`,
        }),
      );
    }
  }, [orders, positions, symbol]);

  return <div ref={container} className="h-full w-full" />;
});
