"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { DataPanel } from "@/components/data-panel";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label, Select } from "@/components/ui/input";
import { api } from "@/lib/api";
import { etDateTime, money, pnlClass, signedMoney } from "@/lib/format";
import { useTradingDays } from "@/hooks/use-trading-days";
import type { SessionSummary } from "@/lib/types";

function NewSession() {
  const router = useRouter();
  const [symbol, setSymbol] = useState("SPY");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [cash, setCash] = useState(100_000);
  const [speed, setSpeed] = useState(10);
  const { data: days = [] } = useTradingDays(symbol);
  const startDay = start || days[days.length - 1] || "";

  const create = useMutation({
    mutationFn: () =>
      api<SessionSummary>("/sessions", {
        method: "POST",
        json: { symbol, start_date: startDay, end_date: end || null, starting_cash: cash, speed },
      }),
    onSuccess: (s) => router.push(`/replay/${s.id}`),
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>New replay session</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <Label>Symbol</Label>
            <Select value={symbol} onChange={(e) => setSymbol(e.target.value)}>
              <option>SPY</option>
              <option>QQQ</option>
            </Select>
          </div>
          <div>
            <Label>Starting cash</Label>
            <Input type="number" value={cash} onChange={(e) => setCash(+e.target.value)} className="num" />
          </div>
          <div>
            <Label>Start day</Label>
            <Select value={startDay} onChange={(e) => setStart(e.target.value)} disabled={!days.length}>
              {[...days].reverse().map((d) => (
                <option key={d}>{d}</option>
              ))}
            </Select>
          </div>
          <div>
            <Label>End day (optional, multi-day)</Label>
            <Select value={end} onChange={(e) => setEnd(e.target.value)} disabled={!days.length}>
              <option value="">Same day</option>
              {[...days]
                .reverse()
                .filter((d) => d > startDay)
                .map((d) => (
                  <option key={d}>{d}</option>
                ))}
            </Select>
          </div>
          <div>
            <Label>Speed</Label>
            <Select value={speed} onChange={(e) => setSpeed(+e.target.value)}>
              {[1, 2, 5, 10, 30, 60].map((s) => (
                <option key={s} value={s}>
                  {s}x
                </option>
              ))}
            </Select>
          </div>
        </div>
        <Button className="w-full" disabled={!startDay || create.isPending} onClick={() => create.mutate()}>
          Start replay
        </Button>
        {!days.length && <p className="text-xs text-muted">No {symbol} data yet. Load some below.</p>}
        {create.error && <p className="text-xs text-down">{(create.error as Error).message}</p>}
      </CardContent>
    </Card>
  );
}

function SessionList() {
  const qc = useQueryClient();
  const { data: sessions = [] } = useQuery({ queryKey: ["sessions"], queryFn: () => api<SessionSummary[]>("/sessions") });
  const remove = useMutation({
    mutationFn: (id: string) => api(`/sessions/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["sessions"] }),
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>Sessions</CardTitle>
      </CardHeader>
      {sessions.length === 0 ? (
        <CardContent className="text-sm text-muted">No sessions yet.</CardContent>
      ) : (
        <table className="num w-full text-sm">
          <thead className="text-xs text-muted">
            <tr className="text-left">
              <th className="px-4 py-2 font-normal">Session</th>
              <th className="font-normal">Days</th>
              <th className="font-normal">Cursor</th>
              <th className="font-normal">Status</th>
              <th className="text-right font-normal">Equity</th>
              <th className="text-right font-normal">P&L</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {sessions.map((s) => {
              const pnl = (s.equity ?? s.starting_cash) - s.starting_cash;
              return (
                <tr key={s.id} className="border-t border-border/50 hover:bg-panel-2">
                  <td className="px-4 py-2">
                    <Link href={`/replay/${s.id}`} className="text-accent hover:underline">
                      {s.symbol} · {s.id}
                    </Link>
                  </td>
                  <td>
                    {s.start_date}
                    {s.end_date !== s.start_date && ` → ${s.end_date}`}
                  </td>
                  <td className="text-muted">{s.cursor_ts ? etDateTime(s.cursor_ts + 60) : "start"}</td>
                  <td>
                    <Badge tone={s.status === "finished" ? "neutral" : "accent"}>{s.status}</Badge>
                  </td>
                  <td className="text-right">{money(s.equity)}</td>
                  <td className={`text-right ${pnlClass(pnl)}`}>{signedMoney(pnl)}</td>
                  <td className="px-2 text-right">
                    <Link href={`/analytics?session=${s.id}`} className="mr-2 text-xs text-muted hover:text-foreground">
                      analytics
                    </Link>
                    <Button size="icon" variant="ghost" onClick={() => remove.mutate(s.id)} title="Delete session">
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
  );
}

export default function Home() {
  return (
    <div className="grid gap-4 lg:grid-cols-[380px_1fr]">
      <div className="space-y-4">
        <NewSession />
      </div>
      <div className="space-y-4">
        <SessionList />
        <DataPanel />
      </div>
    </div>
  );
}
