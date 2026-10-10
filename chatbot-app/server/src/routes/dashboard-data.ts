import {
  Router,
  type Request,
  type Response,
  type Router as RouterType,
} from 'express';
import { authMiddleware, requireAuth } from '../middleware/auth';
import { executeSql } from '../lib/databricks-sql';
import { isSqlBackedEnabled, getGraphTableConfig } from '../lib/pro-config';

export const dashboardDataRouter: RouterType = Router();
dashboardDataRouter.use(authMiddleware);

const IDENT = /^[A-Za-z0-9_]+$/;

/**
 * GET /api/dashboard-data
 * Returns all dashboard data in one call using the SP's SQL execution API.
 * No iframes needed — data is fetched server-side and rendered natively.
 */
dashboardDataRouter.get('/', requireAuth, async (req: Request, res: Response) => {
  if (!isSqlBackedEnabled()) {
    return res.status(503).json({ error: 'SQL features not configured.' });
  }

  const { catalog, schema } = getGraphTableConfig();
  if (!IDENT.test(catalog) || !IDENT.test(schema)) {
    return res.status(500).json({ error: 'Invalid catalog/schema config.' });
  }

  const ticker = `\`${catalog}\`.\`${schema}\`.ticker_data`;
  const docs = [
    { source: 'Annual Reports', table: `\`${catalog}\`.\`${schema}\`.annual_reports_data` },
    { source: 'Earning Transcripts', table: `\`${catalog}\`.\`${schema}\`.earning_transcripts_data` },
    { source: 'Earning Releases', table: `\`${catalog}\`.\`${schema}\`.earning_releases_data` },
    { source: '10-K Filings', table: `\`${catalog}\`.\`${schema}\`.\`10k_data\`` },
    { source: '10-Q Filings', table: `\`${catalog}\`.\`${schema}\`.\`10q_data\`` },
    { source: '8-K Filings', table: `\`${catalog}\`.\`${schema}\`.\`8k_data\`` },
    { source: 'EDGAR 10-K', table: `\`${catalog}\`.\`${schema}\`.edgar_10k_data` },
    { source: 'EDGAR 10-Q', table: `\`${catalog}\`.\`${schema}\`.edgar_10q_data` },
    { source: 'Synthetic (illustrative)', table: `\`${catalog}\`.\`${schema}\`.synthetic_data` },
  ];
  const payload = `\`${catalog}\`.\`${schema}\`.era_supervisor_payload`;


  try {
    const [snapshot, priceSeries, evSeries, docCounts, agentStats, agentTimeline] =
      await Promise.all([
        // Latest snapshot per company
        // DATE_FORMAT → yyyy-MM-dd so Safari can parse temporal values.
        executeSql(
          `SELECT company_name, DATE_FORMAT(Date, 'yyyy-MM-dd') AS date, ` +
          `CAST(price_close AS DOUBLE) AS price_close, CAST(market_cap AS DOUBLE) AS market_cap, ` +
          `CAST(volume AS DOUBLE) AS volume, CAST(pe_trailing AS DOUBLE) AS pe_trailing, ` +
          `CAST(pe_forward AS DOUBLE) AS pe_forward, CAST(beta AS DOUBLE) AS beta, ` +
          `CAST(ev_ebitda AS DOUBLE) AS ev_ebitda ` +
          `FROM (SELECT *, ROW_NUMBER() OVER (PARTITION BY company_name ORDER BY Date DESC) AS rn FROM ${ticker}) WHERE rn = 1 ORDER BY market_cap DESC`,
        ),
        // Price time series (sampled weekly for performance)
        executeSql(
          `SELECT DATE_FORMAT(Date, 'yyyy-MM-dd') AS date, company_name, CAST(price_close AS DOUBLE) AS value ` +
          `FROM ${ticker} WHERE DAYOFWEEK(Date) = 2 ORDER BY company_name, Date`,
        ),
        // EV/EBITDA time series (weekly)
        executeSql(
          `SELECT DATE_FORMAT(Date, 'yyyy-MM-dd') AS date, company_name, CAST(ev_ebitda AS DOUBLE) AS value ` +
          `FROM ${ticker} WHERE ev_ebitda IS NOT NULL AND DAYOFWEEK(Date) = 2 ORDER BY company_name, Date`,
        ),
        // Research library document counts. One query per table: a workspace
        // without a folder (e.g. no 8-K data) skips that row instead of
        // failing the whole dashboard.
        Promise.all(
          docs.map((d) =>
            executeSql(
              `SELECT '${d.source}' AS source, COUNT(*) AS doc_count FROM ${d.table}`,
            )
              .then((r) => r.records[0] ?? null)
              .catch(() => null),
          ),
        ).then((rows) => ({ records: rows.filter((r) => r !== null) })),
        // Agent operations summary
        executeSql(
          `SELECT COUNT(*) AS total_requests, ` +
          `ROUND(AVG(CAST(execution_duration_ms AS DOUBLE))) AS avg_duration_ms, ` +
          `ROUND(PERCENTILE(CAST(execution_duration_ms AS DOUBLE), 0.95)) AS p95_duration_ms ` +
          `FROM ${payload}`,
        ).catch(() => ({ records: [{ total_requests: '0', avg_duration_ms: '0', p95_duration_ms: '0' }], columns: [], rows: [] })),
        // Agent requests over time (daily)
        executeSql(
          `SELECT DATE_FORMAT(DATE_TRUNC('day', request_time), 'yyyy-MM-dd') AS date, ` +
          `COUNT(*) AS request_count, ` +
          `CAST(status_code AS STRING) AS status_code ` +
          `FROM ${payload} GROUP BY 1, 3 ORDER BY 1`,
        ).catch(() => ({ records: [], columns: [], rows: [] })),
      ]);

    res.json({
      market: {
        snapshot: snapshot.records,
        priceSeries: priceSeries.records,
        evSeries: evSeries.records,
      },
      library: { docCounts: docCounts.records },
      operations: {
        stats: agentStats.records[0] ?? {},
        timeline: agentTimeline.records,
      },
    });
  } catch (error) {
    console.error('[/api/dashboard-data] error:', error);
    res.status(500).json({ error: error instanceof Error ? error.message : 'Failed to load dashboard data.' });
  }
});
