/** LWC options derived from CSS variables — tokens are the only color source. */

import type { DeepPartial, ChartOptions } from "lightweight-charts";

const cssVar = (n: string) =>
  getComputedStyle(document.documentElement).getPropertyValue(n).trim();

export function chartOptions(): DeepPartial<ChartOptions> {
  return {
    layout: {
      background: { color: "transparent" },
      textColor: cssVar("--fg-2") || "#9aa3b2",
      fontFamily: "Inter, system-ui, sans-serif",
      fontSize: 11,
      panes: {
        separatorColor: cssVar("--hairline") || "#232830",
        separatorHoverColor: cssVar("--accent") || "#3b82f6",
        enableResize: true,
      },
      attributionLogo: true,
    },
    grid: {
      vertLines: { color: cssVar("--chart-grid") || "#161a20" },
      horzLines: { color: cssVar("--chart-grid") || "#161a20" },
    },
    crosshair: {
      vertLine: { color: cssVar("--fg-3"), labelBackgroundColor: cssVar("--elevated") },
      horzLine: { color: cssVar("--fg-3"), labelBackgroundColor: cssVar("--elevated") },
    },
    rightPriceScale: {
      borderColor: cssVar("--hairline"),
      textColor: cssVar("--axis-text"),
    },
    timeScale: {
      borderColor: cssVar("--hairline"),
      timeVisible: false,
      secondsVisible: false,
    },
  };
}

export const palette = {
  up: () => cssVar("--up"),
  down: () => cssVar("--down"),
  accent: () => cssVar("--accent"),
  genie: () => cssVar("--genie"),
  warn: () => cssVar("--warn"),
  fg2: () => cssVar("--fg-2"),
  hairline: () => cssVar("--hairline"),
};

/** series colors for overlays / compare — semantic, not decorative */
export const SERIES_COLORS = ["#3b82f6", "#8b5cf6", "#f59e0b", "#14b8a6", "#f472b6", "#a3e635"];
export const RIBBON_COLORS = ["#c4b5fd", "#a78bfa", "#8b5cf6", "#7c3aed", "#d946ef", "#e879f9", "#f0abfc", "#f5d0fe", "#818cf8", "#6366f1"];

/** gradient fill for area/line series — 35% at line → 0 at baseline */
export function gradientArea(color: string) {
  return {
    topColor: `${color}59`, // ~35%
    bottomColor: `${color}00`,
    lineColor: color,
    lineWidth: 2 as const,
  };
}
