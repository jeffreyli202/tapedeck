"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { ParamForm } from "@/components/backtest/param-form";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label, Select } from "@/components/ui/input";
import { useTradingDays } from "@/hooks/use-trading-days";
import { api, wsUrl } from "@/lib/api";
import { num, pct, pnlClass, signedMoney } from "@/lib/format";
import type { BacktestRun, StrategyInfo } from "@/lib/types";

type Progress = { status: string; progress: number; error?: string };

function useBacktestProgress(runId: string | null, onDone: () => void) {
  const [progress, setProgress] = useState<Progress | null>(null);
  useEffect(() => {
    if (!runId) return;
    const ws = new WebSocket(wsUrl(`/ws/backtests/${runId}`));
    ws.onmessage = (m) => {
      const p = JSON.parse(m.data) as Progress;
      setProgress(p);
      if (p.status === "done" || p.status === "failed") {
        onDone();
        ws.close();
      }
    };
    return () => ws.close();
  }, [runId, onDone]);
  return progress;
}

const STATUS_TONE = { queued: "neutral", running: "accent", done: "up", failed: "down" } as const;

export default function BacktestPage() {
  const qc = useQueryClient();
  const { data: strategies = [] } = useQuery({ queryKey: ["strategies"], queryFn: () => api<StrategyInfo[]>("/strategies") });
  const { data: runs = [] } = useQuery({ queryKey: ["backtests"], queryFn: () => api<BacktestRun[]>("/backtests") });
  const [name, setName] = useState("orb");
  const [symbol, setSymbol] = useState("SPY");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [cash, setCash] = useState(100_000);
  const [params, setParams] = useState<Record<string, unknown>>({});
  const [activeRun, setActiveRun] = useState<string | null>(null);
  const { data: days = [] } = useTradingDays(symbol);

  const strategy = useMemo(() => strategies.find((s) => s.name === name), [strategies, name]);
  const from = start || days[0] || "";
  const to = end || days[days.length - 1] || "";

  const refresh = useMemo(() => () => qc.invalidateQueries({ queryKey: ["backtests"] }), [qc]);
  const progress = useBacktestProgress(activeRun, refresh);

  const run = useMutation({
    mutationFn: () =>
      api<BacktestRun>("/backtests", {
        method: "POST",
        json: { strategy: name, symbol, start_date: from, end_date: to, starting_cash: cash, params },
      }),
    onSuccess: (r) => {
      setActiveRun(r.id);
      refresh();
    },
  });
  const remove = useMutation({ mutationFn: (id: string) => api(`/backtests/${id}`, { method: "DELETE" }), onSuccess: refresh });

  return (
    <div className="grid gap-4 lg:grid-cols-[420px_1fr]">
      <Card className="h-fit">
        <CardHeader>
          <CardTitle>New backtest</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <Label>Strategy</Label>
            <Select
              value={name}
              onChange={(e) => {
                setName(e.target.value);
                setParams({});
              }}
            >
              {strategies.map((s) => (
                <option key={s.name} value={s.name}>
                  {s.label}
                </option>
              ))}
            </Select>
            {strategy && (
              <p className="mt-2 text-xs text-muted">
                {strategy.description}
                {strategy.uses_options && " Option prices come from real Alpaca bars where ingested, otherwise Black-Scholes."}
              </p>
            )}
          </div>
          <div className="grid grid-cols-3 gap-2">
            <div>
              <Label>Symbol</Label>
              <Select value={symbol} onChange={(e) => setSymbol(e.target.value)}>
                <option>SPY</option>
                <option>QQQ</option>
              </Select>
            </div>
            <div>
              <Label>From</Label>
              <Input type="date" value={from} onChange={(e) => setStart(e.target.value)} />
            </div>
            <div>
              <Label>To</Label>
              <Input type="date" value={to} onChange={(e) => setEnd(e.target.value)} />
            </div>
          </div>
          <div>
            <Label>Starting cash</Label>
            <Input type="number" className="num" value={cash} onChange={(e) => setCash(+e.target.value)} />
          </div>
          {strategy && (
            <div className="border-t border-border pt-4">
              <ParamForm schema={strategy.params.properties} values={params} onChange={setParams} />
            </div>
          )}
          <Button className="w-full" disabled={!from || !to || run.isPending} onClick={() => run.mutate()}>
            Run backtest
          </Button>
          {run.error && <p className="text-xs text-down">{(run.error as Error).message}</p>}
          {progress && activeRun && (
            <div className="space-y-1">
              <div className="h-1.5 overflow-hidden rounded bg-panel-2">
                <div className="h-full bg-accent transition-all" style={{ width: `${progress.progress * 100}%` }} />
              </div>
              <p className="text-xs text-muted">
                {progress.status} · {pct(progress.progress, 0)}
                {progress.status === "done" && (
                  <Link href={`/analytics?run=${activeRun}`} className="ml-2 text-accent hover:underline">
                    View results →
                  </Link>
                )}
                {progress.error && <span className="text-down"> {progress.error}</span>}
              </p>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Runs</CardTitle>
        </CardHeader>
        {runs.length === 0 ? (
          <CardContent className="text-sm text-muted">No backtests yet.</CardContent>
        ) : (
          <table className="num w-full text-sm">
            <thead className="text-xs text-muted">
              <tr className="text-left">
                <th className="px-4 py-2 font-normal">Strategy</th>
                <th className="font-normal">Range</th>
                <th className="font-normal">Status</th>
                <th className="text-right font-normal">Net P&L</th>
                <th className="text-right font-normal">Return</th>
                <th className="text-right font-normal">Max DD</th>
                <th className="text-right font-normal">Sharpe</th>
                <th className="text-right font-normal">Win %</th>
                <th className="text-right font-normal">Trades</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => {
                const m = r.metrics;
                const label = strategies.find((s) => s.name === r.strategy)?.label ?? r.strategy;
                return (
                  <tr key={r.id} className="border-t border-border/50 hover:bg-panel-2">
                    <td className="px-4 py-2">
                      {r.status === "done" ? (
                        <Link href={`/analytics?run=${r.id}`} className="text-accent hover:underline">
                          {label}
                        </Link>
                      ) : (
                        label
                      )}
                      <span className="ml-1 text-xs text-muted">{r.symbol}</span>
                    </td>
                    <td className="text-xs text-muted">
                      {r.start_date} → {r.end_date}
                    </td>
                    <td>
                      <Badge tone={STATUS_TONE[r.status]} title={r.error ?? undefined}>
                        {r.status}
                      </Badge>
                    </td>
                    <td className={`text-right ${pnlClass(m?.net_pnl)}`}>{signedMoney(m?.net_pnl)}</td>
                    <td className={`text-right ${pnlClass(m?.total_return)}`}>{pct(m?.total_return)}</td>
                    <td className="text-right text-down">{pct(m?.max_drawdown)}</td>
                    <td className="text-right">{num(m?.sharpe)}</td>
                    <td className="text-right">{pct(m?.win_rate, 0)}</td>
                    <td className="text-right">{m?.trades ?? "—"}</td>
                    <td className="px-2 text-right">
                      <Button size="icon" variant="ghost" onClick={() => remove.mutate(r.id)}>
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}
