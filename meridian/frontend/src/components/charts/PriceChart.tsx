/** PriceChart — the main LWC chart pane: candles/line/area/HA + volume,
 *  overlay indicators, up to 2 oscillator sub-panes, event badges, compare mode.
 *
 *  LWC v5 native panes: addSeries(def, opts, paneIndex). The whole custom
 *  visual layer (band fills, gradients) uses series options + primitives —
 *  no DOM overlays.
 */

import { useQueries } from "@tanstack/react-query";
import {
  AreaSeries,
  CandlestickSeries,
  ColorType,
  HistogramSeries,
  LineSeries,
  createChart,
  createSeriesMarkers,
  type IChartApi,
  type ISeriesApi,
  type Time,
} from "lightweight-charts";
import { useEffect, useMemo, useRef } from "react";
import type { Bar, PricesResponse } from "../../hooks/usePrices";
import { useEvents, useIndicator, usePrices } from "../../hooks/usePrices";
import { api } from "../../lib/api";
import { chartOptions, palette, gradientArea, SERIES_COLORS, RIBBON_COLORS } from "./chartTheme";
import { BandFillPrimitive } from "./primitives";

export interface OverlaySpec {
  type: string;
  params: Record<string, number>;
}
export interface SubPaneSpec {
  type: string;
  params: Record<string, number>;
}

interface Props {
  symbol: string;
  range: string;
  interval: string;
  chartType: "candles" | "line" | "area" | "heikin";
  adjusted: boolean;
  overlays: OverlaySpec[];
  subPanes: SubPaneSpec[];
  compare: string[];
  replayUntil?: string | null;
  dimAfter?: string | null;
  active?: boolean;
  onFocus?: () => void;
  onSelectTime?: (t: string) => void;
  onLegend?: (legend: LegendState | null) => void;
}

export interface LegendState {
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  changePct: number | null;
  overlays: Record<string, number | null>;
}

const DIM = "#3a4150";

interface HaBar { time: string; open: number; high: number; low: number; close: number }

function toHa(bars: Bar[]): HaBar[] {
  let prevO = bars[0]?.open ?? 0;
  let prevC = bars[0]?.close ?? 0;
  return bars.map((b) => {
    const c = (b.open + b.high + b.low + b.close) / 4;
    const o = (prevO + prevC) / 2;
    prevO = o;
    prevC = c;
    return { time: b.time, open: o, high: Math.max(b.high, o, c), low: Math.min(b.low, o, c), close: c };
  });
}

export function PriceChart(props: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const themeKey = `${document.documentElement.dataset.theme}-${document.documentElement.dataset.palette}`;

  const { data } = usePrices(props.symbol, props.range, props.interval, props.replayUntil);
  const events = useEvents(props.symbol);
  const compareQueries = useQueries({
    queries: props.compare.map((s) => ({
      queryKey: ["prices", s, props.range, props.interval, props.replayUntil ?? null],
      queryFn: () =>
        api<PricesResponse>(
          `/prices/${s}?interval=${props.interval}&range=${props.range}${props.replayUntil ? `&until=${props.replayUntil}` : ""}`,
        ),
      staleTime: 60_000,
    })),
  });

  const bars = useMemo(() => {
    const raw = data?.bars ?? [];
    if (!props.adjusted) return raw;
    return raw.map((b) => {
      const k = b.close ? b.adj_close / b.close : 1;
      return { ...b, open: b.open * k, high: b.high * k, low: b.low * k, close: b.adj_close };
    });
  }, [data, props.adjusted]);

  // indicator queries (overlays + sub-panes share the hook)
  const overlayData = props.overlays.map((o) =>
    // eslint-disable-next-line react-hooks/rules-of-hooks -- stable order
    useIndicator(props.symbol, o.type, o.params, props.range, props.replayUntil),
  );
  const subData = props.subPanes.map((s) =>
    // eslint-disable-next-line react-hooks/rules-of-hooks -- stable order
    useIndicator(props.symbol, s.type, s.params, props.range, props.replayUntil),
  );

  useEffect(() => {
    if (!ref.current) return;
    const c = createChart(ref.current, {
      ...chartOptions(),
      autoSize: true,
      layout: { ...chartOptions().layout, background: { type: ColorType.Solid, color: "transparent" } },
    });
    chartRef.current = c;
    if (props.onSelectTime) {
      c.subscribeClick((p) => {
        if (p.time) props.onSelectTime?.(String(p.time));
      });
    }
    return () => {
      c.remove();
      chartRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ref.current, themeKey]);

  // main price series + volume
  useEffect(() => {
    const c = chartRef.current;
    if (!c || !bars.length) return;
    c.panes().forEach((_, i) => i > 0 && c.removePane(i));

    const comparing = props.compare.length > 0;
    const dimT = props.dimAfter;

    const dimBar = (b: { time: string }) => (dimT && b.time > dimT ? DIM : undefined);
    const up = palette.up();
    const down = palette.down();

    if (comparing) {
      const mkLine = (symBars: Bar[], color: string, width: 1 | 2 = 2) => {
        const base = symBars[0]?.close ?? 1;
        const s = c.addSeries(LineSeries, {
          color, lineWidth: width, lastValueVisible: true, priceLineVisible: false,
          crosshairMarkerRadius: 3,
        });
        s.setData(symBars.map((b) => ({ time: b.time, value: (b.close / base) * 100 })));
        return s;
      };
      mkLine(bars, palette.accent());
      props.compare.forEach((_, i) => {
        const qb = compareQueries[i]?.data?.bars ?? [];
        if (qb.length) mkLine(qb, SERIES_COLORS[(i + 1) % SERIES_COLORS.length], 1);
      });
    } else if (props.chartType === "candles" || props.chartType === "heikin") {
      const src: HaBar[] = props.chartType === "heikin" ? toHa(bars) : bars;
      const s = c.addSeries(CandlestickSeries, {
        upColor: up, downColor: down, borderVisible: false,
        wickUpColor: up, wickDownColor: down,
      });
      s.setData(
        src.map((b) => ({
          time: b.time, open: b.open, high: b.high, low: b.low, close: b.close,
          ...(dimBar(b) ? { color: DIM, wickColor: DIM, borderColor: DIM } : {}),
        })),
      );
      addMarkers(c, s);
    } else {
      const color = palette.accent();
      const def = props.chartType === "area" ? AreaSeries : LineSeries;
      const past = bars.filter((b) => !dimT || b.time <= dimT);
      const future = dimT ? bars.filter((b) => b.time >= dimT) : [];
      const s = c.addSeries(def, {
        ...gradientArea(color),
        lastValueVisible: true,
      });
      s.setData((past as Bar[]).map((b) => ({ time: b.time, value: b.close })));
      if (future.length > 1) {
        const fs = c.addSeries(def, { ...gradientArea(DIM), lineWidth: 1, lastValueVisible: false });
        fs.setData(future.map((b) => ({ time: b.time, value: b.close })));
      }
      addMarkers(c, s);
    }

    // volume — overlay at bottom of main pane
    const vol = c.addSeries(HistogramSeries, { priceScaleId: "vol", lastValueVisible: false });
    c.priceScale("vol").applyOptions({ scaleMargins: { top: 0.82, bottom: 0 }, visible: false });
    vol.setData(
      bars.map((b) => ({
        time: b.time, value: b.volume,
        color: b.close >= b.open ? `${up}55` : `${down}55`,
      })),
    );

    function addMarkers(_chart: IChartApi, series: ISeriesApi<"Candlestick" | "Line" | "Area">) {
      const ev = (events.data ?? [])
        .filter((e) => e.event_date >= (bars[0]?.time ?? "") && e.event_date <= (bars.at(-1)?.time ?? ""))
        .map((e) => ({
          time: e.event_date as Time,
          position: "belowBar" as const,
          shape: "circle" as const,
          color: e.kind === "E" ? (e.sentiment === "beat" ? up : e.sentiment === "miss" ? down : palette.warn()) : palette.fg2(),
          text: e.kind,
          size: 0.6,
        }));
      createSeriesMarkers(series, ev);
    }

    c.timeScale().fitContent();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chartRef.current, bars, props.chartType, props.adjusted, props.dimAfter, props.compare.join(","), events.data]);

  // overlay indicators → lines on pane 0 (bands get fills via gradient between lines)
  useEffect(() => {
    const c = chartRef.current;
    if (!c) return;
    props.overlays.forEach((o, i) => {
      const pts = overlayData[i]?.data?.points ?? [];
      if (!pts.length) return;
      const color = SERIES_COLORS[i % SERIES_COLORS.length];
      const cols = Object.keys(pts[0].extra);
      if (o.type === "bollinger" || o.type === "envelope") {
        let upperSeries: ISeriesApi<"Line"> | null = null;
        for (const [j, col] of ["upper", "basis", "lower"].entries()) {
          const s = c.addSeries(LineSeries, {
            color: j === 1 ? color : `${color}88`, lineWidth: 1, lastValueVisible: j === 1,
          });
          s.setData(pts.filter((p) => p.extra[col] != null).map((p) => ({ time: p.time, value: p.extra[col]! })));
          if (col === "upper") upperSeries = s;
        }
        if (upperSeries) {
          const bandPts = pts
            .filter((p) => p.extra.upper != null && p.extra.lower != null)
            .map((p) => ({ time: p.time as Time, upper: p.extra.upper!, lower: p.extra.lower! }));
          upperSeries.attachPrimitive(new BandFillPrimitive(bandPts, color));
        }
      } else if (o.type === "ribbon") {
        cols.forEach((col, j) => {
          const s = c.addSeries(LineSeries, {
            color: RIBBON_COLORS[j % RIBBON_COLORS.length], lineWidth: 1, lastValueVisible: false,
          });
          s.setData(pts.filter((p) => p.extra[col] != null).map((p) => ({ time: p.time, value: p.extra[col]! })));
        });
      } else {
        const col = cols[0] ?? "value";
        const get = (p: { extra: Record<string, number | null>; value: number | null }) =>
          p.value ?? p.extra[col] ?? null;
        const s = c.addSeries(LineSeries, { color, lineWidth: 1, lastValueVisible: true });
        s.setData(pts.map((p) => ({ time: p.time, value: get(p) })).filter((p) => p.value != null) as never[]);
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chartRef.current, props.overlays.map((o) => o.type + JSON.stringify(o.params)).join("|"), overlayData.map((d) => d.dataUpdatedAt).join("|")]);

  // oscillator sub-panes → paneIndex 1..n
  useEffect(() => {
    const c = chartRef.current;
    if (!c) return;
    props.subPanes.forEach((_, i) => {
      const pts = subData[i]?.data?.points ?? [];
      if (!pts.length) return;
      const pane = 1 + i;
      const cols = Object.keys(pts[0].extra);
      const colors = [palette.accent(), palette.warn(), palette.genie()];
      cols.forEach((col, j) => {
        const isHist = col === "hist";
        const s = c.addSeries(
          isHist ? HistogramSeries : LineSeries,
          { color: colors[j % colors.length], lineWidth: 1, lastValueVisible: true },
          pane,
        );
        s.setData(pts.filter((p) => p.extra[col] != null).map((p) => ({ time: p.time, value: p.extra[col]! })));
      });
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chartRef.current, props.subPanes.map((s) => s.type + JSON.stringify(s.params)).join("|"), subData.map((d) => d.dataUpdatedAt).join("|")]);

  return (
    <div
      className={`relative h-full w-full ${props.active ? "ring-1 ring-pane-active ring-inset" : ""}`}
      onMouseDown={props.onFocus ?? undefined}
    >
      <div ref={ref} className="h-full w-full" role="img" aria-label={`Price chart for ${props.symbol}`} />
      {data?.as_of && (
        <div className="absolute bottom-6 left-2 text-[10px] text-fg-3 num">as of {data.as_of}</div>
      )}
    </div>
  );
}
