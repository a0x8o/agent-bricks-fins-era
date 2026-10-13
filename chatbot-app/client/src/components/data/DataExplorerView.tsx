import { useEffect, useMemo, useRef, useState } from 'react';
import useSWR from 'swr';
import { Vega } from 'react-vega';
import { BarChart3, Loader2 } from 'lucide-react';
import { fetcher, cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { PanelEmptyState } from '@/components/workspace-panel/panel-empty-state';

export interface DataExplorerViewProps {
  focusTicker?: string;
}

interface MetricOption {
  key: string;
  label: string;
  format: 'currency' | 'number';
}

interface SeriesMeta {
  tickers: string[];
  metrics: MetricOption[];
}

interface SeriesPoint {
  date: string;
  ticker: string;
  value: number | null;
}

interface SeriesResponse {
  metric: string;
  label: string;
  points: SeriesPoint[];
}

interface SummaryRow {
  symbol: string | null;
  company_name: string | null;
  price_close: string | null;
  market_cap: string | null;
  pe_trailing: string | null;
  beta: string | null;
}

function formatCompactCurrency(value: number): string {
  if (!Number.isFinite(value)) return '—';
  const abs = Math.abs(value);
  if (abs >= 1e12) return `$${(value / 1e12).toFixed(2)}T`;
  if (abs >= 1e9) return `$${(value / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `$${(value / 1e6).toFixed(2)}M`;
  return `$${value.toFixed(2)}`;
}

function formatNumber(value: number, digits = 2): string {
  if (!Number.isFinite(value)) return '—';
  return value.toLocaleString(undefined, { maximumFractionDigits: digits });
}

// Company names contain commas ("Tesla, Inc."), so tickers are joined with '|'.
const TICKER_SEP = '|';

function KpiTiles({ tickers }: { tickers: string[] }) {
  const key =
    tickers.length > 0
      ? `/api/series/summary?tickers=${encodeURIComponent(tickers.join(TICKER_SEP))}`
      : '/api/series/summary';
  const { data } = useSWR<{ rows: SummaryRow[] }>(key, fetcher);
  const rows = data?.rows ?? [];
  if (rows.length === 0) return null;

  return (
    <div className="grid grid-cols-2 gap-2 px-2 py-2 lg:grid-cols-3">
      {rows.map((row) => {
        const price = Number(row.price_close);
        const mcap = Number(row.market_cap);
        const pe = Number(row.pe_trailing);
        return (
          <div
            key={row.symbol ?? row.company_name ?? Math.random()}
            className="rounded-lg border bg-card p-2"
          >
            <p className="truncate font-medium text-xs">{row.company_name}</p>
            <p className="font-semibold text-sm">
              {Number.isFinite(price) ? `$${formatNumber(price)}` : '—'}
            </p>
            <p className="text-muted-foreground text-[11px]">
              {formatCompactCurrency(mcap)} · P/E{' '}
              {Number.isFinite(pe) ? formatNumber(pe, 1) : '—'}
            </p>
          </div>
        );
      })}
    </div>
  );
}

/**
 * MAG7 ticker data explorer: KPI tiles + an interactive multi-series chart,
 * with ticker and metric selectors. Reads /api/series* (Statement Execution
 * API over ticker_data).
 */
export function DataExplorerView({ focusTicker }: DataExplorerViewProps) {
  const { data: meta, error: metaError } = useSWR<SeriesMeta>(
    '/api/series/meta',
    fetcher,
  );

  const [metric, setMetric] = useState('price_close');
  const [selected, setSelected] = useState<string[]>([]);

  // Initialize selection once metadata is available.
  useEffect(() => {
    if (!meta?.tickers?.length) return;
    setSelected((prev) => {
      if (prev.length > 0) return prev;
      if (focusTicker && meta.tickers.includes(focusTicker)) {
        return [focusTicker];
      }
      return meta.tickers.slice(0, Math.min(4, meta.tickers.length));
    });
  }, [meta, focusTicker]);

  const seriesKey =
    selected.length > 0
      ? `/api/series?metric=${metric}&tickers=${encodeURIComponent(selected.join(TICKER_SEP))}`
      : null;
  const { data: series, isLoading } = useSWR<SeriesResponse>(seriesKey, fetcher);

  const metricLabel =
    meta?.metrics.find((m) => m.key === metric)?.label ?? 'Value';

  // react-vega does not support vega-embed's `width: 'container'` (renders a
  // zero-width, invisible chart). Measure the container and pass pixels,
  // same approach as VegaChart.tsx.
  const chartRef = useRef<HTMLDivElement>(null);
  const [chartWidth, setChartWidth] = useState(0);
  useEffect(() => {
    const el = chartRef.current;
    if (!el) return;
    const update = () => {
      const w = el.clientWidth;
      if (w > 0) setChartWidth(w);
    };
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  });

  const spec = useMemo(
    () =>
      ({
        $schema: 'https://vega.github.io/schema/vega-lite/v5.json',
        width: Math.max(chartWidth - 16, 200),
        height: 240,
        autosize: { type: 'fit', contains: 'padding' },
        data: { values: series?.points ?? [] },
        mark: { type: 'line', interpolate: 'monotone', strokeWidth: 2 },
        encoding: {
          x: { field: 'date', type: 'temporal', title: null, timeUnit: 'yearmonthdate' },
          y: {
            field: 'value',
            type: 'quantitative',
            title: metricLabel,
            scale: { zero: false },
          },
          color: { field: 'ticker', type: 'nominal', title: 'Ticker' },
          tooltip: [
            { field: 'ticker', type: 'nominal' },
            { field: 'date', type: 'temporal' },
            { field: 'value', type: 'quantitative', format: ',.2f' },
          ],
        },
      }) as const,
    [series, metricLabel, chartWidth],
  );

  if (metaError) {
    return (
      <PanelEmptyState
        icon={<BarChart3 className="h-8 w-8" />}
        title="Couldn't load data"
        description={
          (metaError as Error)?.message ??
          'The data service returned an error. Confirm ticker_data and the warehouse are configured.'
        }
      />
    );
  }

  if (!meta) {
    return (
      <div className="flex h-full items-center justify-center text-muted-foreground">
        <Loader2 className="h-5 w-5 animate-spin" />
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col overflow-y-auto">
      {/* Metric selector */}
      <div className="flex flex-wrap gap-1 border-b px-2 py-1.5">
        {meta.metrics.map((m) => (
          <Button
            key={m.key}
            variant={metric === m.key ? 'secondary' : 'ghost'}
            size="sm"
            className="h-6 px-2 text-xs"
            onClick={() => setMetric(m.key)}
          >
            {m.label}
          </Button>
        ))}
      </div>

      {/* Ticker chips */}
      <div className="flex flex-wrap gap-1 border-b px-2 py-1.5">
        {meta.tickers.map((t) => {
          const active = selected.includes(t);
          return (
            <button
              type="button"
              key={t}
              onClick={() =>
                setSelected((prev) =>
                  prev.includes(t)
                    ? prev.filter((x) => x !== t)
                    : [...prev, t],
                )
              }
              className={cn(
                'rounded-full border px-2 py-0.5 text-xs transition-colors',
                active
                  ? 'border-primary bg-primary/10 text-primary'
                  : 'border-border text-muted-foreground hover:bg-muted',
              )}
            >
              {t}
            </button>
          );
        })}
      </div>

      <KpiTiles tickers={selected} />

      {/* Chart */}
      <div className="min-h-0 flex-1 px-2 pb-3">
        {selected.length === 0 ? (
          <div className="flex h-full items-center justify-center text-muted-foreground text-xs">
            Select one or more tickers to chart.
          </div>
        ) : isLoading ? (
          <div className="flex h-full items-center justify-center text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin" />
          </div>
        ) : (
          <div ref={chartRef} className="w-full">
            {chartWidth > 0 && (series?.points?.length ?? 0) > 0 ? (
              <Vega spec={spec as never} actions={false} />
            ) : series && series.points.length === 0 ? (
              <div className="flex h-40 items-center justify-center text-muted-foreground text-xs">
                No data for the selected tickers.
              </div>
            ) : null}
          </div>
        )}
      </div>
    </div>
  );
}
