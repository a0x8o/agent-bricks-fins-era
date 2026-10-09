import {
  Router,
  type Request,
  type Response,
  type Router as RouterType,
} from 'express';
import { z } from 'zod';
import { authMiddleware, requireAuth } from '../middleware/auth';
import { executeSql } from '../lib/databricks-sql';
import { getGraphTableConfig, isSqlBackedEnabled } from '../lib/pro-config';

export const seriesRouter: RouterType = Router();
seriesRouter.use(authMiddleware);

/**
 * Read-only views over the ticker_data table for the Data Explorer tab.
 *
 *   GET /api/series/meta                 → available tickers + metric options
 *   GET /api/series?metric=&tickers=     → tidy time series for charting
 *   GET /api/series/summary?tickers=     → latest-snapshot KPI rows
 */

// Whitelisted, charts-friendly numeric columns (key -> {column,label,format}).
const METRICS = {
  price_close: { column: 'price_close', label: 'Close price', format: 'currency' },
  price_open: { column: 'price_open', label: 'Open price', format: 'currency' },
  volume: { column: 'volume', label: 'Volume', format: 'number' },
  market_cap: { column: 'market_cap', label: 'Market cap', format: 'currency' },
  pe_trailing: { column: 'pe_trailing', label: 'P/E (trailing)', format: 'number' },
  pe_forward: { column: 'pe_forward', label: 'P/E (forward)', format: 'number' },
  peg: { column: 'peg', label: 'PEG ratio', format: 'number' },
  ev_ebitda: { column: 'ev_ebitda', label: 'EV/EBITDA', format: 'number' },
  beta: { column: 'beta', label: 'Beta', format: 'number' },
} as const;

type MetricKey = keyof typeof METRICS;
const METRIC_KEYS = Object.keys(METRICS) as MetricKey[];

const IDENT = /^[A-Za-z_][A-Za-z0-9_-]*$/;

function tableName(): string | null {
  const { catalog, schema } = getGraphTableConfig();
  if (!IDENT.test(catalog) || !IDENT.test(schema)) return null;
  return `\`${catalog}\`.\`${schema}\`.ticker_data`;
}

function parseTickers(raw: unknown): string[] {
  if (typeof raw !== 'string' || !raw.trim()) return [];
  return raw
    .split(',')
    .map((t) => t.trim())
    .filter(Boolean)
    .slice(0, 12);
}

/** Build a safe `company_name IN (:t0, :t1, ...)` clause + params. */
function tickerFilter(tickers: string[]) {
  if (tickers.length === 0) return { clause: '', params: [] as const };
  const params = tickers.map((value, i) => ({
    name: `t${i}`,
    value,
    type: 'STRING' as const,
  }));
  const clause = `WHERE company_name IN (${params
    .map((p) => `:${p.name}`)
    .join(', ')})`;
  return { clause, params };
}

function ensureEnabled(res: Response): boolean {
  if (!isSqlBackedEnabled()) {
    res
      .status(503)
      .json({ error: 'Data explorer is not configured on this deployment.' });
    return false;
  }
  return true;
}

// GET /api/series/meta
seriesRouter.get('/meta', requireAuth, async (_req: Request, res: Response) => {
  if (!ensureEnabled(res)) return;
  const table = tableName();
  if (!table) {
    return res.status(500).json({ error: 'Invalid catalog/schema config.' });
  }
  try {
    const result = await executeSql(
      `SELECT DISTINCT company_name FROM ${table} ORDER BY company_name`,
    );
    const tickers = result.records
      .map((r) => r.company_name)
      .filter((t): t is string => Boolean(t));
    res.json({
      tickers,
      metrics: METRIC_KEYS.map((key) => ({
        key,
        label: METRICS[key].label,
        format: METRICS[key].format,
      })),
    });
  } catch (error) {
    console.error('[/api/series/meta] error:', error);
    res.status(500).json({
      error: error instanceof Error ? error.message : 'Failed to load metadata.',
    });
  }
});

// GET /api/series/summary?tickers=
seriesRouter.get(
  '/summary',
  requireAuth,
  async (req: Request, res: Response) => {
    if (!ensureEnabled(res)) return;
    const table = tableName();
    if (!table) {
      return res.status(500).json({ error: 'Invalid catalog/schema config.' });
    }
    const tickers = parseTickers(req.query.tickers);
    const { clause, params } = tickerFilter(tickers);
    try {
      // Latest row per company (most recent Date).
      const result = await executeSql(
        `SELECT company_name, Date, price_close, market_cap, pe_trailing, ` +
          `pe_forward, beta, volume FROM (` +
          `  SELECT *, ROW_NUMBER() OVER ` +
          `    (PARTITION BY company_name ORDER BY Date DESC) AS rn ` +
          `  FROM ${table} ${clause}` +
          `) WHERE rn = 1 ORDER BY market_cap DESC`,
        [...params],
      );
      res.json({ rows: result.records });
    } catch (error) {
      console.error('[/api/series/summary] error:', error);
      res.status(500).json({
        error:
          error instanceof Error ? error.message : 'Failed to load summary.',
      });
    }
  },
);

// GET /api/series?metric=&tickers=
const seriesQuery = z.object({
  metric: z.enum(METRIC_KEYS as [MetricKey, ...MetricKey[]]).default('price_close'),
  tickers: z.string().optional(),
});

seriesRouter.get('/', requireAuth, async (req: Request, res: Response) => {
  if (!ensureEnabled(res)) return;
  const table = tableName();
  if (!table) {
    return res.status(500).json({ error: 'Invalid catalog/schema config.' });
  }
  const parsed = seriesQuery.safeParse(req.query);
  if (!parsed.success) {
    return res
      .status(400)
      .json({ error: 'Invalid query', details: parsed.error.flatten() });
  }
  const metric = parsed.data.metric;
  const column = METRICS[metric].column; // whitelisted identifier
  const tickers = parseTickers(parsed.data.tickers);
  const { clause, params } = tickerFilter(tickers);

  try {
    const result = await executeSql(
      `SELECT CAST(Date AS STRING) AS date, company_name AS ticker, ` +
        `CAST(${column} AS DOUBLE) AS value FROM ${table} ${clause} ` +
        `ORDER BY company_name, Date`,
      [...params],
    );
    const points = result.records
      .filter((r) => r.value !== null)
      .map((r) => ({
        date: r.date,
        ticker: r.ticker,
        value: r.value === null ? null : Number(r.value),
      }));
    res.json({ metric, label: METRICS[metric].label, points });
  } catch (error) {
    console.error('[/api/series] error:', error);
    res.status(500).json({
      error: error instanceof Error ? error.message : 'Failed to load series.',
    });
  }
});
