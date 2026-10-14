"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Select } from "@/components/ui/input";
import { api } from "@/lib/api";
import { pct } from "@/lib/format";
import type { Chain, OptionQuote } from "@/lib/types";
import { cn } from "@/lib/utils";

import type { TicketTarget } from "./order-ticket";

type Props = { sessionId: string; cursor: number; selected: string | null; onPick: (t: TicketTarget) => void };

function Quote({ q, selected, onPick, align }: { q: OptionQuote; selected: boolean; onPick: Props["onPick"]; align: "left" | "right" }) {
  const cells = [
    <td key="iv" className="px-2 text-muted">{(q.iv * 100).toFixed(1)}</td>,
    <td key="d" className="px-2 text-muted">{q.delta.toFixed(2)}</td>,
    <td key="p" className="px-2">
      <button
        className={cn("num rounded px-1.5 py-0.5 hover:bg-accent/20", selected && "bg-accent text-black")}
        onClick={() => onPick({ symbol: q.symbol, price: q.price, source: q.source })}
      >
        {q.price.toFixed(2)}
        {q.source === "real" && <span className="ml-0.5 text-[9px] text-up">R</span>}
      </button>
    </td>,
  ];
  return <>{align === "left" ? cells : [...cells].reverse()}</>;
}

export function OptionChain({ sessionId, cursor, selected, onPick }: Props) {
  const [expiry, setExpiry] = useState<string | null>(null);
  const { data, error } = useQuery({
    queryKey: ["chain", sessionId, expiry, cursor],
    queryFn: () => api<Chain>(`/sessions/${sessionId}/chain?strikes=8${expiry ? `&expiry=${expiry}` : ""}`),
    placeholderData: keepPreviousData,
  });

  if (error) return <p className="p-3 text-sm text-down">{(error as Error).message}</p>;
  if (!data) return <p className="p-3 text-sm text-muted">Loading chain…</p>;
  const atm = data.rows.reduce((best, r) => (Math.abs(r.strike - data.spot) < Math.abs(best - data.spot) ? r.strike : best), data.rows[0]?.strike);

  return (
    <div>
      <div className="flex flex-wrap items-center gap-3 border-b border-border px-3 py-2 text-xs">
        <Select className="h-7 w-36" value={data.expiry} onChange={(e) => setExpiry(e.target.value)}>
          {data.expiries.map((e, i) => (
            <option key={e} value={e}>
              {e} ({i === 0 ? "0DTE" : `${Math.round((Date.parse(e) - Date.parse(data.expiries[0])) / 86_400_000)}d`})
            </option>
          ))}
        </Select>
        <span className="text-muted">
          Spot <span className="num text-foreground">{data.spot.toFixed(2)}</span>
        </span>
        <span className="text-muted">
          ATM IV proxy <span className="num text-foreground">{pct(data.atm_iv, 1)}</span>
        </span>
        <Badge tone={data.real_contracts ? "up" : "accent"}>
          {data.real_contracts ? `${data.real_contracts} contracts with real bars today` : "all prices modeled (Black-Scholes)"}
        </Badge>
      </div>
      <table className="num w-full text-xs">
        <thead className="text-muted">
          <tr>
            <th className="px-2 py-1 text-left font-normal">IV</th>
            <th className="px-2 text-left font-normal">Δ</th>
            <th className="px-2 text-left font-normal">Call</th>
            <th className="px-2 text-center font-normal">Strike</th>
            <th className="px-2 text-right font-normal">Put</th>
            <th className="px-2 text-right font-normal">Δ</th>
            <th className="px-2 text-right font-normal">IV</th>
          </tr>
        </thead>
        <tbody>
          {data.rows.map((r) => (
            <tr key={r.strike} className={cn("border-t border-border/50", r.strike === atm && "bg-accent/5")}>
              <Quote q={r.call} selected={selected === r.call.symbol} onPick={onPick} align="left" />
              <td className={cn("px-2 py-0.5 text-center font-medium", r.strike === atm && "text-accent")}>{r.strike}</td>
              <Quote q={r.put} selected={selected === r.put.symbol} onPick={onPick} align="right" />
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
