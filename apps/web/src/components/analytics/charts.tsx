"use client";

import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { etDateTime, money, pct } from "@/lib/format";
import type { Analytics, GroupStat } from "@/lib/types";
import { cn } from "@/lib/utils";

const AXIS = { stroke: "#8a94a8", fontSize: 11, tickLine: false, axisLine: false } as const;
const TOOLTIP = {
  contentStyle: { background: "#121722", border: "1px solid #263042", borderRadius: 6, fontSize: 12 },
  labelStyle: { color: "#8a94a8" },
};
const UP = "#26a69a";
const DOWN = "#ef5350";

const compactMoney = (v: number) => (Math.abs(v) >= 1000 ? `$${(v / 1000).toFixed(1)}k` : `$${v.toFixed(0)}`);

export function EquityChart({ data, start }: { data: Analytics["equity"]; start: number }) {
  return (
    <ResponsiveContainer width="100%" height={240}>
      <AreaChart data={data} margin={{ left: 8, right: 8, top: 8 }}>
        <defs>
          <linearGradient id="eq" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#f5a524" stopOpacity={0.35} />
            <stop offset="100%" stopColor="#f5a524" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke="#1b2333" vertical={false} />
        <XAxis dataKey="t" {...AXIS} tickFormatter={(t) => etDateTime(t).split(",")[0]} minTickGap={60} />
        <YAxis {...AXIS} domain={["auto", "auto"]} tickFormatter={compactMoney} width={60} />
        <Tooltip {...TOOLTIP} labelFormatter={(t) => etDateTime(t as number)} formatter={(v) => [money(v as number), "Equity"]} />
        <ReferenceLine y={start} stroke="#8a94a8" strokeDasharray="3 3" />
        <Area type="monotone" dataKey="equity" stroke="#f5a524" strokeWidth={1.5} fill="url(#eq)" isAnimationActive={false} />
      </AreaChart>
    </ResponsiveContainer>
  );
}

export function DrawdownChart({ data }: { data: Analytics["drawdown"] }) {
  return (
    <ResponsiveContainer width="100%" height={140}>
      <AreaChart data={data} margin={{ left: 8, right: 8 }}>
        <CartesianGrid stroke="#1b2333" vertical={false} />
        <XAxis dataKey="t" {...AXIS} tickFormatter={(t) => etDateTime(t).split(",")[0]} minTickGap={60} />
        <YAxis {...AXIS} tickFormatter={(v) => pct(v, 1)} width={60} />
        <Tooltip {...TOOLTIP} labelFormatter={(t) => etDateTime(t as number)} formatter={(v) => [pct(v as number), "Drawdown"]} />
        <Area type="stepAfter" dataKey="dd" stroke={DOWN} fill={DOWN} fillOpacity={0.25} isAnimationActive={false} />
      </AreaChart>
    </ResponsiveContainer>
  );
}

export function PnlHistogram({ data }: { data: Analytics["histogram"] }) {
  const rows = data.map((b) => ({ ...b, mid: (b.from + b.to) / 2 }));
  return (
    <ResponsiveContainer width="100%" height={200}>
      <BarChart data={rows} margin={{ left: 8, right: 8 }}>
        <CartesianGrid stroke="#1b2333" vertical={false} />
        <XAxis dataKey="mid" {...AXIS} tickFormatter={compactMoney} />
        <YAxis {...AXIS} allowDecimals={false} width={30} />
        <Tooltip
          {...TOOLTIP}
          labelFormatter={(_, p) => {
            const r = p?.[0]?.payload as (typeof rows)[number] | undefined;
            return r ? `${money(r.from)} to ${money(r.to)}` : "";
          }}
          formatter={(v) => [v as number, "Trades"]}
        />
        <Bar dataKey="count" isAnimationActive={false}>
          {rows.map((r, i) => (
            <Cell key={i} fill={r.mid >= 0 ? UP : DOWN} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

export function GroupBars({ data }: { data: GroupStat[] }) {
  return (
    <ResponsiveContainer width="100%" height={200}>
      <BarChart data={data} margin={{ left: 8, right: 8 }}>
        <CartesianGrid stroke="#1b2333" vertical={false} />
        <XAxis dataKey="key" {...AXIS} />
        <YAxis {...AXIS} tickFormatter={compactMoney} width={50} />
        <Tooltip
          {...TOOLTIP}
          formatter={(v, _n, p) => {
            const r = p.payload as GroupStat;
            return [`${money(v as number)} · ${r.count} trades · ${pct(r.win_rate, 0)} win`, "P&L"];
          }}
        />
        <ReferenceLine y={0} stroke="#263042" />
        <Bar dataKey="pnl" isAnimationActive={false}>
          {data.map((r, i) => (
            <Cell key={i} fill={r.pnl >= 0 ? UP : DOWN} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

export function Heatmap({ data }: { data: Analytics["heatmap"] }) {
  const buckets = [...new Set(data.map((d) => d.bucket))].sort();
  const days = ["Mon", "Tue", "Wed", "Thu", "Fri"];
  const max = Math.max(1, ...data.map((d) => Math.abs(d.pnl)));
  const cell = (wd: string, b: string) => data.find((d) => d.weekday === wd && d.bucket === b);
  if (!data.length) return <p className="text-sm text-muted">No trades yet.</p>;
  return (
    <div className="overflow-x-auto">
      <table className="num text-[11px]">
        <thead>
          <tr>
            <th />
            {buckets.map((b) => (
              <th key={b} className="px-1 pb-1 font-normal text-muted">
                {b}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {days.map((wd) => (
            <tr key={wd}>
              <td className="pr-2 text-muted">{wd}</td>
              {buckets.map((b) => {
                const c = cell(wd, b);
                const alpha = c ? 0.15 + 0.85 * (Math.abs(c.pnl) / max) : 0;
                return (
                  <td key={b} className="p-0.5">
                    <div
                      className={cn("flex h-8 w-14 items-center justify-center rounded", !c && "bg-panel-2")}
                      style={c ? { background: `${c.pnl >= 0 ? "rgba(38,166,154," : "rgba(239,83,80,"}${alpha})` } : undefined}
                      title={c ? `${wd} ${b}: ${money(c.pnl)} over ${c.count} trades` : undefined}
                    >
                      {c ? compactMoney(c.pnl) : ""}
                    </div>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
