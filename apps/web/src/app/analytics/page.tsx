"use client";

import { useQuery } from "@tanstack/react-query";
import { NotebookPen } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { DrawdownChart, EquityChart, GroupBars, Heatmap, PnlHistogram } from "@/components/analytics/charts";
import { Modal, NoteForm } from "@/components/journal/note-form";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select } from "@/components/ui/input";
import { api } from "@/lib/api";
import { describeSymbol, duration, etDateTime, money, num, pct, pnlClass, signedMoney } from "@/lib/format";
import type { Analytics, BacktestRun, Metrics, SessionSummary, Trade } from "@/lib/types";
import { cn } from "@/lib/utils";

function MetricCards({ m }: { m: Metrics }) {
  const cards: [string, string, string?][] = [
    ["Net P&L", signedMoney(m.net_pnl), pnlClass(m.net_pnl)],
    ["Total return", pct(m.total_return), pnlClass(m.total_return)],
    ["CAGR", pct(m.cagr)],
    ["Max drawdown", pct(m.max_drawdown), "text-down"],
    ["DD duration", duration(m.max_drawdown_duration_s)],
    ["Sharpe", num(m.sharpe)],
    ["Sortino", num(m.sortino)],
    ["Win rate", pct(m.win_rate, 1)],
    ["Profit factor", num(m.profit_factor)],
    ["Expectancy", signedMoney(m.expectancy), pnlClass(m.expectancy)],
    ["Avg win / loss", `${money(m.avg_win)} / ${money(m.avg_loss)}`],
    ["Trades", String(m.trades)],
    ["Exposure", pct(m.exposure, 0)],
    ["Days", String(m.trading_days)],
  ];
  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-7">
      {cards.map(([label, value, cls]) => (
        <Card key={label} className="px-3 py-2">
          <div className="text-[11px] uppercase text-muted">{label}</div>
          <div className={cn("num text-base font-medium", cls)}>{value}</div>
        </Card>
      ))}
    </div>
  );
}

function TradesTable({ trades, onNote }: { trades: Trade[]; onNote: (t: Trade) => void }) {
  if (!trades.length) return <p className="p-4 text-sm text-muted">No closed trades.</p>;
  return (
    <div className="max-h-96 overflow-auto">
      <table className="num w-full text-xs">
        <thead className="sticky top-0 bg-panel text-muted">
          <tr className="text-left">
            <th className="px-4 py-1.5 font-normal">Entry</th>
            <th className="font-normal">Exit</th>
            <th className="font-normal">Symbol</th>
            <th className="font-normal">Side</th>
            <th className="text-right font-normal">Qty</th>
            <th className="text-right font-normal">Entry px</th>
            <th className="text-right font-normal">Exit px</th>
            <th className="text-right font-normal">P&L</th>
            <th className="text-right font-normal">Fees</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {[...trades].reverse().map((t) => (
            <tr key={t.id} className="border-t border-border/50">
              <td className="px-4 py-1">{etDateTime(t.entry_t)}</td>
              <td className="text-muted">{etDateTime(t.exit_t)}</td>
              <td>{describeSymbol(t.symbol)}</td>
              <td className={t.direction === "long" ? "text-up" : "text-down"}>{t.direction}</td>
              <td className="text-right">{t.qty}</td>
              <td className="text-right">{num(t.entry_price)}</td>
              <td className="text-right">{num(t.exit_price)}</td>
              <td className={`text-right ${pnlClass(t.pnl)}`}>{signedMoney(t.pnl)}</td>
              <td className="text-right text-muted">{num(t.commission)}</td>
              <td className="px-2 text-right">
                <button
                  onClick={() => onNote(t)}
                  className={cn("hover:text-accent", t.has_note ? "text-accent" : "text-muted")}
                  title={t.has_note ? "Has journal note" : "Add journal note"}
                >
                  <NotebookPen className="h-3.5 w-3.5" />
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function AnalyticsView() {
  const router = useRouter();
  const params = useSearchParams();
  const runId = params.get("run");
  const sessionId = params.get("session");
  const [noteFor, setNoteFor] = useState<Trade | null>(null);

  const { data: runs = [] } = useQuery({ queryKey: ["backtests"], queryFn: () => api<BacktestRun[]>("/backtests") });
  const { data: sessions = [] } = useQuery({ queryKey: ["sessions"], queryFn: () => api<SessionSummary[]>("/sessions") });
  const query = runId ? `run_id=${runId}` : sessionId ? `session_id=${sessionId}` : null;
  const { data, error } = useQuery({
    queryKey: ["analytics", query],
    queryFn: () => api<Analytics>(`/analytics?${query}`),
    enabled: !!query,
  });

  const value = runId ? `run:${runId}` : sessionId ? `session:${sessionId}` : "";
  const choose = (v: string) => {
    const [kind, id] = v.split(":");
    router.push(kind ? `/analytics?${kind}=${id}` : "/analytics");
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <h1 className="text-lg font-semibold">Analytics</h1>
        <Select className="w-96" value={value} onChange={(e) => choose(e.target.value)}>
          <option value="">Choose a replay session or backtest…</option>
          <optgroup label="Replay sessions">
            {sessions.map((s) => (
              <option key={s.id} value={`session:${s.id}`}>
                {s.symbol} replay {s.start_date} · {s.id}
              </option>
            ))}
          </optgroup>
          <optgroup label="Backtests">
            {runs
              .filter((r) => r.status === "done")
              .map((r) => (
                <option key={r.id} value={`run:${r.id}`}>
                  {r.strategy} {r.symbol} {r.start_date}→{r.end_date} · {r.id}
                </option>
              ))}
          </optgroup>
        </Select>
      </div>
      {error && <p className="text-sm text-down">{(error as Error).message}</p>}
      {!query && <p className="text-sm text-muted">Pick a session or backtest to analyze.</p>}
      {data && (
        <>
          <MetricCards m={data.metrics} />
          <div className="grid gap-4 xl:grid-cols-[2fr_1fr]">
            <Card>
              <CardHeader>
                <CardTitle>Equity curve</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                <EquityChart data={data.equity} start={data.metrics.starting_equity} />
                <div className="text-[11px] uppercase text-muted">Underwater (drawdown from peak)</div>
                <DrawdownChart data={data.drawdown} />
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>Trade P&L distribution</CardTitle>
              </CardHeader>
              <CardContent>
                <PnlHistogram data={data.histogram} />
                <div className="mt-4 text-[11px] uppercase text-muted">By weekday</div>
                <GroupBars data={data.by_weekday} />
              </CardContent>
            </Card>
          </div>
          <div className="grid gap-4 xl:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>P&L by entry time (ET)</CardTitle>
              </CardHeader>
              <CardContent>
                <GroupBars data={data.by_time_of_day} />
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>Heatmap: weekday × time of day</CardTitle>
              </CardHeader>
              <CardContent>
                <Heatmap data={data.heatmap} />
              </CardContent>
            </Card>
          </div>
          <Card>
            <CardHeader>
              <CardTitle>Trades ({data.trades.length})</CardTitle>
            </CardHeader>
            <TradesTable trades={data.trades} onNote={setNoteFor} />
          </Card>
        </>
      )}
      {noteFor && (
        <Modal title={`Note: ${describeSymbol(noteFor.symbol)} ${noteFor.direction} ${signedMoney(noteFor.pnl)}`} onClose={() => setNoteFor(null)}>
          <NoteForm
            tradeId={noteFor.id}
            sessionId={sessionId}
            runId={runId}
            onDone={() => setNoteFor(null)}
            onCancel={() => setNoteFor(null)}
          />
        </Modal>
      )}
    </div>
  );
}

export default function AnalyticsPage() {
  return (
    <Suspense>
      <AnalyticsView />
    </Suspense>
  );
}
