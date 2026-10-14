"use client";

import { Camera, Keyboard } from "lucide-react";
import Link from "next/link";
import { use, useCallback, useEffect, useRef, useState } from "react";

import { Modal, NoteForm } from "@/components/journal/note-form";
import { ReplayChart, type ChartHandle } from "@/components/replay/chart";
import { OptionChain } from "@/components/replay/option-chain";
import { OrderTicket, type TicketTarget } from "@/components/replay/order-ticket";
import { AccountSummary, FillsTable, OrdersTable, PositionsTable } from "@/components/replay/positions";
import { SPEEDS, Transport } from "@/components/replay/transport";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import { useReplaySocket } from "@/hooks/use-replay-socket";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { useReplay } from "@/stores/replay";

const TIMEFRAMES = [1, 5, 15];
const SHORTCUTS = [
  ["Space", "Play / pause"],
  ["→ / Shift+→", "Step 1 / 5 bars"],
  ["↑ / ↓", "Faster / slower"],
  ["N", "Next trading day"],
  ["B / S", "Market buy / sell at ticket size"],
  ["F", "Flatten everything"],
  ["1 / 5 / 0", "1m / 5m / 15m candles"],
  ["J", "Snapshot chart to journal"],
];

export default function ReplayPage({ params }: { params: Promise<{ sessionId: string }> }) {
  const { sessionId } = use(params);
  const send = useReplaySocket(sessionId);
  const { session, state, bars, account, orders, fills, connected, error, epoch, setError } = useReplay();
  const chartRef = useRef<ChartHandle>(null);
  const [timeframe, setTimeframe] = useState(1);
  const [option, setOption] = useState<TicketTarget | null>(null);
  const [qty, setQty] = useState(100);
  const [optionQty, setOptionQty] = useState(1);
  const [tab, setTab] = useState<"orders" | "fills">("orders");
  const [snap, setSnap] = useState<string | null>(null);
  const [help, setHelp] = useState(false);

  const last = bars[bars.length - 1];
  const symbol = session?.symbol ?? "";

  const quickOrder = useCallback(
    (side: "buy" | "sell") => {
      api(`/sessions/${sessionId}/orders`, {
        method: "POST",
        json: { symbol: option?.symbol ?? symbol, side, qty: option ? optionQty : qty, type: "market" },
      }).catch((e: Error) => setError(e.message));
    },
    [sessionId, option, symbol, qty, optionQty, setError],
  );

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName) || snap) return;
      if (!state) return;
      const speedIdx = SPEEDS.indexOf(state.speed);
      const keys: Record<string, () => void> = {
        " ": () => send({ action: state.status === "playing" ? "pause" : "play" }),
        ArrowRight: () => send({ action: "step", value: e.shiftKey ? 5 : 1 }),
        ArrowUp: () => send({ action: "speed", value: SPEEDS[Math.min(SPEEDS.length - 1, speedIdx + 1)] }),
        ArrowDown: () => send({ action: "speed", value: SPEEDS[Math.max(0, speedIdx - 1)] }),
        n: () => send({ action: "next_day" }),
        b: () => quickOrder("buy"),
        s: () => quickOrder("sell"),
        f: () => api(`/sessions/${sessionId}/flatten`, { method: "POST" }),
        "1": () => setTimeframe(1),
        "5": () => setTimeframe(5),
        "0": () => setTimeframe(15),
        j: () => setSnap(chartRef.current?.screenshot() ?? ""),
        "?": () => setHelp((h) => !h),
      };
      const fn = keys[e.key.length === 1 ? e.key.toLowerCase() : e.key];
      if (fn) {
        e.preventDefault();
        fn();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [state, send, quickOrder, sessionId, snap]);

  if (!session || !state || !account) {
    return (
      <div className="p-8 text-center text-muted">
        {error ?? (connected ? "Loading session…" : "Connecting to replay server…")}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-4">
        <h1 className="text-lg font-semibold">
          {symbol} replay <span className="text-sm font-normal text-muted">#{session.id}</span>
        </h1>
        <span className={cn("h-2 w-2 rounded-full", connected ? "bg-up" : "bg-down")} title={connected ? "Live" : "Reconnecting"} />
        <div className="flex-1">
          <AccountSummary account={account} startingCash={session.starting_cash} />
        </div>
        <Link href={`/analytics?session=${session.id}`} className="text-sm text-accent hover:underline">
          Analytics →
        </Link>
      </div>
      {error && (
        <div className="flex items-center justify-between rounded border border-down/40 bg-down/10 px-3 py-2 text-sm text-down">
          {error}
          <button onClick={() => setError(null)}>dismiss</button>
        </div>
      )}

      <div className="grid gap-3 xl:grid-cols-[1fr_340px]">
        <Card className="flex h-[560px] flex-col overflow-hidden">
          <CardHeader className="py-1.5">
            <div className="flex items-center gap-1">
              {TIMEFRAMES.map((tf) => (
                <Button key={tf} size="sm" variant={tf === timeframe ? "outline" : "ghost"} onClick={() => setTimeframe(tf)}>
                  {tf}m
                </Button>
              ))}
              <span className="ml-3 text-xs text-muted">
                <span className="text-accent">VWAP</span> · <span className="text-[#7aa2f7]">EMA 20</span>
              </span>
            </div>
            <div className="flex items-center gap-1">
              <Button size="sm" variant="ghost" onClick={() => setSnap(chartRef.current?.screenshot() ?? "")}>
                <Camera className="h-3.5 w-3.5" /> Journal
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setHelp((h) => !h)}>
                <Keyboard className="h-3.5 w-3.5" />
              </Button>
            </div>
          </CardHeader>
          <div className="relative min-h-0 flex-1">
            <ReplayChart
              ref={chartRef}
              bars={bars}
              epoch={epoch}
              timeframe={timeframe}
              symbol={symbol}
              fills={fills}
              orders={orders}
              positions={account.positions}
            />
            {help && (
              <div className="absolute left-3 top-3 z-10 rounded border border-border bg-panel/95 p-3 text-xs">
                {SHORTCUTS.map(([k, v]) => (
                  <div key={k} className="flex justify-between gap-6 py-0.5">
                    <kbd className="num text-accent">{k}</kbd>
                    <span className="text-muted">{v}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
          <Transport state={state} send={send} />
        </Card>

        <div className="space-y-3">
          <Card>
            <CardHeader>
              <CardTitle>Order ticket</CardTitle>
              <span className="text-[11px] text-muted">B / S</span>
            </CardHeader>
            <div className="p-3">
              <OrderTicket
                sessionId={sessionId}
                underlying={symbol}
                lastPrice={last?.c ?? 0}
                option={option}
                onClearOption={() => setOption(null)}
                qty={option ? optionQty : qty}
                onQty={option ? setOptionQty : setQty}
              />
            </div>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Positions</CardTitle>
              <Button size="sm" variant="destructive" onClick={() => api(`/sessions/${sessionId}/flatten`, { method: "POST" })}>
                Flatten (F)
              </Button>
            </CardHeader>
            <PositionsTable sessionId={sessionId} account={account} />
          </Card>
        </div>
      </div>

      <div className="grid gap-3 xl:grid-cols-[1fr_1fr]">
        <Card>
          <CardHeader>
            <CardTitle>Option chain</CardTitle>
            <span className="text-[11px] text-muted">click a price to load the ticket · R = real Alpaca bar</span>
          </CardHeader>
          <OptionChain sessionId={sessionId} cursor={state.cursor_ts} selected={option?.symbol ?? null} onPick={setOption} />
        </Card>
        <Card>
          <CardHeader>
            <div className="flex gap-1">
              {(["orders", "fills"] as const).map((t) => (
                <Button key={t} size="sm" variant={tab === t ? "outline" : "ghost"} onClick={() => setTab(t)}>
                  {t === "orders" ? `Orders (${orders.filter((o) => o.status === "open").length} open)` : `Fills (${fills.length})`}
                </Button>
              ))}
            </div>
          </CardHeader>
          {tab === "orders" ? <OrdersTable sessionId={sessionId} orders={orders} /> : <FillsTable fills={fills} />}
        </Card>
      </div>

      {snap !== null && (
        <Modal title="Journal entry" onClose={() => setSnap(null)}>
          <NoteForm sessionId={sessionId} screenshot={snap || null} onDone={() => setSnap(null)} onCancel={() => setSnap(null)} />
        </Modal>
      )}
    </div>
  );
}
