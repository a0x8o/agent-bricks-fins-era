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

export const graphRouter: RouterType = Router();
graphRouter.use(authMiddleware);

/**
 * GET /api/graph?focus=<nodeId>&limit=<n>
 *
 * Returns a node/edge graph derived from the graphrag_vertices / graphrag_edges
 * Delta tables (created by the optional OntoBricks GraphRAG notebook).
 *
 *  - No focus → overview: the Company nodes plus a sample of each company's most
 *    recent trading days (keeps the network legible against ~1.7k day nodes).
 *  - focus=<company|ticker|tradingDayId> → that company's subgraph (the company
 *    node + its recent trading days, chained by NEXT_DAY).
 */

const querySchema = z.object({
  focus: z.string().trim().min(1).max(128).optional(),
  limit: z.coerce.number().int().min(7).max(600).default(150),
});

// Identifier guard for the admin-provided catalog/schema (not user input).
const IDENT = /^[A-Za-z0-9_]+$/;

interface GraphNode {
  id: string;
  type: string;
  label: string;
  ticker: string | null;
  props: Record<string, string | null>;
}

interface GraphEdge {
  source: string;
  target: string;
  type: string;
  weight?: number | null;
}

// Hub node types that group/relate companies (added by the enrichment step in
// the GraphRAG notebook): a MAG7 index, sectors, beta tiers, valuation tiers.
const HUB_TYPES = ['Index', 'Sector', 'BetaTier', 'ValuationTier'];

const NODE_COLS =
  'id, type, ticker, name, prop_market_cap, prop_beta, prop_pe_trailing, ' +
  'prop_pe_forward, prop_ev_ebitda, prop_date, prop_price_close, ' +
  'prop_volume, prop_daily_return';

function toNode(r: Record<string, string | null>): GraphNode {
  const type = r.type ?? 'Unknown';
  let label: string;
  if (type === 'Company') label = r.ticker ?? r.id ?? '';
  else if (type === 'TradingDay') label = r.prop_date ?? r.id ?? '';
  else label = r.name ?? r.id ?? '';
  return {
    id: r.id ?? '',
    type,
    label,
    ticker: r.ticker ?? null,
    props: {
      market_cap: r.prop_market_cap,
      beta: r.prop_beta,
      pe_trailing: r.prop_pe_trailing,
      pe_forward: r.prop_pe_forward,
      ev_ebitda: r.prop_ev_ebitda,
      date: r.prop_date,
      price_close: r.prop_price_close,
      volume: r.prop_volume,
      daily_return: r.prop_daily_return,
    },
  };
}

graphRouter.get('/', requireAuth, async (req: Request, res: Response) => {
  if (!isSqlBackedEnabled()) {
    return res
      .status(503)
      .json({ error: 'Graph feature is not configured on this deployment.' });
  }

  const parsed = querySchema.safeParse(req.query);
  if (!parsed.success) {
    return res
      .status(400)
      .json({ error: 'Invalid query', details: parsed.error.flatten() });
  }
  const { focus, limit } = parsed.data;

  const { catalog, schema } = getGraphTableConfig();
  if (!IDENT.test(catalog) || !IDENT.test(schema)) {
    return res
      .status(500)
      .json({ error: 'Invalid GRAPH_CATALOG/GRAPH_SCHEMA configuration.' });
  }
  const vertices = `\`${catalog}\`.\`${schema}\`.graphrag_vertices`;
  const edges = `\`${catalog}\`.\`${schema}\`.graphrag_edges`;

  try {
    const nodes: GraphNode[] = [];

    // Resolve the focus ticker (a TradingDay id resolves to its company).
    let focusTicker: string | null = null;
    if (focus) {
      const lookup = await executeSql(
        `SELECT ticker FROM ${vertices} WHERE id = :focus LIMIT 1`,
        [{ name: 'focus', value: focus, type: 'STRING' }],
      );
      focusTicker = lookup.records[0]?.ticker ?? null;
    }

    // Always include the company-level scaffold: every Company node plus the
    // hub nodes (index / sectors / beta + valuation tiers). These give the graph
    // multiple centers of gravity and surface the cross-company relationships.
    const hubList = HUB_TYPES.map((t) => `'${t}'`).join(',');
    const scaffold = await executeSql(
      `SELECT ${NODE_COLS} FROM ${vertices} ` +
        `WHERE type = 'Company' OR type IN (${hubList})`,
    );
    nodes.push(...scaffold.records.map(toNode));

    if (focusTicker) {
      // Focus: add the focused company's recent trading days (its detail layer).
      // `limit` is a zod-validated integer (server-controlled), safe to inline.
      const days = await executeSql(
        `SELECT ${NODE_COLS} FROM ${vertices} WHERE type = 'TradingDay' AND ticker = :t ` +
          `ORDER BY prop_date DESC LIMIT ${limit}`,
        [{ name: 't', value: focusTicker, type: 'STRING' }],
      );
      nodes.push(...days.records.map(toNode));
    } else {
      // Overview: a small sample of recent days per company so the day chains
      // are visible without burying the company-level web.
      const perCompany = Math.max(4, Math.min(12, Math.floor(limit / 12)));
      const recentDays = await executeSql(
        `SELECT ${NODE_COLS} FROM (` +
          `  SELECT ${NODE_COLS}, ROW_NUMBER() OVER ` +
          `    (PARTITION BY ticker ORDER BY prop_date DESC) AS rn ` +
          `  FROM ${vertices} WHERE type = 'TradingDay'` +
          `) WHERE rn <= ${perCompany}`,
      );
      nodes.push(...recentDays.records.map(toNode));
    }

    // Edges: fetch all (table is small) and keep only those fully inside the
    // selected node set. weight carries the correlation strength.
    const nodeIds = new Set(nodes.map((n) => n.id));
    const allEdges = await executeSql(
      `SELECT src, dst, relationship, weight FROM ${edges}`,
    );
    const graphEdges: GraphEdge[] = [];
    for (const e of allEdges.records) {
      if (e.src && e.dst && nodeIds.has(e.src) && nodeIds.has(e.dst)) {
        const w = e.weight === null || e.weight === undefined ? null : Number(e.weight);
        graphEdges.push({
          source: e.src,
          target: e.dst,
          type: e.relationship ?? 'RELATED',
          weight: Number.isFinite(w as number) ? w : null,
        });
      }
    }

    res.json({ nodes, edges: graphEdges, focus: focus ?? null });
  } catch (error) {
    console.error('[/api/graph] error:', error);
    res.status(500).json({
      error:
        error instanceof Error ? error.message : 'Failed to load graph data.',
    });
  }
});
