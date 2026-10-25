import { useQuery } from "@tanstack/react-query";
import ReactECharts from "echarts-for-react";
import { api } from "../../lib/api";
import type { GenieResult } from "../../lib/genie";
import { fmtCompact, fmtCurrency, fmtPct, fmtPrice, pctClass } from "../../lib/format";
import { EmptyState, Skeleton } from "../ui/primitives";

export default function Portfolio() {
  const { data, isLoading } = useQuery({
    queryKey: ["portfolio", "demo-core"],
    queryFn: () => api<GenieResult>("/portfolio/demo-core"),
  });

  if (isLoading) return <div className="space-y-2 p-3"><Skeleton className="h-6 w-52" /><Skeleton className="h-32" /></div>;
  if (!data?.row_count) return <EmptyState title="Portfolio is empty" hint="The demo portfolio has no positions." />;

  const c = (n: string) => data.columns.findIndex((x) => x.name === n);
  const mv = data.rows.reduce((s, r) => s + Number(r[c("market_value")]), 0);
  const pnl = data.rows.reduce((s, r) => s + Number(r[c("unrealized_pnl")]), 0);
  const top = data.rows.map((r) => ({ sym: String(r[c("symbol")]), w: Number(r[c("weight")]) * 100, pnl: Number(r[c("unrealized_pnl")]), sector: String(r[c("sector")]) }));
  const bySector = Object.entries(
    top.reduce<Record<string, number>>((m, t) => ((m[t.sector] = (m[t.sector] ?? 0) + t.w), m), {}),
  ).map(([name, value]) => ({ name, value: +value.toFixed(1) }));

  const donut = {
    backgroundColor: "transparent",
    tooltip: { backgroundColor: "#171b21", borderColor: "#232830", textStyle: { color: "#e6e9ee", fontSize: 11 } },
    color: ["#3b82f6", "#8b5cf6", "#f59e0b", "#14b8a6", "#f472b6", "#a3e635", "#22c55e", "#ef4444"],
    series: [{ type: "pie", radius: ["50%", "78%"], data: bySector, label: { fontSize: 9, color: "#9aa3b2" } }],
    legend: { bottom: 0, textStyle: { fontSize: 9, color: "#9aa3b2" }, type: "scroll" as const },
  };
  const contrib = {
    backgroundColor: "transparent",
    grid: { left: 8, right: 8, top: 10, bottom: 20, containLabel: true },
    tooltip: { backgroundColor: "#171b21", borderColor: "#232830", textStyle: { color: "#e6e9ee", fontSize: 11 } },
    xAxis: { type: "category", data: top.map((t) => t.sym), axisLabel: { fontSize: 9, color: "#8a94a3" } },
    yAxis: { type: "value", axisLabel: { fontSize: 9, color: "#8a94a3" }, splitLine: { lineStyle: { color: "#161a20" } } },
    series: [{ type: "bar", data: top.map((t) => ({ value: +t.pnl.toFixed(0), itemStyle: { color: t.pnl >= 0 ? "#22c55e" : "#ef4444" } })), barMaxWidth: 26 }],
  };

  return (
    <div className="flex h-full flex-col overflow-auto p-2" aria-label="Portfolio">
      <div className="grid grid-cols-4 gap-1.5">
        <Kpi label="Market value" value={fmtCurrency(mv)} />
        <Kpi label="Total P&L" value={fmtCurrency(pnl)} cls={pctClass(pnl)} />
        <Kpi label="Positions" value={String(data.row_count)} />
        <Kpi label="Top weight" value={`${top[0]?.sym} · ${fmtPct(top[0]?.w ?? 0, false)}`} />
      </div>
      <div className="mt-1.5 grid min-h-0 flex-1 grid-cols-[1fr_1fr_1.4fr] gap-1.5">
        <div className="rounded border border-hairline bg-elevated/40 p-1">
          <div className="px-1 py-0.5 text-[10px] text-fg-3">Allocation by sector</div>
          <ReactECharts option={donut} style={{ height: "85%" }} notMerge />
        </div>
        <div className="rounded border border-hairline bg-elevated/40 p-1">
          <div className="px-1 py-0.5 text-[10px] text-fg-3">P&L contribution</div>
          <ReactECharts option={contrib} style={{ height: "85%" }} notMerge />
        </div>
        <div className="overflow-auto rounded border border-hairline bg-elevated/40">
          <table className="w-full border-collapse text-[11px]">
            <thead className="sticky top-0 bg-elevated">
              <tr>{["Symbol", "Qty", "Cost", "Value", "P&L", "Weight"].map((h) => (
                <th key={h} className="border-b border-hairline px-2 py-1 text-right text-[9px] font-semibold uppercase tracking-wide text-fg-3 first:text-left">{h}</th>
              ))}</tr>
            </thead>
            <tbody>
              {data.rows.map((r, i) => (
                <tr key={i} className="hover:bg-hairline/40">
                  <td className="num border-b border-hairline/40 px-2 py-1 font-medium">{String(r[c("symbol")])}</td>
                  <td className="num border-b border-hairline/40 px-2 py-1 text-right">{String(r[c("quantity")])}</td>
                  <td className="num border-b border-hairline/40 px-2 py-1 text-right text-fg-2">{fmtCompact(Number(r[c("cost_basis")]))}</td>
                  <td className="num border-b border-hairline/40 px-2 py-1 text-right">{fmtPrice(Number(r[c("market_value")]))}</td>
                  <td className={`num border-b border-hairline/40 px-2 py-1 text-right ${pctClass(Number(r[c("unrealized_pnl")]))}`}>{fmtCurrency(Number(r[c("unrealized_pnl")]))}</td>
                  <td className="num border-b border-hairline/40 px-2 py-1 text-right text-fg-2">{fmtPct(Number(r[c("weight")]) * 100, false)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function Kpi({ label, value, cls = "" }: { label: string; value: string; cls?: string }) {
  return (
    <div className="rounded border border-hairline bg-elevated/40 px-2.5 py-1.5">
      <div className="text-[9px] uppercase tracking-wide text-fg-3">{label}</div>
      <div className={`num text-[15px] font-semibold ${cls}`}>{value}</div>
    </div>
  );
}
