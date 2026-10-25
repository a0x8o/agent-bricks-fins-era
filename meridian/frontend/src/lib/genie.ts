import { api } from "./api";

export interface ChartSpec {
  kind: "kpi" | "line" | "area" | "candlestick" | "multi_line" | "bar" | "bar_h" | "donut" | "treemap" | "scatter" | "table";
  score: number;
  x: string | null;
  y: string[];
  series: string | null;
  normalized: boolean;
  reason: string;
}

export interface GenieResult {
  columns: { name: string; type: string }[];
  rows: unknown[][];
  row_count: number;
  truncated: boolean;
}

export interface GenieMessage {
  conversation_id: string;
  message_id: string;
  status: string;
  text: string | null;
  sql: string | null;
  query_description: string | null;
  result: GenieResult | null;
  suggested: string[];
  attachment_id: string | null;
  tables_used: string[];
  as_of: string | null;
  lookahead_warning: boolean;
  chart_specs?: ChartSpec[];
}

export const askGenie = (
  question: string,
  contextSymbol: string | null,
  asOf: string | null,
  conversationId?: string,
): Promise<GenieMessage> => {
  const body = { question, context_symbol: contextSymbol, as_of: asOf };
  return conversationId
    ? api<GenieMessage>(`/genie/conversations/${conversationId}/messages`, { method: "POST", body: JSON.stringify(body) })
    : api<GenieMessage>("/genie/conversations", { method: "POST", body: JSON.stringify(body) });
};

export const sendFeedback = (cid: string, mid: string, rating: 1 | -1, comment?: string) =>
  api(`/genie/conversations/${cid}/messages/${mid}/feedback`, {
    method: "POST",
    body: JSON.stringify({ rating, comment }),
  });

/** Streaming status via SSE; falls back to nothing when FEATURE_STREAMING off. */
export function streamGenie(cid: string, mid: string, onStatus: (s: string) => void): () => void {
  const es = new EventSource(`/api/genie/conversations/${cid}/messages/${mid}/stream`);
  es.onmessage = (e) => {
    if (e.data === "[DONE]") {
      es.close();
      return;
    }
    try {
      onStatus(JSON.parse(e.data).status);
    } catch { /* ignore */ }
  };
  es.onerror = () => es.close();
  return () => es.close();
}
