/**
 * Databricks Genie API client.
 *
 * Wraps the Genie Conversations REST API to provide:
 *  - start / continue conversations
 *  - poll until a message reaches a terminal state
 *  - retrieve SQL query results (columns + rows)
 */

import { getDatabricksToken } from '@chat-template/auth';
import { getHostUrl } from '@chat-template/utils';

// ─── Types ───────────────────────────────────────────────────────────────────

export type GenieMessageStatus =
  | 'QUEUED'
  | 'FILTERING_CONTEXT'
  | 'ASKING_AI'
  | 'EXECUTING_QUERY'
  | 'COMPLETED'
  | 'FAILED'
  | 'CANCELLED'
  | 'QUERY_RESULT_EXPIRED';

export interface GenieAttachment {
  text?: { content: string };
  query?: {
    query: string;
    description?: string;
  };
}

export interface GenieMessage {
  id: string;
  space_id: string;
  conversation_id: string;
  content?: string;
  status: GenieMessageStatus;
  attachments?: GenieAttachment[];
  created_at?: string;
  // MessageError in the API is { error, type }; `message` kept as a fallback.
  error?: { error?: string; type?: string; message?: string };
}

export interface GenieQueryResult {
  statement_id?: string;
  columns?: Array<{ name: string; type_name: string }>;
  data_array?: string[][];
  row_count?: number;
  truncated?: boolean;
}

export interface GenieConversationStart {
  conversation_id: string;
  message_id: string;
  message?: GenieMessage;
}

// ─── Configuration ───────────────────────────────────────────────────────────

const POLL_INTERVAL_MS = 1_500;
const MAX_POLL_ATTEMPTS = 120; // 3 min max

const TERMINAL_STATUSES: Set<GenieMessageStatus> = new Set([
  'COMPLETED',
  'FAILED',
  'CANCELLED',
  'QUERY_RESULT_EXPIRED',
]);

// ─── Helpers ─────────────────────────────────────────────────────────────────

async function genieHeaders(userToken?: string): Promise<Headers> {
  // Priority: the end user's forwarded token (Genie permissions evaluated
  // against the real user) > GENIE_PAT > SP token. The token is passed per
  // call, never stored at module level: concurrent requests must not see
  // each other's credentials.
  const token =
    userToken ||
    process.env.GENIE_PAT ||
    process.env.DATABRICKS_TOKEN ||
    (await getDatabricksToken());
  const h = new Headers();
  h.set('Authorization', `Bearer ${token}`);
  h.set('Content-Type', 'application/json');
  return h;
}

function genieBase(): string {
  return `${getHostUrl()}/api/2.0/genie/spaces`;
}

async function genieRequest<T>(
  path: string,
  init?: RequestInit,
  token?: string,
): Promise<T> {
  const url = `${genieBase()}${path}`;
  const headers = await genieHeaders(token);

  const res = await fetch(url, {
    ...init,
    headers,
  });

  if (!res.ok) {
    const body = await res.text().catch(() => '(no body)');
    throw new Error(
      `Genie API ${init?.method ?? 'GET'} ${path} failed (${res.status}): ${body}`,
    );
  }
  return res.json() as Promise<T>;
}

// ─── Public API ──────────────────────────────────────────────────────────────

/** Start a brand-new Genie conversation with an initial question. */
export async function startConversation(
  spaceId: string,
  content: string,
  token?: string,
): Promise<GenieConversationStart> {
  console.log(`[Genie] Starting conversation in space ${spaceId}`);
  return genieRequest<GenieConversationStart>(
    `/${spaceId}/start-conversation`,
    {
      method: 'POST',
      body: JSON.stringify({ content }),
    },
    token,
  );
}

/** Send a follow-up message in an existing conversation. */
export async function sendMessage(
  spaceId: string,
  conversationId: string,
  content: string,
  token?: string,
): Promise<{ message_id: string }> {
  console.log(
    `[Genie] Sending message in conversation ${conversationId}`,
  );
  return genieRequest<{ message_id: string }>(
    `/${spaceId}/conversations/${conversationId}/messages`,
    {
      method: 'POST',
      body: JSON.stringify({ content }),
    },
    token,
  );
}

/** Retrieve the current state of a Genie message. */
export async function getMessage(
  spaceId: string,
  conversationId: string,
  messageId: string,
  token?: string,
): Promise<GenieMessage> {
  return genieRequest<GenieMessage>(
    `/${spaceId}/conversations/${conversationId}/messages/${messageId}`,
    undefined,
    token,
  );
}

/**
 * Poll a Genie message until it reaches a terminal status.
 *
 * Calls `onStatus` on each poll so callers can emit progress updates.
 */
export async function pollMessage(
  spaceId: string,
  conversationId: string,
  messageId: string,
  onStatus?: (status: GenieMessageStatus, attempt: number) => void,
  token?: string,
): Promise<GenieMessage> {
  for (let attempt = 1; attempt <= MAX_POLL_ATTEMPTS; attempt++) {
    const msg = await getMessage(spaceId, conversationId, messageId, token);
    onStatus?.(msg.status, attempt);

    if (TERMINAL_STATUSES.has(msg.status)) {
      console.log(
        `[Genie] Message ${messageId} reached terminal status: ${msg.status}`,
      );
      return msg;
    }

    await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
  }

  throw new Error(
    `[Genie] Message ${messageId} did not complete within ${MAX_POLL_ATTEMPTS * POLL_INTERVAL_MS / 1000}s`,
  );
}

/** Retrieve the SQL query result rows for a completed message. */
export async function getQueryResult(
  spaceId: string,
  conversationId: string,
  messageId: string,
  token?: string,
): Promise<GenieQueryResult> {
  console.log(`[Genie] Fetching query result for message ${messageId}`);
  const raw = await genieRequest<GenieQueryResultResponse>(
    `/${spaceId}/conversations/${conversationId}/messages/${messageId}/query-result`,
    undefined,
    token,
  );
  // The API wraps the result in a Statement Execution response:
  // { statement_response: { manifest: { schema: { columns } }, result: { data_array } } }.
  // Reading columns/data_array at the top level found nothing, so no table or
  // chart ever rendered. The flat shape is still accepted.
  const sr = raw.statement_response;
  if (!sr) return raw as GenieQueryResult;
  return {
    statement_id: sr.statement_id,
    columns: sr.manifest?.schema?.columns,
    data_array: sr.result?.data_array,
    row_count: sr.manifest?.total_row_count,
    truncated: sr.manifest?.truncated,
  };
}

interface GenieQueryResultResponse extends GenieQueryResult {
  statement_response?: {
    statement_id?: string;
    manifest?: {
      schema?: { columns?: Array<{ name: string; type_name: string }> };
      total_row_count?: number;
      truncated?: boolean;
    };
    result?: { data_array?: string[][] };
  };
}

// ─── High-level helper ───────────────────────────────────────────────────────

export interface GenieFullResponse {
  message: GenieMessage;
  queryResult?: GenieQueryResult;
  /** Narrative text assembled from all text attachments. */
  narrativeText: string;
  /** SQL query from the first query attachment (if any). */
  sql?: string;
  /** Error string when the message FAILED. */
  error?: string;
}

/**
 * All-in-one: start or continue a conversation, poll to completion,
 * and fetch query results if a SQL attachment is present.
 */
export async function askGenie(
  spaceId: string,
  content: string,
  conversationId?: string,
  onStatus?: (status: GenieMessageStatus, attempt: number) => void,
  token?: string,
): Promise<GenieFullResponse> {
  let convId: string;
  let msgId: string;

  if (conversationId) {
    const resp = await sendMessage(spaceId, conversationId, content, token);
    convId = conversationId;
    msgId = resp.message_id;
  } else {
    const resp = await startConversation(spaceId, content, token);
    convId = resp.conversation_id;
    msgId = resp.message_id;
  }

  const message = await pollMessage(
    spaceId,
    convId,
    msgId,
    onStatus,
    token,
  );

  // Assemble narrative text from attachments
  const textParts =
    message.attachments
      ?.filter((a) => a.text?.content)
      .map((a) => a.text!.content) ?? [];
  const narrativeText =
    textParts.join('\n\n') || message.content || '';

  // Extract SQL
  const queryAttachment = message.attachments?.find((a) => a.query);
  const sql = queryAttachment?.query?.query;

  // Fetch query result if SQL was executed
  let queryResult: GenieQueryResult | undefined;
  if (sql && message.status === 'COMPLETED') {
    try {
      queryResult = await getQueryResult(spaceId, convId, msgId, token);
    } catch (err) {
      console.warn('[Genie] Failed to fetch query result:', err);
    }
  }

  return {
    message: { ...message, conversation_id: convId },
    queryResult,
    narrativeText,
    sql,
    error:
      message.status === 'FAILED'
        ? message.error?.error ??
          message.error?.message ??
          'Genie query failed'
        : undefined,
  };
}
