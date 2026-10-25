import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { api } from "../../lib/api";
import type { GenieResult } from "../../lib/genie";
import { fmtCompact, fmtPct, fmtPrice, pctClass } from "../../lib/format";
import { useApp } from "../../stores/app";
import { Chip, EmptyState, Skeleton } from "../ui/primitives";

const SECTORS = ["Technology", "Financials", "Energy", "Healthcare", "Consumer Staples", "Consumer Discretionary", "Communication", "Industrials", "Materials", "Utilities", "Real Estate"];
const NUMS = new Set(["last", "chg_pct_1d", "ret_1m", "ret_1y", "market_cap"]);

export default function Screener() {
  const app = useApp();
  const [sector, setSector] = useState<string | null>(null);
  const [sortCol, setSortCol] = useState("market_cap");
  const [dir, setDir] = useState<-1 | 1>(-1);
  const { data, isLoading } = useQuery({
    queryKey: ["screener", sector],
    queryFn: () => api<GenieResult>(`/screener${sector ? `?sector=${encodeURIComponent(sector)}` : ""}`),
  });

  const cols = data?.columns.map((c) => c.name) ?? [];
  const rows = useMemo(() => {
    const i = cols.indexOf(sortCol);
    if (i < 0 || !data) return data?.rows ?? [];
    return [...data.rows].sort((a, b) => {
      const x = a[i], y = b[i];
      const cmp = typeof x === "number" && typeof y === "number" ? x - y : String(x ?? "").localeCompare(String(y ?? ""));
      return cmp * dir;
    });
  }, [data, sortCol, dir, cols]);

  const fmt = (name: string, v: unknown) => {
    if (v == null) return "—";
    if (name === "last") return fmtPrice(Number(v));
    if (name === "market_cap") return fmtCompact(Number(v));
    if (name.startsWith("ret_") || name === "chg_pct_1d") return fmtPct(Number(v));
    return String(v);
  };

  return (
    <div className="flex h-full flex-col" aria-label="Screener">
      <div className="flex flex-wrap items-center gap-1 px-2 py-1">
        <Chip tone={sector === null ? "accent" : "neutral"} onRemove={sector ? () => setSector(null) : undefined}>
          All sectors
        </Chip>
        {SECTORS.map((s) => (
          <button key={s} onClick={() => setSector(s === sector ? null : s)}>
            <Chip tone={sector === s ? "accent" : "neutral"}>{s}</Chip>
          </button>
        ))}
      </div>
      <div className="min-h-0 flex-1 overflow-auto">
        {isLoading ? (
          <div className="space-y-1 p-2">{Array.from({ length: 10 }).map((_, i) => <Skeleton key={i} className="h-6" />)}</div>
        ) : !rows.length ? (
          <EmptyState title="No matches" hint="Widen the filters." />
        ) : (
          <table className="w-full border-collapse text-[11px]">
            <thead className="sticky top-0 z-10 bg-panel">
              <tr>
                {cols.map((c) => (
                  <th
                    key={c}
                    onClick={() => { setSortCol(c); setDir((d) => (sortCol === c ? (d * -1) as 1 | -1 : -1)); }}
                    className={`cursor-pointer border-b border-hairline px-2 py-1 text-left text-[9px] font-semibold uppercase tracking-wide text-fg-3 hover:text-fg ${NUMS.has(c) ? "text-right" : ""}`}
                  >
                    {c.replace(/_/g, " ")} {sortCol === c && (dir === -1 ? "▼" : "▲")}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => {
                const sym = String(r[cols.indexOf("symbol")]);
                return (
                  <tr key={i} className={`cursor-pointer hover:bg-elevated ${sym === app.symbol ? "bg-accent/10" : ""}`} onClick={() => app.setSymbol(sym)}>
                    {r.map((v, ci) => (
                      <td
                        key={ci}
                        className={`border-b border-hairline/40 px-2 py-1 ${
                          NUMS.has(cols[ci])
                            ? `num text-right ${(cols[ci].startsWith("ret_") || cols[ci] === "chg_pct_1d") ? pctClass(Number(v)) : ""}`
                            : "text-fg-2"
                        }`}
                      >
                        {fmt(cols[ci], v)}
                      </td>
                    ))}
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
