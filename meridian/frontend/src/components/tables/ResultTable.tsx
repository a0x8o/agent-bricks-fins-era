/** Shared result table — sortable, sticky header, CSV export, truncation notice. */

import { Download } from "lucide-react";
import { useMemo, useState } from "react";
import type { GenieResult } from "../../lib/genie";

export function ResultTable({ result, compact = false }: { result: GenieResult; compact?: boolean }) {
  const [sort, setSort] = useState<{ col: number; dir: 1 | -1 } | null>(null);

  const rows = useMemo(() => {
    if (!sort) return result.rows;
    const { col, dir } = sort;
    return [...result.rows].sort((a, b) => {
      const x = a[col], y = b[col];
      const n = typeof x === "number" && typeof y === "number";
      const cmp = n ? (x as number) - (y as number) : String(x ?? "").localeCompare(String(y ?? ""));
      return cmp * dir;
    });
  }, [result.rows, sort]);

  const csv = () => {
    const esc = (v: unknown) => `"${String(v ?? "").replaceAll('"', '""')}"`;
    const text = [result.columns.map((c) => esc(c.name)).join(","), ...rows.map((r) => r.map(esc).join(","))].join("\n");
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([text], { type: "text/csv" }));
    a.download = "meridian-result.csv";
    a.click();
    URL.revokeObjectURL(a.href);
  };

  const numCol = (i: number) => /INT|DOUBLE|FLOAT|DECIMAL|NUMERIC|REAL|LONG/i.test(result.columns[i]?.type ?? "");

  return (
    <div className="flex flex-col">
      <div className={`overflow-auto ${compact ? "max-h-44" : "max-h-full"}`}>
        <table className="w-full border-collapse text-[11px]">
          <thead className="sticky top-0 z-10 bg-elevated">
            <tr>
              {result.columns.map((c, i) => (
                <th
                  key={c.name}
                  onClick={() => setSort((s) => (s?.col === i ? { col: i, dir: (s.dir * -1) as 1 | -1 } : { col: i, dir: 1 }))}
                  className={`cursor-pointer select-none border-b border-hairline px-2 py-1 text-left text-[9px] font-semibold uppercase tracking-wide text-fg-3 hover:text-fg ${numCol(i) ? "num" : ""}`}
                >
                  {c.name} {sort?.col === i && (sort.dir === 1 ? "▲" : "▼")}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r, ri) => (
              <tr key={ri} className="hover:bg-hairline/40">
                {r.map((v, ci) => (
                  <td key={ci} className={`border-b border-hairline/50 px-2 ${compact ? "py-0.5" : "py-1"} ${numCol(ci) ? "num text-right" : "text-fg-2"}`}>
                    {v == null ? <span className="text-fg-3">—</span> : String(v)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex items-center gap-2 border-t border-hairline px-2 py-0.5">
        <span className="num text-[9px] text-fg-3">{result.row_count} rows{result.truncated ? " · truncated — refine the query" : ""}</span>
        <button onClick={csv} className="ml-auto flex items-center gap-1 text-[9px] text-fg-3 hover:text-fg-2" title="Export CSV">
          <Download size={9} /> CSV
        </button>
      </div>
    </div>
  );
}
