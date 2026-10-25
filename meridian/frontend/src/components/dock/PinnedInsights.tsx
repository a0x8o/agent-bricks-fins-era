import { RefreshCw, Trash2 } from "lucide-react";
import { useState } from "react";
import { api } from "../../lib/api";
import type { GenieResult } from "../../lib/genie";
import { usePins } from "../../stores/pins";
import { ResultTable } from "../tables/ResultTable";
import { EmptyState } from "../ui/primitives";

/** Pinned Genie answer cards — rearrange, rename, refresh (re-runs stored SQL), remove. */
export default function PinnedInsights() {
  const { pins, unpin, rename } = usePins();
  const [refreshing, setRefreshing] = useState<Record<string, GenieResult | undefined>>({});

  const refresh = async (id: string, sql: string | null) => {
    if (!sql) return;
    try {
      const rs = await api<GenieResult>("/genie/run-sql", { method: "POST", body: JSON.stringify({ sql }) });
      setRefreshing((m) => ({ ...m, [id]: rs }));
    } catch {
      /* surfaced in UI below */
    }
  };

  if (!pins.length)
    return <EmptyState title="No pinned insights" hint="Pin an answer card from the Genie panel to build a personal dashboard." />;

  return (
    <div className="grid h-full auto-rows-min grid-cols-2 gap-2 overflow-auto p-2 xl:grid-cols-3" aria-label="Pinned insights">
      {pins.map((p) => (
        <div key={p.id} className="flex flex-col rounded border border-hairline bg-elevated">
          <div className="flex items-center gap-1 border-b border-hairline px-2 py-1">
            <input
              defaultValue={p.title}
              onBlur={(e) => rename(p.id, e.target.value)}
              className="w-full bg-transparent text-[11px] font-medium outline-none"
              aria-label="Insight title"
            />
            <button title="Refresh (re-run stored SQL)" className="text-fg-3 hover:text-fg" onClick={() => refresh(p.id, p.sql)}>
              <RefreshCw size={11} />
            </button>
            <button title="Remove" className="text-fg-3 hover:text-down" onClick={() => unpin(p.id)}>
              <Trash2 size={11} />
            </button>
          </div>
          <div className="px-2 py-1 text-[9px] text-fg-3">{p.question}</div>
          {refreshing[p.id] ? (
            <div className="max-h-40 overflow-auto"><ResultTable result={refreshing[p.id]!} compact /></div>
          ) : p.chartSpec ? (
            <div className="text-[9px] text-fg-3 p-2">Chart: {p.chartSpec.kind} — refresh to re-run the stored query.</div>
          ) : (
            <div className="p-2 text-[10px] text-fg-3">Refresh to re-run the stored query.</div>
          )}
        </div>
      ))}
    </div>
  );
}
