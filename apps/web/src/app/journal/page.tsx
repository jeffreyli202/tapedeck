"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil, Plus, Trash2 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Modal, NoteForm } from "@/components/journal/note-form";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { api } from "@/lib/api";
import { describeSymbol, etDateTime, num, pnlClass, signedMoney } from "@/lib/format";
import type { Note } from "@/lib/types";
import { cn } from "@/lib/utils";

export default function JournalPage() {
  const qc = useQueryClient();
  const [tag, setTag] = useState<string | null>(null);
  const [editing, setEditing] = useState<Partial<Note> | null>(null);
  const { data: notes = [] } = useQuery({ queryKey: ["journal"], queryFn: () => api<Note[]>("/journal") });
  const remove = useMutation({
    mutationFn: (id: number) => api(`/journal/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["journal"] }),
  });

  const tags = [...new Set(notes.flatMap((n) => n.tags))].sort();
  const shown = tag ? notes.filter((n) => n.tags.includes(tag)) : notes;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="mr-2 text-lg font-semibold">Journal</h1>
        <button onClick={() => setTag(null)}>
          <Badge tone={tag === null ? "accent" : "neutral"}>all ({notes.length})</Badge>
        </button>
        {tags.map((t) => (
          <button key={t} onClick={() => setTag(t === tag ? null : t)}>
            <Badge tone={t === tag ? "accent" : "neutral"}>#{t}</Badge>
          </button>
        ))}
        <Button size="sm" className="ml-auto" onClick={() => setEditing({})}>
          <Plus className="h-3.5 w-3.5" /> New note
        </Button>
      </div>
      {shown.length === 0 && (
        <p className="text-sm text-muted">
          No notes yet. Press J on a replay to snapshot the chart, or use the note icon on any trade in Analytics.
        </p>
      )}
      <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-3">
        {shown.map((n) => (
          <Card key={n.id} className="flex flex-col overflow-hidden">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            {n.screenshot && <img src={n.screenshot} alt="" className="max-h-56 w-full border-b border-border object-cover object-right" />}
            <div className="flex-1 space-y-2 p-4">
              <div className="flex items-start justify-between gap-2">
                <h3 className="font-medium">{n.title || "Untitled"}</h3>
                <div className="flex gap-1">
                  <Button size="icon" variant="ghost" onClick={() => setEditing(n)}>
                    <Pencil className="h-3.5 w-3.5" />
                  </Button>
                  <Button size="icon" variant="ghost" onClick={() => remove.mutate(n.id)}>
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </div>
              </div>
              {n.trade && (
                <div className="num flex flex-wrap gap-x-3 rounded bg-panel-2 px-2 py-1 text-xs">
                  <span>{describeSymbol(n.trade.symbol)}</span>
                  <span className={n.trade.direction === "long" ? "text-up" : "text-down"}>
                    {n.trade.direction} {n.trade.qty}
                  </span>
                  <span>
                    {num(n.trade.entry_price)} → {num(n.trade.exit_price)}
                  </span>
                  <span className={pnlClass(n.trade.pnl)}>{signedMoney(n.trade.pnl)}</span>
                  <span className="text-muted">{etDateTime(n.trade.entry_t)}</span>
                </div>
              )}
              <p className="whitespace-pre-wrap text-sm text-foreground/90">{n.body}</p>
              <div className="flex flex-wrap items-center gap-1">
                {n.tags.map((t) => (
                  <Badge key={t}>#{t}</Badge>
                ))}
                <span className={cn("ml-auto text-[11px] text-muted")}>
                  {n.session_id && (
                    <Link href={`/replay/${n.session_id}`} className="hover:text-foreground">
                      replay {n.session_id}
                    </Link>
                  )}
                  {n.run_id && (
                    <Link href={`/analytics?run=${n.run_id}`} className="hover:text-foreground">
                      backtest {n.run_id}
                    </Link>
                  )}
                  {" · "}
                  {new Date(n.created_at).toLocaleString()}
                </span>
              </div>
            </div>
          </Card>
        ))}
      </div>
      {editing && (
        <Modal title={editing.id ? "Edit note" : "New note"} onClose={() => setEditing(null)}>
          <NoteForm initial={editing} onDone={() => setEditing(null)} onCancel={() => setEditing(null)} />
        </Modal>
      )}
    </div>
  );
}
