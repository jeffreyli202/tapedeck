"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input, Label, Textarea } from "@/components/ui/input";
import { api } from "@/lib/api";
import type { Note } from "@/lib/types";

type Props = {
  initial?: Partial<Note>;
  sessionId?: string | null;
  runId?: string | null;
  tradeId?: number | null;
  screenshot?: string | null;
  onDone: (note: Note) => void;
  onCancel?: () => void;
};

export function NoteForm({ initial, sessionId, runId, tradeId, screenshot, onDone, onCancel }: Props) {
  const qc = useQueryClient();
  const [title, setTitle] = useState(initial?.title ?? "");
  const [body, setBody] = useState(initial?.body ?? "");
  const [tags, setTags] = useState((initial?.tags ?? []).join(", "));
  const shot = screenshot ?? initial?.screenshot ?? null;

  const save = useMutation({
    mutationFn: () => {
      const payload = { title, body, tags: tags.split(",").map((t) => t.trim()).filter(Boolean) };
      return initial?.id
        ? api<Note>(`/journal/${initial.id}`, { method: "PATCH", json: payload })
        : api<Note>("/journal", {
            method: "POST",
            json: { ...payload, session_id: sessionId ?? null, run_id: runId ?? null, trade_id: tradeId ?? null, screenshot: shot },
          });
    },
    onSuccess: (note) => {
      qc.invalidateQueries({ queryKey: ["journal"] });
      qc.invalidateQueries({ queryKey: ["analytics"] });
      onDone(note);
    },
  });

  return (
    <form
      className="space-y-3"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate();
      }}
    >
      {/* eslint-disable-next-line @next/next/no-img-element */}
      {shot && <img src={shot} alt="Chart at time of note" className="w-full rounded border border-border" />}
      <div>
        <Label>Title</Label>
        <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Faded the opening drive" />
      </div>
      <div>
        <Label>Notes</Label>
        <Textarea rows={5} value={body} onChange={(e) => setBody(e.target.value)} placeholder="Setup, why I entered, what I'd do differently…" />
      </div>
      <div>
        <Label>Tags (comma separated)</Label>
        <Input value={tags} onChange={(e) => setTags(e.target.value)} placeholder="orb, a+ setup, chased" />
      </div>
      {save.error && <p className="text-xs text-down">{(save.error as Error).message}</p>}
      <div className="flex justify-end gap-2">
        {onCancel && (
          <Button type="button" variant="ghost" onClick={onCancel}>
            Cancel
          </Button>
        )}
        <Button type="submit" disabled={save.isPending}>
          Save note
        </Button>
      </div>
    </form>
  );
}

export function Modal({ title, children, onClose }: { title: string; children: React.ReactNode; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onMouseDown={onClose}>
      <div
        className="max-h-[90vh] w-full max-w-xl overflow-auto rounded-lg border border-border bg-panel p-4"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <h3 className="mb-3 font-medium">{title}</h3>
        {children}
      </div>
    </div>
  );
}
