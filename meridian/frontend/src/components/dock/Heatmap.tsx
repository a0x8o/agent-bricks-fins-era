import { useQuery } from "@tanstack/react-query";
import ReactECharts from "echarts-for-react";
import { useState } from "react";
import { api } from "../../lib/api";
import type { GenieResult } from "../../lib/genie";
import { useApp } from "../../stores/app";
import { Skeleton } from "../ui/primitives";

const METRICS = [
  { id: "1d", label: "1D" }, { id: "1w", label: "1W" }, { id: "1m", label: "1M" },
  { id: "ytd", label: "YTD" }, { id: "1y", label: "1Y" },
];

export default function Heatmap() {
  const app = useApp();
  const [metric, setMetric] = useState("1m");
  const { data, isLoading } = useQuery({
    queryKey: ["heatmap", metric],
    queryFn: () => api<GenieResult>(`/heatmap?metric=${metric}`),
  });

  if (isLoading || !data) return <div className="p-2"><Skeleton className="h-full min-h-28" /></div>;

  const c = (n: string) => data.columns.findIndex((x) => x.name === n);
  const mi = data.columns.findIndex((x) => x.name !== "last" && x.type !== "STRING" && !["market_cap"].includes(x.name));
  const sectors = new Map<string, { name: string; value: number; children: any[] }>();
  for (const r of data.rows) {
    const sec = String(r[c("sector")]);
    const ret = Number(r[mi]);
    const node = {
      name: String(r[c("symbol")]),
      value: Number(r[c("market_cap")]) || 1,
      ret,
      full: `${r[c("name")]} · ${ret > 0 ? "+" : ""}${ret.toFixed(2)}%`,
    };
    if (!sectors.has(sec)) sectors.set(sec, { name: sec, value: 0, children: [] });
    const s = sectors.get(sec)!;
    s.children.push(node);
    s.value += node.value;
  }

  const option = {
    backgroundColor: "transparent",
    tooltip: {
      backgroundColor: "#171b21", borderColor: "#232830", textStyle: { color: "#e6e9ee", fontSize: 11 },
      formatter: (p: any) => p.data?.full ?? p.name,
    },
    series: [{
      type: "treemap",
      roam: false,
      nodeClick: false,
      breadcrumb: { show: false },
      label: { show: true, fontSize: 10, fontWeight: 600, formatter: (p: any) => p.name },
      upperLabel: { show: true, height: 18, color: "#9aa3b2", fontSize: 9 },
      itemStyle: { borderColor: "#0b0d10", borderWidth: 1, gapWidth: 1 },
      data: [...sectors.values()],
      visualMap: {
        show: false, min: -15, max: 15, dimension: 2,
        inRange: { color: ["#ef4444", "#7f1d1d", "#171b21", "#14532d", "#22c55e"] },
      },
    }],
  };
  // attach ret to data nodes for visualMap dimension
  (option.series[0] as any).data = [...sectors.values()].map((s) => ({
    ...s,
    children: s.children.map((n) => ({ ...n, value: n.value, dimension: n.ret })),
  }));
  (option.series[0] as any).colorMappingBy = "value";

  const onEvents = {
    click: (p: any) => {
      if (p.data?.children == null && typeof p.name === "string") app.setSymbol(p.name);
    },
  };

  return (
    <div className="flex h-full flex-col" aria-label="Heatmap">
      <div className="flex items-center gap-1 px-2 py-1">
        <span className="text-[10px] text-fg-3">Return window:</span>
        {METRICS.map((m) => (
          <button key={m.id} onClick={() => setMetric(m.id)} className={`rounded px-1.5 py-0.5 text-[10px] num ${metric === m.id ? "bg-accent/15 text-accent" : "text-fg-3 hover:text-fg-2"}`}>
            {m.label}
          </button>
        ))}
        <span className="ml-auto text-[9px] text-fg-3">size = market cap · click a symbol</span>
      </div>
      <div className="min-h-0 flex-1">
        <ReactECharts option={option} style={{ height: "100%" }} notMerge onEvents={onEvents} />
      </div>
    </div>
  );
}
