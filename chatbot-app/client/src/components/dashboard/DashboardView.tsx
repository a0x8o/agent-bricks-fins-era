import { useState, useEffect, useCallback } from 'react';
import {
  LayoutDashboard,
  TrendingUp,
  BookOpen,
  Activity,
  RefreshCw,
  Loader2,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { VegaChart } from '@/components/VegaChart';

type DashPage = 'market' | 'valuation' | 'operations' | 'library';

interface DashData {
  market: {
    snapshot: Record<string, string | null>[];
    priceSeries: Record<string, string | null>[];
    evSeries: Record<string, string | null>[];
  };
  library: { docCounts: Record<string, string | null>[] };
  operations: {
    stats: Record<string, string | null>;
    timeline: Record<string, string | null>[];
  };
}

function fmt(v: string | null | undefined, type: 'currency' | 'number' | 'pct' = 'number'): string {
  if (!v) return '—';
  const n = Number(v);
  if (!Number.isFinite(n)) return '—';
  if (type === 'currency') {
    if (n >= 1e12) return `$${(n / 1e12).toFixed(2)}T`;
    if (n >= 1e9) return `$${(n / 1e9).toFixed(1)}B`;
    if (n >= 1e6) return `$${(n / 1e6).toFixed(1)}M`;
    return `$${n.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
  }
  if (type === 'pct') return `${n.toFixed(1)}%`;
  if (n >= 1e9) return `${(n / 1e9).toFixed(1)}B`;
  if (n >= 1e6) return `${(n / 1e6).toFixed(1)}M`;
  return n.toLocaleString(undefined, { maximumFractionDigits: 1 });
}

function KPI({ label, value, className }: { label: string; value: string; className?: string }) {
  return (
    <div className={cn('rounded-lg border bg-card p-3', className)}>
      <div className="text-[11px] text-muted-foreground">{label}</div>
      <div className="mt-1 font-semibold text-lg tabular-nums">{value}</div>
    </div>
  );
}

function lineSpec(data: Record<string, string | null>[], yField: string, yTitle: string) {
  return JSON.stringify({
    $schema: 'https://vega.github.io/schema/vega-lite/v5.json',
    data: { values: data.map(r => ({ date: r.date, company: r.company_name, value: Number(r.value) })) },
    mark: { type: 'line', strokeWidth: 1.5 },
    encoding: {
      x: { field: 'date', type: 'temporal', title: null },
      y: { field: 'value', type: 'quantitative', title: yTitle },
      color: { field: 'company', type: 'nominal', title: 'Company' },
    },
    width: 'container', height: 220,
    config: { view: { stroke: null }, axis: { grid: true, gridOpacity: 0.15 } },
  });
}

function barSpec(data: { label: string; value: number }[], yTitle: string) {
  return JSON.stringify({
    $schema: 'https://vega.github.io/schema/vega-lite/v5.json',
    data: { values: data },
    mark: { type: 'bar', cornerRadiusTopLeft: 3, cornerRadiusTopRight: 3 },
    encoding: {
      x: { field: 'label', type: 'nominal', title: null, sort: '-y' },
      y: { field: 'value', type: 'quantitative', title: yTitle },
      color: { field: 'label', type: 'nominal', legend: null },
    },
    width: 'container', height: 200,
    config: { view: { stroke: null } },
  });
}

/**
 * Native dashboard view — fetches data via the SP's SQL execution API.
 * No iframes, no CSP issues.
 */
export function DashboardView() {
  const [data, setData] = useState<DashData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState<DashPage>('market');

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await fetch('/api/dashboard-data');
      if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
      setData(await r.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const pages: { id: DashPage; label: string; icon: typeof LayoutDashboard }[] = [
    { id: 'market', label: 'Market', icon: TrendingUp },
    { id: 'valuation', label: 'Valuation', icon: LayoutDashboard },
    { id: 'operations', label: 'Agent Ops', icon: Activity },
    { id: 'library', label: 'Library', icon: BookOpen },
  ];

  return (
    <div className="flex h-full flex-col">
      {/* Tab bar */}
      <div className="flex items-center justify-between border-b px-2 py-1">
        <div className="flex items-center gap-0.5">
          {pages.map(p => {
            const Icon = p.icon;
            return (
              <Button key={p.id} variant={page === p.id ? 'secondary' : 'ghost'} size="sm"
                className="h-7 gap-1 px-2 text-xs" onClick={() => setPage(p.id)}>
                <Icon className="h-3 w-3" />{p.label}
              </Button>
            );
          })}
        </div>
        <Button variant="ghost" size="icon" className="h-7 w-7" onClick={load} disabled={loading}>
          {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
        </Button>
      </div>

      {/* Content */}
      <div className="min-h-0 flex-1 overflow-y-auto p-3">
        {loading && !data && <div className="flex h-full items-center justify-center text-muted-foreground">Loading dashboard data...</div>}
        {error && <div className="rounded-md bg-destructive/10 p-3 text-sm text-destructive">{error}</div>}
        {data && page === 'market' && <MarketPage data={data} />}
        {data && page === 'valuation' && <ValuationPage data={data} />}
        {data && page === 'operations' && <OpsPage data={data} />}
        {data && page === 'library' && <LibraryPage data={data} />}
      </div>
    </div>
  );
}

function MarketPage({ data }: { data: DashData }) {
  const s = data.market.snapshot;
  const totalMcap = s.reduce((a, r) => a + Number(r.market_cap ?? 0), 0);
  const avgVol = s.reduce((a, r) => a + Number(r.volume ?? 0), 0) / (s.length || 1);
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-2">
        <KPI label="Total Market Cap" value={fmt(String(totalMcap), 'currency')} />
        <KPI label="Avg Daily Volume" value={fmt(String(avgVol))} />
        <KPI label="Companies" value={String(s.length)} />
      </div>
      <div>
        <h3 className="mb-1 font-medium text-xs text-muted-foreground">Stock Price Trends</h3>
        <VegaChart specString={lineSpec(data.market.priceSeries, 'value', 'Close Price ($)')} />
      </div>
      <div>
        <h3 className="mb-1 font-medium text-xs text-muted-foreground">Market Cap Comparison</h3>
        <VegaChart specString={barSpec(s.map(r => ({ label: r.company_name ?? '', value: Number(r.market_cap ?? 0) })), 'Market Cap')} />
      </div>
    </div>
  );
}

function ValuationPage({ data }: { data: DashData }) {
  const s = data.market.snapshot;
  return (
    <div className="space-y-4">
      {/* One trailing P/E card per company (all 7 MAG7), ordered by market cap */}
      <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">
        {s.map(r => (
          <KPI key={r.company_name} label={`${r.company_name} P/E (T)`} value={fmt(r.pe_trailing)} />
        ))}
      </div>
      <div>
        <h3 className="mb-1 font-medium text-xs text-muted-foreground">EV/EBITDA Over Time</h3>
        <VegaChart specString={lineSpec(data.market.evSeries, 'value', 'EV/EBITDA')} />
      </div>
      <div>
        <h3 className="mb-1 font-medium text-xs text-muted-foreground">Beta — Volatility Comparison</h3>
        <VegaChart specString={barSpec(s.map(r => ({ label: r.company_name ?? '', value: Number(r.beta ?? 0) })), 'Beta')} />
      </div>
      <div>
        <h3 className="mb-1 font-medium text-xs text-muted-foreground">P/E: Trailing vs Forward</h3>
        <VegaChart specString={JSON.stringify({
          $schema: 'https://vega.github.io/schema/vega-lite/v5.json',
          data: { values: s.flatMap(r => [
            { company: r.company_name, metric: 'Trailing', value: Number(r.pe_trailing ?? 0) },
            { company: r.company_name, metric: 'Forward', value: Number(r.pe_forward ?? 0) },
          ]) },
          mark: { type: 'bar', cornerRadiusTopLeft: 3, cornerRadiusTopRight: 3 },
          encoding: {
            x: { field: 'company', type: 'nominal', title: null },
            y: { field: 'value', type: 'quantitative', title: 'P/E Ratio' },
            color: { field: 'metric', type: 'nominal' },
            xOffset: { field: 'metric' },
          },
          width: 'container', height: 220,
          config: { view: { stroke: null } },
        })} />
      </div>
    </div>
  );
}

function OpsPage({ data }: { data: DashData }) {
  const s = data.operations.stats;
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-2">
        <KPI label="Total Requests" value={fmt(s.total_requests)} />
        <KPI label="Avg Duration (ms)" value={fmt(s.avg_duration_ms)} />
        <KPI label="P95 Duration (ms)" value={fmt(s.p95_duration_ms)} />
      </div>
      {data.operations.timeline.length > 0 && (
        <div>
          <h3 className="mb-1 font-medium text-xs text-muted-foreground">Requests Over Time</h3>
          <VegaChart specString={JSON.stringify({
            $schema: 'https://vega.github.io/schema/vega-lite/v5.json',
            data: { values: data.operations.timeline.map(r => ({ date: r.date, count: Number(r.request_count ?? 0), status: r.status_code })) },
            mark: { type: 'bar' },
            encoding: {
              x: { field: 'date', type: 'temporal', title: null },
              y: { field: 'count', type: 'quantitative', title: 'Requests', stack: true },
              color: { field: 'status', type: 'nominal', title: 'Status' },
            },
            width: 'container', height: 200,
            config: { view: { stroke: null } },
          })} />
        </div>
      )}
    </div>
  );
}

function LibraryPage({ data }: { data: DashData }) {
  const docs = data.library.docCounts;
  const total = docs.reduce((a, r) => a + Number(r.doc_count ?? 0), 0);
  return (
    <div className="space-y-4">
      <KPI label="Total Documents" value={String(total)} />
      <div>
        <h3 className="mb-1 font-medium text-xs text-muted-foreground">Documents by Source</h3>
        <VegaChart specString={barSpec(docs.map(r => ({ label: r.source ?? '', value: Number(r.doc_count ?? 0) })), 'Documents')} />
      </div>
      <div>
        <h3 className="mb-1 font-medium text-xs text-muted-foreground">Breakdown</h3>
        <div className="rounded-md border">
          <table className="w-full text-sm">
            <thead><tr className="border-b bg-muted/50"><th className="p-2 text-left font-medium">Source</th><th className="p-2 text-right font-medium">Count</th></tr></thead>
            <tbody>{docs.map(r => (
              <tr key={r.source} className="border-b last:border-0">
                <td className="p-2">{r.source}</td>
                <td className="p-2 text-right tabular-nums">{Number(r.doc_count ?? 0).toLocaleString()}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
