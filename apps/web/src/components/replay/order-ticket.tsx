"use client";

import { useMutation } from "@tanstack/react-query";
import { X } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input, Label, Select } from "@/components/ui/input";
import { api } from "@/lib/api";
import { describeSymbol, money } from "@/lib/format";
import type { Order } from "@/lib/types";
import { cn } from "@/lib/utils";

export type TicketTarget = { symbol: string; price: number; source?: "real" | "model" };

type Props = {
  sessionId: string;
  underlying: string;
  lastPrice: number;
  option: TicketTarget | null;
  onClearOption: () => void;
  qty: number;
  onQty: (q: number) => void;
};

type OrderType = "market" | "limit" | "stop";

export function OrderTicket({ sessionId, underlying, lastPrice, option, onClearOption, qty, onQty }: Props) {
  const [type, setType] = useState<OrderType>("market");
  const [price, setPrice] = useState("");
  const [bracket, setBracket] = useState(false);
  const [tp, setTp] = useState("");
  const [sl, setSl] = useState("");
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  const symbol = option?.symbol ?? underlying;
  const ref = option?.price ?? lastPrice;
  const mult = option ? 100 : 1;

  const submit = useMutation({
    mutationFn: (side: "buy" | "sell") =>
      api<Order>(`/sessions/${sessionId}/orders`, {
        method: "POST",
        json: {
          symbol,
          side,
          qty,
          type,
          limit_price: type === "limit" ? +price : null,
          stop_price: type === "stop" ? +price : null,
          take_profit: bracket && tp ? +tp : null,
          stop_loss: bracket && sl ? +sl : null,
        },
      }),
    onSuccess: (o) =>
      setMessage(
        o.status === "rejected"
          ? { ok: false, text: o.reason ?? "rejected" }
          : { ok: true, text: `${o.side} ${o.qty} ${describeSymbol(o.symbol)} queued, fills on the next bar` },
      ),
    onError: (e: Error) => setMessage({ ok: false, text: e.message }),
  });

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="num font-medium">{describeSymbol(symbol)}</div>
        <div className="flex items-center gap-2">
          {option?.source && <Badge tone={option.source === "real" ? "up" : "accent"}>{option.source}</Badge>}
          {option && (
            <button className="text-muted hover:text-foreground" onClick={onClearOption} title="Back to stock">
              <X className="h-4 w-4" />
            </button>
          )}
        </div>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <div>
          <Label>{option ? "Contracts" : "Shares"}</Label>
          <Input type="number" min={1} value={qty} onChange={(e) => onQty(Math.max(1, +e.target.value || 1))} className="num" />
        </div>
        <div>
          <Label>Type</Label>
          <Select value={type} onChange={(e) => setType(e.target.value as OrderType)}>
            <option value="market">Market</option>
            <option value="limit">Limit</option>
            <option value="stop">Stop</option>
          </Select>
        </div>
      </div>
      {type !== "market" && (
        <div>
          <Label>{type === "limit" ? "Limit price" : "Stop price"}</Label>
          <Input type="number" step="0.01" value={price} placeholder={ref.toFixed(2)} onChange={(e) => setPrice(e.target.value)} className="num" />
        </div>
      )}
      <label className="flex items-center gap-2 text-xs text-muted">
        <input type="checkbox" checked={bracket} onChange={(e) => setBracket(e.target.checked)} /> Bracket (take profit / stop loss)
      </label>
      {bracket && (
        <div className="grid grid-cols-2 gap-2">
          <div>
            <Label>Take profit</Label>
            <Input type="number" step="0.01" value={tp} onChange={(e) => setTp(e.target.value)} className="num" />
          </div>
          <div>
            <Label>Stop loss</Label>
            <Input type="number" step="0.01" value={sl} onChange={(e) => setSl(e.target.value)} className="num" />
          </div>
        </div>
      )}
      <div className="flex justify-between text-xs text-muted">
        <span>Last {ref.toFixed(2)}</span>
        <span>Est. notional {money(ref * qty * mult)}</span>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <Button variant="buy" disabled={submit.isPending} onClick={() => submit.mutate("buy")} title="B">
          Buy
        </Button>
        <Button variant="sell" disabled={submit.isPending} onClick={() => submit.mutate("sell")} title="S">
          Sell
        </Button>
      </div>
      {message && <p className={cn("text-xs", message.ok ? "text-muted" : "text-down")}>{message.text}</p>}
    </div>
  );
}
