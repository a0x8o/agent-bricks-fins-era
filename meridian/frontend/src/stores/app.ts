/** UI + layout state (Zustand). Persisted bits go to localStorage. */

import { create } from "zustand";
import { persist } from "zustand/middleware";

export type RangePreset = "1D" | "5D" | "1M" | "3M" | "6M" | "YTD" | "1Y" | "5Y" | "ALL";
export type ChartType = "candles" | "line" | "area" | "heikin";
export type LayoutPreset = "trader" | "analyst" | "portfolio";
export type ChartGridKind = "1" | "2h" | "2v" | "3" | "4";

interface AppState {
  symbol: string;
  range: RangePreset;
  interval: string;
  chartType: ChartType;
  adjusted: boolean;
  theme: "dark" | "light";
  palette: "std" | "cb";
  density: "compact" | "comfortable";
  grid: ChartGridKind;
  activePane: number;
  genieOpen: boolean;
  genieContextSymbol: boolean;
  dockTab: string;
  dockOpen: boolean;
  compare: string[];
  overlays: { type: string; params: Record<string, number> }[];
  subPanes: { type: string; params: Record<string, number> }[];
  replay: { active: boolean; cursor: string | null; playing: boolean; speed: number };
  setSymbol: (s: string) => void;
  set: (p: Partial<AppState>) => void;
}

export const useApp = create<AppState>()(
  persist(
    (set) => ({
      symbol: "NVDA",
      range: "1Y",
      interval: "1D",
      chartType: "candles",
      adjusted: true,
      theme: "dark",
      palette: "std",
      density: "compact",
      grid: "1",
      activePane: 0,
      genieOpen: true,
      genieContextSymbol: true,
      dockTab: "screener",
      dockOpen: true,
      compare: [],
      overlays: [
        { type: "ema", params: { length: 20 } },
        { type: "sma", params: { length: 50 } },
      ],
      subPanes: [{ type: "rsi", params: { length: 14 } }],
      replay: { active: false, cursor: null, playing: false, speed: 1 },
      setSymbol: (symbol) => set({ symbol }),
      set: (p) => set(p),
    }),
    {
      name: "meridian-layout",
      partialize: (s) => ({
        theme: s.theme, palette: s.palette, density: s.density, grid: s.grid,
        dockTab: s.dockTab, dockOpen: s.dockOpen, genieOpen: s.genieOpen,
        chartType: s.chartType, adjusted: s.adjusted, overlays: s.overlays,
        subPanes: s.subPanes, symbol: s.symbol, range: s.range, compare: s.compare,
      }),
    },
  ),
);
