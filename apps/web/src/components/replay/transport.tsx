"use client";

import { ChevronsRight, Pause, Play, SkipForward, StepForward } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/input";
import type { Command } from "@/hooks/use-replay-socket";
import { etDate, etTime } from "@/lib/format";
import { toChartTime } from "@/lib/indicators";
import type { ClockState } from "@/lib/types";

export const SPEEDS = [1, 2, 5, 10, 30, 60];

/** Epoch seconds for HH:MM New York time on the cursor's trading day. */
function sameDayAt(cursor: number, hhmm: string): number | null {
  const m = hhmm.match(/^(\d{1,2}):(\d{2})$/);
  if (!m) return null;
  const wall = toChartTime(cursor);
  const offset = wall - cursor;
  const midnight = wall - (wall % 86400);
  return midnight + +m[1] * 3600 + +m[2] * 60 - offset;
}

export function Transport({ state, send }: { state: ClockState; send: (c: Command) => void }) {
  const [goto, setGoto] = useState("");
  const playing = state.status === "playing";
  const finished = state.status === "finished";
  const progress = state.total > 1 ? state.index / (state.total - 1) : 1;

  const seekTo = () => {
    const t = sameDayAt(state.cursor_ts, goto);
    if (t && t > state.cursor_ts) send({ action: "seek", value: t });
  };

  return (
    <div className="flex flex-wrap items-center gap-2 border-t border-border px-3 py-2">
      <Button
        size="icon"
        variant={playing ? "outline" : "default"}
        disabled={finished}
        onClick={() => send({ action: playing ? "pause" : "play" })}
        title="Play / pause (Space)"
      >
        {playing ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
      </Button>
      <Button size="icon" variant="outline" disabled={finished} onClick={() => send({ action: "step", value: 1 })} title="Step 1 bar (→)">
        <StepForward className="h-4 w-4" />
      </Button>
      <Button size="sm" variant="outline" disabled={finished} onClick={() => send({ action: "step", value: 5 })} title="Step 5 bars (Shift+→)">
        +5
      </Button>
      <Button size="sm" variant="outline" disabled={finished} onClick={() => send({ action: "seek", value: state.cursor_ts + 1800 })}>
        +30m
      </Button>
      <Button size="sm" variant="outline" disabled={finished} onClick={() => send({ action: "next_day" })} title="Next trading day (N)">
        <SkipForward className="h-3.5 w-3.5" /> Next day
      </Button>
      <Select
        className="h-8 w-20"
        value={state.speed}
        onChange={(e) => send({ action: "speed", value: +e.target.value })}
        title="Speed (↑/↓)"
      >
        {SPEEDS.map((s) => (
          <option key={s} value={s}>
            {s}x
          </option>
        ))}
      </Select>
      <form
        className="flex items-center gap-1"
        onSubmit={(e) => {
          e.preventDefault();
          seekTo();
        }}
      >
        <Input className="h-8 w-20" placeholder="HH:MM" value={goto} onChange={(e) => setGoto(e.target.value)} />
        <Button size="icon" variant="ghost" type="submit" title="Fast-forward to time (resting orders still fill)">
          <ChevronsRight className="h-4 w-4" />
        </Button>
      </form>
      <div className="ml-auto flex items-center gap-3">
        <div className="h-1.5 w-40 overflow-hidden rounded bg-panel-2">
          <div className="h-full bg-accent" style={{ width: `${progress * 100}%` }} />
        </div>
        <div className="num text-sm">
          <span className="text-muted">{etDate(state.cursor_ts)}</span> {etTime(state.cursor_ts + 60)} ET
        </div>
        <span className="text-xs uppercase text-muted">{state.status}</span>
      </div>
    </div>
  );
}
