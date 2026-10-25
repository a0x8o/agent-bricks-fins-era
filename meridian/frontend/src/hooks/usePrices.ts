import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";

export interface Bar {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  adj_close: number;
  volume: number;
}

export interface PricesResponse {
  symbol: string;
  interval: string;
  bars: Bar[];
  as_of: string | null;
}

export function usePrices(symbol: string, range: string, interval: string, until?: string | null) {
  return useQuery({
    queryKey: ["prices", symbol, range, interval, until ?? null],
    queryFn: () =>
      api<PricesResponse>(
        `/prices/${symbol}?interval=${interval}&range=${range}${until ? `&until=${until}` : ""}`,
      ),
    enabled: !!symbol,
    staleTime: 60_000,
  });
}

export interface IndicatorPoint {
  time: string;
  value: number | null;
  extra: Record<string, number | null>;
}

export function useIndicator(
  symbol: string,
  type: string,
  params: Record<string, number>,
  range: string,
  until?: string | null,
) {
  return useQuery({
    queryKey: ["indicator", symbol, type, params, range, until ?? null],
    queryFn: () =>
      api<{ points: IndicatorPoint[] }>(
        `/indicators/${symbol}?type=${type}&range=${range}&params=${encodeURIComponent(
          JSON.stringify(params),
        )}${until ? `&until=${until}` : ""}`,
      ),
    enabled: !!symbol && !!type,
    staleTime: 60_000,
  });
}

export interface Quote {
  symbol: string;
  name: string;
  last: number;
  change: number;
  change_pct: number;
  currency: string;
  market_status: string;
  perf: { w1: number | null; m1: number | null; m3: number | null; m6: number | null; ytd: number | null; y1: number | null };
  technicals: { score: number; label: string };
  news_headline: string | null;
  as_of: string;
}

export function useQuote(symbol: string, until?: string | null) {
  return useQuery({
    queryKey: ["quote", symbol, until ?? null],
    queryFn: () => api<Quote>(`/quote/${symbol}${until ? `?until=${until}` : ""}`),
    enabled: !!symbol,
  });
}

export interface Security {
  symbol: string;
  name: string;
  asset_class: string;
  sector: string | null;
  exchange: string | null;
}

export function useSecurities(query: string, enabled = true) {
  return useQuery({
    queryKey: ["securities", query],
    queryFn: () => api<Security[]>(`/securities?query=${encodeURIComponent(query)}`),
    enabled,
    staleTime: 120_000,
  });
}

export function useEvents(symbol: string) {
  return useQuery({
    queryKey: ["events", symbol],
    queryFn: () =>
      api<{ event_date: string; kind: string; detail: string; sentiment: string }[]>(
        `/events/${symbol}`,
      ),
    enabled: !!symbol,
    staleTime: 300_000,
  });
}
