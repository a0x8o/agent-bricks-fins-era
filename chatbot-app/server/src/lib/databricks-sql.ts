import { getWorkspaceHostname } from '@chat-template/ai-sdk-providers';
import { getDatabricksToken } from '@chat-template/auth';

/**
 * Minimal client for the Databricks SQL Statement Execution API
 * (POST /api/2.0/sql/statements). Used by the pro-mode Graph and Data Explorer
 * endpoints to read the graphrag_* and ticker_data Delta tables.
 *
 * Auth + host resolution reuse the same helpers the model provider uses, so a
 * deployed app authenticates as its service principal and a local dev session
 * uses the Databricks CLI profile.
 */

const API_VERSION = '2.0';

type StatementState =
  | 'PENDING'
  | 'RUNNING'
  | 'SUCCEEDED'
  | 'FAILED'
  | 'CANCELED'
  | 'CLOSED';

interface ColumnInfo {
  name: string;
  type_name: string;
  position: number;
}

interface StatementResponse {
  statement_id: string;
  status: { state: StatementState; error?: { message?: string } };
  manifest?: { schema?: { columns?: ColumnInfo[] } };
  result?: { data_array?: string[][] };
}

export interface SqlResult {
  columns: string[];
  /** Raw rows as string arrays, in column order. */
  rows: string[][];
  /** Rows as objects keyed by column name (string values, NULL -> null). */
  records: Array<Record<string, string | null>>;
}

/** A typed query parameter for safe value interpolation (`:name` markers). */
export interface SqlParam {
  name: string;
  value: string | number | null;
  type?: string; // e.g. "STRING", "INT", "DOUBLE"
}

async function getToken(): Promise<string> {
  if (process.env.DATABRICKS_TOKEN) return process.env.DATABRICKS_TOKEN;
  return getDatabricksToken();
}

function normalizeHost(host: string): string {
  const withScheme = host.startsWith('http') ? host : `https://${host}`;
  return withScheme.replace(/\/$/, '');
}

function toRecords(
  columns: string[],
  rows: string[][],
): Array<Record<string, string | null>> {
  return rows.map((row) => {
    const record: Record<string, string | null> = {};
    columns.forEach((col, i) => {
      record[col] = row[i] ?? null;
    });
    return record;
  });
}

const TERMINAL: StatementState[] = [
  'SUCCEEDED',
  'FAILED',
  'CANCELED',
  'CLOSED',
];

/**
 * Execute a SQL statement and return the (inline) result set. Throws if no
 * warehouse is configured or the statement fails.
 */
export async function executeSql(
  statement: string,
  params?: SqlParam[],
  overrideToken?: string,
): Promise<SqlResult> {
  const warehouseId = process.env.DATABRICKS_WAREHOUSE_ID;
  if (!warehouseId) {
    throw new Error(
      'DATABRICKS_WAREHOUSE_ID is not set; pro-mode SQL features are unavailable.',
    );
  }

  const [spToken, rawHost] = await Promise.all([
    getToken(),
    getWorkspaceHostname(),
  ]);
  const token = overrideToken || spToken;
  const host = normalizeHost(rawHost);
  const baseUrl = `${host}/api/${API_VERSION}/sql/statements`;

  const headers = {
    Authorization: `Bearer ${token}`,
    'Content-Type': 'application/json',
  };

  const submit = await fetch(baseUrl, {
    method: 'POST',
    headers,
    body: JSON.stringify({
      warehouse_id: warehouseId,
      statement,
      disposition: 'INLINE',
      format: 'JSON_ARRAY',
      wait_timeout: '30s',
      on_wait_timeout: 'CONTINUE',
      ...(params && params.length > 0
        ? {
            // The Statement Execution API expects parameter values as strings.
            parameters: params.map((p) => ({
              name: p.name,
              type: p.type,
              value: p.value === null ? null : String(p.value),
            })),
          }
        : {}),
    }),
  });

  if (!submit.ok) {
    const text = await submit.text();
    throw new Error(`SQL submit failed (${submit.status}): ${text}`);
  }

  let body = (await submit.json()) as StatementResponse;

  // Poll until the statement reaches a terminal state.
  while (!TERMINAL.includes(body.status.state)) {
    await new Promise((r) => setTimeout(r, 1000));
    const poll = await fetch(`${baseUrl}/${body.statement_id}`, {
      method: 'GET',
      headers,
    });
    if (!poll.ok) {
      const text = await poll.text();
      throw new Error(`SQL poll failed (${poll.status}): ${text}`);
    }
    body = (await poll.json()) as StatementResponse;
  }

  if (body.status.state !== 'SUCCEEDED') {
    const message = body.status.error?.message ?? body.status.state;
    throw new Error(`SQL statement ${body.status.state}: ${message}`);
  }

  const columns = (body.manifest?.schema?.columns ?? [])
    .sort((a, b) => a.position - b.position)
    .map((c) => c.name);
  const rows = body.result?.data_array ?? [];

  return { columns, rows, records: toRecords(columns, rows) };
}
