import useSWR from 'swr';
import { fetcher, cn } from '@/lib/utils';
import { useAppConfig } from '@/contexts/AppConfigContext';
import { useWorkspacePanel } from '@/contexts/WorkspacePanelContext';
import { loadDemoTickers } from '@/lib/you-com';
import { useMemo } from 'react';

interface SummaryRow {
  company_name: string | null;
  Date: string | null;
  price_close: string | null;
  market_cap: string | null;
  pe_trailing: string | null;
  beta: string | null;
}

function compactCurrency(value: number): string {
  if (!Number.isFinite(value)) return '—';
  const abs = Math.abs(value);
  if (abs >= 1e12) return `$${(value / 1e12).toFixed(1)}T`;
  if (abs >= 1e9) return `$${(value / 1e9).toFixed(1)}B`;
  if (abs >= 1e6) return `$${(value / 1e6).toFixed(1)}M`;
  return `$${value.toFixed(2)}`;
}

/**
 * Top-level desk summary. The workspace panel to the right is the deeper
 * analyst view (graph / series / Genie). This strip is the VP glance.
 */
export function SummaryStrip() {
  const { dataExplorerEnabled } = useAppConfig();
  const { open } = useWorkspacePanel();
  const tickers = useMemo(() => loadDemoTickers(), []);
  const key = dataExplorerEnabled
    ? `/api/series/summary?tickers=${encodeURIComponent(tickers.join(','))}`
    : null;
  const { data, error, isLoading } = useSWR<{ rows: SummaryRow[] }>(
    key,
    fetcher,
    { revalidateOnFocus: false },
  );

  if (!dataExplorerEnabled) return null;

  const rows = (data?.rows ?? []).slice(0, 6);

  return (
    <section
      data-testid="summary-strip"
      aria-label="Market summary"
      className="border-b bg-card/40 px-3 py-2"
    >
      <div className="mb-1.5 flex items-baseline justify-between gap-2">
        <p className="font-medium text-[11px] text-muted-foreground uppercase tracking-wide">
          Coverage snapshot
        </p>
        <p className="text-[11px] text-muted-foreground">
          {isLoading
            ? 'Loading latest close…'
            : error
              ? 'Summary unavailable'
              : rows[0]?.Date
                ? `As of ${rows[0].Date}`
                : 'Latest close in ticker_data'}
        </p>
      </div>
      {error ? (
        <p className="text-muted-foreground text-xs">
          The app service principal needs CAN_USE on the warehouse and SELECT
          on ticker_data. Re-run notebook 06b or the grant job.
        </p>
      ) : (
        <div className="flex gap-2 overflow-x-auto pb-0.5">
          {(isLoading ? tickers.map((t) => ({ company_name: t })) : rows).map(
            (row, i) => {
              const ticker = row.company_name ?? tickers[i] ?? '—';
              const price = Number(row.price_close);
              const mcap = Number(row.market_cap);
              return (
                <button
                  key={ticker}
                  type="button"
                  onClick={() => open('data', { ticker })}
                  className={cn(
                    'min-w-[7.5rem] shrink-0 rounded-lg border bg-background px-2.5 py-1.5 text-left',
                    'hover:border-foreground/40',
                  )}
                >
                  <p className="font-medium text-[11px] text-muted-foreground">
                    {ticker}
                  </p>
                  <p className="font-semibold text-sm tabular-nums">
                    {Number.isFinite(price) ? `$${price.toFixed(2)}` : '—'}
                  </p>
                  <p className="text-[11px] text-muted-foreground tabular-nums">
                    {Number.isFinite(mcap) ? compactCurrency(mcap) : 'mcap —'}
                  </p>
                </button>
              );
            },
          )}
        </div>
      )}
    </section>
  );
}
