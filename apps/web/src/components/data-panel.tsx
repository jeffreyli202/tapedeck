"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label, Select } from "@/components/ui/input";
import { api } from "@/lib/api";
import type { DataStatus, JobStatus } from "@/lib/types";

function useJob(jobId: string | null, onDone: () => void) {
  const { data } = useQuery({
    queryKey: ["job", jobId],
    queryFn: () => api<JobStatus>(`/data/jobs/${jobId}`),
    enabled: !!jobId,
    refetchInterval: (q) => (q.state.data?.status === "complete" ? false : 1000),
  });
  const done = data?.status === "complete";
  useEffect(() => {
    if (done) onDone();
  }, [done, onDone]);
  return data;
}

export function DataPanel() {
  const qc = useQueryClient();
  const { data: status } = useQuery({ queryKey: ["data-status"], queryFn: () => api<DataStatus>("/data/status") });
  const [jobId, setJobId] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [symbol, setSymbol] = useState("SPY");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [day, setDay] = useState("");
  const [days, setDays] = useState(20);

  const job = useJob(jobId, () => {
    qc.invalidateQueries({ queryKey: ["data-status"] });
    qc.invalidateQueries({ queryKey: ["days"] });
  });

  const run = async (body: Record<string, unknown>) => {
    setErr(null);
    try {
      const { job_id } = await api<{ job_id: string }>("/data/jobs", { method: "POST", json: body });
      setJobId(job_id);
    } catch (e) {
      setErr((e as Error).message);
    }
  };

  const busy = !!job && job.status !== "complete";

  return (
    <Card>
      <CardHeader>
        <CardTitle>Market data</CardTitle>
        {status && (
          <Badge tone={status.alpaca_configured ? "up" : "accent"}>
            {status.alpaca_configured ? "Alpaca connected" : "No Alpaca keys: synthetic data only"}
          </Badge>
        )}
      </CardHeader>
      <CardContent className="space-y-4">
        <table className="num w-full text-xs">
          <thead className="text-muted">
            <tr className="text-left">
              <th className="font-normal">Series</th>
              <th className="font-normal">Source</th>
              <th className="font-normal">Range</th>
              <th className="text-right font-normal">Days</th>
            </tr>
          </thead>
          <tbody>
            {status?.bars.map((b) => (
              <tr key={b.symbol + b.source} className="border-t border-border/50">
                <td className="py-1">{b.symbol} 1m</td>
                <td>
                  <Badge tone={b.source === "synthetic" ? "accent" : "up"}>{b.source}</Badge>
                </td>
                <td>
                  {b.first.slice(0, 10)} → {b.last.slice(0, 10)}
                </td>
                <td className="text-right">{b.days}</td>
              </tr>
            ))}
            {status?.iv.map((r) => (
              <tr key={r.index} className="border-t border-border/50">
                <td className="py-1">{r.index} daily</td>
                <td>IV proxy</td>
                <td>
                  {r.first} → {r.last}
                </td>
                <td className="text-right">{r.days}</td>
              </tr>
            ))}
            {status?.options.map((o) => (
              <tr key={o.underlying} className="border-t border-border/50">
                <td className="py-1">{o.underlying} options</td>
                <td>{o.contracts} contracts</td>
                <td>
                  {o.first.slice(0, 10)} → {o.last.slice(0, 10)}
                </td>
                <td className="text-right">{o.bars} bars</td>
              </tr>
            ))}
            {status && !status.bars.length && (
              <tr>
                <td colSpan={4} className="py-2 text-muted">
                  No bars yet. Seed synthetic data or ingest from Alpaca.
                </td>
              </tr>
            )}
          </tbody>
        </table>

        <div className="grid gap-3 md:grid-cols-2">
          <div className="space-y-2 rounded border border-border p-3">
            <div className="text-xs font-medium">Quick start</div>
            <div className="flex items-end gap-2">
              <div className="w-20">
                <Label>Days</Label>
                <Input type="number" min={1} max={250} value={days} onChange={(e) => setDays(+e.target.value)} />
              </div>
              <Button variant="outline" disabled={busy} onClick={() => run({ kind: "synthetic", days })}>
                Seed synthetic SPY/QQQ
              </Button>
            </div>
            <Button variant="outline" disabled={busy} onClick={() => run({ kind: "iv" })}>
              Download VIX / VXN history
            </Button>
          </div>
          <div className="space-y-2 rounded border border-border p-3">
            <div className="text-xs font-medium">Alpaca (free tier)</div>
            <div className="grid grid-cols-3 gap-2">
              <Select value={symbol} onChange={(e) => setSymbol(e.target.value)}>
                <option>SPY</option>
                <option>QQQ</option>
              </Select>
              <Input type="date" value={start} onChange={(e) => setStart(e.target.value)} />
              <Input type="date" value={end} onChange={(e) => setEnd(e.target.value)} />
            </div>
            <div className="flex flex-wrap gap-2">
              <Button
                variant="outline"
                disabled={busy || !status?.alpaca_configured || !start || !end}
                onClick={() => run({ kind: "bars", symbol, start, end })}
              >
                Ingest 1m bars
              </Button>
              <Input type="date" className="w-40" value={day} onChange={(e) => setDay(e.target.value)} />
              <Button
                variant="outline"
                disabled={busy || !status?.alpaca_configured || !day}
                onClick={() => run({ kind: "options", symbol, day })}
                title="Real option bars exist from about Feb 2024"
              >
                Ingest option bars
              </Button>
            </div>
          </div>
        </div>
        {job && (
          <p className="text-xs text-muted">
            Job {job.status.replace("_", " ")}
            {job.message ? `: ${job.message}` : ""}
            {job.success === false && <span className="text-down"> failed: {String(job.result)}</span>}
          </p>
        )}
        {err && <p className="text-xs text-down">{err}</p>}
      </CardContent>
    </Card>
  );
}
