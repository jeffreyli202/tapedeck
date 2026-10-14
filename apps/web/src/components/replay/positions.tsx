"use client";

import { X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { describeSymbol, etTime, money, num, pnlClass, signedMoney } from "@/lib/format";
import type { Account, Fill, Order } from "@/lib/types";
import { cn } from "@/lib/utils";

export function AccountSummary({ account, startingCash }: { account: Account; startingCash: number }) {
  const total = account.equity - startingCash;
  const items = [
    ["Equity", money(account.equity), ""],
    ["P&L", signedMoney(total), pnlClass(total)],
    ["Unrealized", signedMoney(account.unrealized_pnl), pnlClass(account.unrealized_pnl)],
    ["Cash", money(account.cash), ""],
    ["Buying power", money(account.buying_power), ""],
  ];
  return (
    <div className="grid grid-cols-5 gap-2">
      {items.map(([label, value, cls]) => (
        <div key={label}>
          <div className="text-[11px] uppercase text-muted">{label}</div>
          <div className={cn("num text-sm font-medium", cls)}>{value}</div>
        </div>
      ))}
    </div>
  );
}

export function PositionsTable({ sessionId, account }: { sessionId: string; account: Account }) {
  if (!account.positions.length) return <p className="p-3 text-sm text-muted">No open positions.</p>;
  const close = (symbol: string, qty: number) =>
    api(`/sessions/${sessionId}/orders`, {
      method: "POST",
      json: { symbol, side: qty > 0 ? "sell" : "buy", qty: Math.abs(qty), type: "market", tag: "close" },
    });
  return (
    <table className="num w-full text-xs">
      <thead className="text-muted">
        <tr className="text-left">
          <th className="px-3 py-1 font-normal">Symbol</th>
          <th className="font-normal">Qty</th>
          <th className="font-normal">Avg</th>
          <th className="font-normal">Last</th>
          <th className="font-normal">Value</th>
          <th className="font-normal">Unrealized</th>
          <th />
        </tr>
      </thead>
      <tbody>
        {account.positions.map((p) => (
          <tr key={p.symbol} className="border-t border-border/50">
            <td className="px-3 py-1">{describeSymbol(p.symbol)}</td>
            <td className={p.qty > 0 ? "text-up" : "text-down"}>{p.qty}</td>
            <td>{num(p.avg_cost)}</td>
            <td>{num(p.last)}</td>
            <td>{money(p.market_value)}</td>
            <td className={pnlClass(p.unrealized_pnl)}>{signedMoney(p.unrealized_pnl)}</td>
            <td className="pr-2 text-right">
              <Button size="sm" variant="ghost" onClick={() => close(p.symbol, p.qty)}>
                Close
              </Button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

const STATUS_TONE = { open: "accent", filled: "up", canceled: "neutral", rejected: "down" } as const;

export function OrdersTable({ sessionId, orders }: { sessionId: string; orders: Order[] }) {
  if (!orders.length) return <p className="p-3 text-sm text-muted">No orders yet. Press B or S to trade.</p>;
  return (
    <div className="max-h-64 overflow-auto">
      <table className="num w-full text-xs">
        <thead className="sticky top-0 bg-panel text-muted">
          <tr className="text-left">
            <th className="px-3 py-1 font-normal">Time</th>
            <th className="font-normal">Symbol</th>
            <th className="font-normal">Side</th>
            <th className="font-normal">Type</th>
            <th className="font-normal">Price</th>
            <th className="font-normal">Status</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {orders.map((o) => (
            <tr key={o.id} className="border-t border-border/50" title={o.reason ?? undefined}>
              <td className="px-3 py-1 text-muted">{o.created_ts ? etTime(o.created_ts + 60) : ""}</td>
              <td>{describeSymbol(o.symbol)}</td>
              <td className={o.side === "buy" ? "text-up" : "text-down"}>
                {o.side} {o.qty}
              </td>
              <td>
                {o.tag && o.parent_id ? o.tag.replace("_", " ") : o.type}
                {(o.take_profit || o.stop_loss) && " + bracket"}
              </td>
              <td>{o.fill_price != null ? num(o.fill_price) : num(o.limit_price ?? o.stop_price)}</td>
              <td>
                <Badge tone={STATUS_TONE[o.status]}>{o.status}</Badge>
              </td>
              <td className="pr-2 text-right">
                {o.status === "open" && (
                  <button
                    className="text-muted hover:text-down"
                    onClick={() => api(`/sessions/${sessionId}/orders/${o.id}`, { method: "DELETE" })}
                    title="Cancel"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function FillsTable({ fills }: { fills: Fill[] }) {
  if (!fills.length) return <p className="p-3 text-sm text-muted">No fills yet.</p>;
  return (
    <div className="max-h-64 overflow-auto">
      <table className="num w-full text-xs">
        <thead className="sticky top-0 bg-panel text-muted">
          <tr className="text-left">
            <th className="px-3 py-1 font-normal">Time</th>
            <th className="font-normal">Symbol</th>
            <th className="font-normal">Side</th>
            <th className="font-normal">Price</th>
            <th className="font-normal">Fee</th>
            <th className="font-normal">Source</th>
          </tr>
        </thead>
        <tbody>
          {[...fills].reverse().map((f, i) => (
            <tr key={`${f.order_id}-${i}`} className="border-t border-border/50">
              <td className="px-3 py-1 text-muted">{etTime(f.t)}</td>
              <td>{describeSymbol(f.symbol)}</td>
              <td className={f.side === "buy" ? "text-up" : "text-down"}>
                {f.side} {f.qty}
              </td>
              <td>{num(f.price)}</td>
              <td>{num(f.commission)}</td>
              <td>
                <Badge tone={f.price_source === "model" ? "accent" : "neutral"}>{f.price_source}</Badge>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
