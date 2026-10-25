/** Renders an inferred ChartSpec over a Genie ResultSet via ECharts. */

import ReactECharts from "echarts-for-react";
import { useMemo } from "react";
import type { ChartSpec, GenieResult } from "../../lib/genie";

const ACCENT = "#3b82f6";
const CAT = ["#3b82f6", "#8b5cf6", "#f59e0b", "#14b8a6", "#f472b6", "#a3e635", "#22c55e", "#ef4444"];

export function AnswerChart({ spec, result }: { spec: ChartSpec; result: GenieResult }) {
  const opt = useMemo(() => {
    const idx = (n: string | null) => result.columns.findIndex((c) => c.name === n);
    const xi = idx(spec.x);
    const xs = xi >= 0 ? result.rows.map((r) => String(r[xi])) : [];
    const base = {
      backgroundColor: "transparent",
      textStyle: { color: "#9aa3b2", fontSize: 10 },
      grid: { left: 8, right: 12, top: 24, bottom: 20, containLabel: true },
      tooltip: { trigger: "axis" as const, backgroundColor: "#171b21", borderColor: "#232830", textStyle: { color: "#e6e9ee", fontSize: 11 } },
      color: CAT,
    };

    if (spec.kind === "kpi") {
      const v = result.rows[0]?.[0];
      return {
        ...base,
        series: [],
        graphic: [{
          type: "text", left: "center", top: "middle",
          style: { text: typeof v === "number" ? v.toLocaleString("en-US", { maximumFractionDigits: 2 }) : String(v ?? "—"), fontSize: 34, fontWeight: 600, fill: ACCENT, fontFamily: "JetBrains Mono" },
        }],
      };
    }

    if (spec.kind === "donut" || spec.kind === "treemap") {
      const yi = idx(spec.y[0]);
      const data = result.rows.map((r) => ({ name: String(r[xi]), value: Number(r[yi]) }));
      return spec.kind === "donut"
        ? { ...base, series: [{ type: "pie", radius: ["45%", "75%"], data, label: { fontSize: 10, color: "#9aa3b2" } }] }
        : { ...base, series: [{ type: "treemap", data, label: { fontSize: 11 } }] };
    }

    if (spec.kind === "scatter") {
      const xi2 = idx(spec.x), yi = idx(spec.y[0]);
      return {
        ...base,
        xAxis: { name: spec.x, axisLabel: { fontSize: 9 } },
        yAxis: { name: spec.y[0], axisLabel: { fontSize: 9 }, splitLine: { lineStyle: { color: "#161a20" } } },
        series: [{ type: "scatter", symbolSize: 7, itemStyle: { color: ACCENT, opacity: 0.75 }, data: result.rows.map((r) => [Number(r[xi2]), Number(r[yi])]) }],
      };
    }

    if (spec.kind === "bar" || spec.kind === "bar_h") {
      const yi = idx(spec.y[0]);
      const data = result.rows.map((r) => Number(r[yi]));
      const horiz = spec.kind === "bar_h";
      return {
        ...base,
        xAxis: { type: horiz ? "value" : "category", data: horiz ? undefined : xs, axisLabel: { fontSize: 9 } },
        yAxis: { type: horiz ? "category" : "value", data: horiz ? xs : undefined, axisLabel: { fontSize: 9 }, splitLine: { lineStyle: { color: "#161a20" } } },
        series: [{ type: "bar", data, itemStyle: { color: ACCENT, borderRadius: 2 }, barMaxWidth: 18 }],
      };
    }

    // line / area / multi_line (+normalized)
    const series = spec.y.map((yn, j) => {
      const yi = idx(yn);
      let vals = result.rows.map((r) => Number(r[yi]));
      if (spec.normalized && vals.length && vals[0]) vals = vals.map((v) => (v / vals[0]) * 100);
      return {
        name: yn, type: "line" as const, smooth: false, showSymbol: false, data: vals,
        lineStyle: { width: 1.5 },
        areaStyle: spec.kind === "area" || (spec.kind === "line" && spec.y.length === 1)
          ? { color: { type: "linear" as const, x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: `${CAT[j % CAT.length]}59` }, { offset: 1, color: `${CAT[j % CAT.length]}00` }] } }
          : undefined,
      };
    });
    return {
      ...base,
      legend: spec.y.length > 1 ? { top: 0, textStyle: { fontSize: 9, color: "#9aa3b2" } } : undefined,
      xAxis: { type: "category", data: xs, axisLabel: { fontSize: 9 } },
      yAxis: { type: "value", axisLabel: { fontSize: 9 }, splitLine: { lineStyle: { color: "#161a20" } }, scale: true },
      series,
    };
  }, [spec, result]);

  return (
    <div className="px-1 pb-1" role="img" aria-label={`Inferred ${spec.kind} chart`}>
      <ReactECharts option={opt} style={{ height: 180 }} notMerge />
    </div>
  );
}
