import { useQuery } from "@tanstack/react-query";
import ReactECharts from "echarts-for-react";
import { api } from "../../lib/api";
import type { GenieResult } from "../../lib/genie";
import { fmtCompact } from "../../lib/format";
import { useApp } from "../../stores/app";
import { EmptyState, Skeleton } from "../ui/primitives";

export default function Fundamentals() {
  const app = useApp();
  const { data, isLoading } = useQuery({
    queryKey: ["fundamentals", app.symbol],
    queryFn: () => api<GenieResult>(`/fundamentals/${app.symbol}`),
  });

  if (isLoading) return <div className="space-y-2 p-3"><Skeleton className="h-5 w-40" /><Skeleton className="h-36" /></div>;
  if (!data?.row_count) return <EmptyState title={`No fundamentals for ${app.symbol}`} hint="Equities only — ETFs, futures, FX and crypto have no filings." />;

  const col = (n: string) => data.columns.findIndex((c) => c.name === n);
  const ix = { pe: col("period_end"), rev: col("revenue"), ni: col("net_income"), eps: col("eps_diluted"), fcf: col("free_cash_flow") };
  const rows = data.rows;
  const periods = rows.map((r) => String(r[ix.pe]).slice(0, 7));
  const axis = { axisLabel: { fontSize: 9, color: "#8a94a3" } };
  const base = {
    backgroundColor: "transparent",
    textStyle: { fontSize: 10, color: "#9aa3b2" },
    grid: { left: 8, right: 8, top: 24, bottom: 20, containLabel: true },
    tooltip: { trigger: "axis" as const, backgroundColor: "#171b21", borderColor: "#232830", textStyle: { color: "#e6e9ee", fontSize: 11 } },
    legend: { top: 0, textStyle: { fontSize: 9, color: "#9aa3b2" } },
  };

  const revNi = {
    ...base,
    xAxis: { type: "category", data: periods, ...axis },
    yAxis: [{ type: "value", ...axis, splitLine: { lineStyle: { color: "#161a20" } } }, { type: "value", ...axis, splitLine: { show: false }, axisLabel: { formatter: (v: number) => `${v}%`, ...axis.axisLabel } }],
    series: [
      { name: "Revenue", type: "bar", data: rows.map((r) => Number(r[ix.rev]) / 1e9), itemStyle: { color: "#3b82f6", borderRadius: 2 } },
      { name: "Net income", type: "bar", data: rows.map((r) => Number(r[ix.ni]) / 1e9), itemStyle: { color: "#22c55e", borderRadius: 2 } },
      { name: "Net margin %", type: "line", yAxisIndex: 1, smooth: true, data: rows.map((r) => +((Number(r[ix.ni]) / Number(r[ix.rev])) * 100).toFixed(1)), itemStyle: { color: "#f59e0b" } },
    ],
  };
  const eps = {
    ...base,
    xAxis: { type: "category", data: periods, ...axis },
    yAxis: { type: "value", ...axis, splitLine: { lineStyle: { color: "#161a20" } } },
    series: [{ name: "EPS diluted", type: "line", smooth: true, areaStyle: { opacity: 0.15 }, data: rows.map((r) => Number(r[ix.eps])), itemStyle: { color: "#8b5cf6" } }],
  };
  const last = rows.at(-1);
  const fcfWaterfall = last && {
    ...base,
    xAxis: { type: "category", data: ["Net income", "FCF"], ...axis },
    yAxis: { type: "value", ...axis, splitLine: { lineStyle: { color: "#161a20" } }, axisLabel: { formatter: (v: number) => fmtCompact(v), ...axis.axisLabel } },
    series: [{ type: "bar", data: [
      { value: Number(last[ix.ni]) / 1e9, itemStyle: { color: "#3b82f6" } },
      { value: Number(last[ix.fcf]) / 1e9, itemStyle: { color: "#14b8a6" } },
    ], label: { show: true, position: "top" as const, fontSize: 9, formatter: (p: any) => fmtCompact(p.value * 1e9) } }],
  };

  return (
    <div className="grid h-full grid-cols-3 gap-1 overflow-auto p-1" aria-label="Fundamentals">
      <Panel title={`Revenue & margin — ${app.symbol}`}><ReactECharts option={revNi} style={{ height: "100%" }} notMerge /></Panel>
      <Panel title="EPS trend"><ReactECharts option={eps} style={{ height: "100%" }} notMerge /></Panel>
      <Panel title="Latest quarter — income → FCF ($B)">{fcfWaterfall ? <ReactECharts option={fcfWaterfall} style={{ height: "100%" }} notMerge /> : null}</Panel>
    </div>
  );
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="flex min-h-0 flex-col rounded border border-hairline bg-elevated/40">
      <div className="border-b border-hairline px-2 py-1 text-[10px] font-medium text-fg-2">{title}</div>
      <div className="min-h-0 flex-1">{children}</div>
    </div>
  );
}
