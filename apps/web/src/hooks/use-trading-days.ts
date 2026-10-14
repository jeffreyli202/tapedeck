"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";

export function useTradingDays(symbol: string) {
  return useQuery({ queryKey: ["days", symbol], queryFn: () => api<string[]>(`/data/days?symbol=${symbol}`) });
}
