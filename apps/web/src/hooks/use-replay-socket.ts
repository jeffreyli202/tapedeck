"use client";

import { useCallback, useEffect, useRef } from "react";

import { wsUrl } from "@/lib/api";
import type { ReplayEvent } from "@/lib/types";
import { useReplay } from "@/stores/replay";

export type Command = { action: "play" | "pause" | "speed" | "step" | "seek" | "next_day"; value?: number };

export function useReplaySocket(sessionId: string) {
  const ws = useRef<WebSocket | null>(null);
  const { apply, setConnected, reset } = useReplay.getState();

  useEffect(() => {
    let closed = false;
    let retry = 0;
    let timer: ReturnType<typeof setTimeout>;
    reset();

    const connect = () => {
      const sock = new WebSocket(wsUrl(`/ws/replay/${sessionId}`));
      ws.current = sock;
      sock.onopen = () => {
        retry = 0;
        setConnected(true);
      };
      sock.onmessage = (msg) => apply(JSON.parse(msg.data) as ReplayEvent);
      sock.onclose = () => {
        setConnected(false);
        if (closed) return;
        timer = setTimeout(connect, Math.min(10_000, 500 * 2 ** retry++));
      };
    };
    connect();
    return () => {
      closed = true;
      clearTimeout(timer);
      ws.current?.close();
    };
  }, [sessionId, apply, setConnected, reset]);

  return useCallback((cmd: Command) => {
    if (ws.current?.readyState === WebSocket.OPEN) ws.current.send(JSON.stringify(cmd));
  }, []);
}
