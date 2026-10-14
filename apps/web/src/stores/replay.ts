import { create } from "zustand";

import type { Account, Bar, ClockState, Fill, Order, ReplayEvent, Snapshot } from "@/lib/types";

type ReplayStore = {
  session: Snapshot["session"] | null;
  state: ClockState | null;
  bars: Bar[];
  account: Account | null;
  orders: Order[];
  fills: Fill[];
  connected: boolean;
  error: string | null;
  /** Bumped on snapshot/reset so the chart knows to redraw instead of append. */
  epoch: number;
  apply: (e: ReplayEvent) => void;
  setConnected: (c: boolean) => void;
  setError: (e: string | null) => void;
  reset: () => void;
};

const empty = {
  session: null,
  state: null,
  bars: [],
  account: null,
  orders: [],
  fills: [],
  connected: false,
  error: null,
  epoch: 0,
};

export const useReplay = create<ReplayStore>((set) => ({
  ...empty,
  apply: (e) =>
    set((s) => {
      switch (e.type) {
        case "snapshot":
        case "reset":
          return {
            session: e.session,
            state: e.state,
            bars: e.bars,
            account: e.account,
            orders: e.orders,
            fills: e.fills,
            error: null,
            epoch: s.epoch + 1,
          };
        case "tick":
          // Ticks published before our snapshot was taken are already included in it.
          if (s.state && e.state.index <= s.state.index) return {};
          return {
            state: e.state,
            bars: [...s.bars, e.bar],
            account: e.account,
            fills: e.fills.length ? [...s.fills, ...e.fills] : s.fills,
            orders: e.orders ?? s.orders,
          };
        case "state":
          return { state: e.state };
        case "orders":
          return { orders: e.orders, ...(e.account ? { account: e.account } : {}) };
        case "error":
          return { error: e.message };
      }
    }),
  setConnected: (connected) => set({ connected }),
  setError: (error) => set({ error }),
  reset: () => set(empty),
}));
