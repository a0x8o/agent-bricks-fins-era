import { useQueries, useQuery } from "@tanstack/react-query";
import { ChevronDown, ChevronRight } from "lucide-react";
import { useState } from "react";
import { api } from "../../lib/api";
import { fmtPct, fmtPrice, pctClass } from "../../lib/format";
import { useApp } from "../../stores/app";
import { usePrices, type Quote } from "../../hooks/usePrices";
import { EmptyState } from "../ui/primitives";

interface WatchlistDef { id: string; name: string; symbols: string[] }

export function Watchlist() {
  const app = useApp();
  const lists = useQuery({ queryKey: ["watchlists"], queryFn: () => api<WatchlistDef[]>("/watchlists") });
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
  const [hover, setHover] = useState<string | null>(null);

  const symbols = (lists.data ?? []).flatMap((l) => l.symbols);
  const quotes = useQueries({
    queries: symbols.map((s) => ({
      queryKey: ["quote", s],
      queryFn: () => api<Quote>(`/quote/${s}`),
      staleTime: 60_000,
      refetchInterval: 30_000,
    })),
  });
  const bySymbol = Object.fromEntries(symbols.map((s, i) => [s, quotes[i]?.data]));

  if (lists.isLoading) return <div className="p-2 space-y-1">{Array.from({ length: 12 }).map((_, i) => <div key={i} className="skeleton h-6" />)}</div>;
  if (!lists.data?.length) return <EmptyState title="No watchlists" hint="Add symbols to start tracking." />;

  return (
    <div className="h-full overflow-auto" aria-label="Watchlist">
      <div className="flex h-7 items-center border-b border-hairline px-2 text-[10px] font-semibold uppercase tracking-wide text-fg-3">
        Watchlist
      </div>
      {(lists.data ?? []).map((l) => (
        <div key={l.id}>
          <button
            className="flex w-full items-center gap-1 px-2 py-1 text-[10px] font-semibold uppercase tracking-wide text-fg-2 hover:bg-elevated"
            onClick={() => setCollapsed((c) => ({ ...c, [l.id]: !c[l.id] }))}
          >
            {collapsed[l.id] ? <ChevronRight size={11} /> : <ChevronDown size={11} />}
            {l.name}
            <span className="ml-auto num text-fg-3">{l.symbols.length}</span>
          </button>
          {!collapsed[l.id] &&
            l.symbols.map((s) => {
              const q = bySymbol[s];
              const active = app.symbol === s;
              return (
                <button
                  key={s}
                  onClick={() => app.setSymbol(s)}
                  onMouseEnter={() => setHover(s)}
                  onMouseLeave={() => setHover(null)}
                  className={`grid w-full grid-cols-[1fr_auto_auto_auto] items-center gap-2 px-2 text-left text-[11px] ${
                    active ? "bg-accent/10" : "hover:bg-elevated"
                  } ${app.density === "compact" ? "h-7" : "h-9"}`}
                >
                  <span className="truncate">
                    <span className="num font-medium">{s}</span>
                    {hover === s && <Sparkline symbol={s} />}
                  </span>
                  <span className="num text-right">{q ? fmtPrice(q.last) : "—"}</span>
                  <span className={`num w-14 text-right ${pctClass(q?.change)}`}>{q ? fmtPrice(q.change) : "—"}</span>
                  <span className={`num w-14 text-right ${pctClass(q?.change_pct)}`}>{q ? fmtPct(q.change_pct) : "—"}</span>
                </button>
              );
            })}
        </div>
      ))}
    </div>
  );
}

function Sparkline({ symbol }: { symbol: string }) {
  const { data } = usePrices(symbol, "5D", "1D");
  const pts = (data?.bars ?? []).map((b) => b.close);
  if (pts.length < 2) return null;
  const min = Math.min(...pts);
  const max = Math.max(...pts);
  const path = pts.map((p, i) => `${(i / (pts.length - 1)) * 48},${14 - ((p - min) / (max - min || 1)) * 12}`).join(" L");
  const up = pts.at(-1)! >= pts[0];
  return (
    <svg width="48" height="14" className="ml-1 inline-block align-middle" aria-hidden>
      <polyline points={path} fill="none" stroke={up ? "var(--up)" : "var(--down)"} strokeWidth="1.2" />
    </svg>
  );
}
