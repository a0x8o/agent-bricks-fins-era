/**
 * Detect You.com-backed tools and URLs so the UI can mark those turns.
 *
 * The workshop MAS exposes You.com as UC functions (`you_web_search`,
 * `you_content_extract`, `you_research`, `era_you_*`) and optionally as the
 * `you-mcp` connection; the supervisor registers them as `Web_Search`,
 * `Web_Content_Extractor` and `Web_Researcher`.
 */

// Only names this project gives You.com tools: you_* / era_you_* functions,
// the you-mcp connection, and the three agent names notebook 04 registers
// (matched as whole names). Generic substrings like "web_search" inside other
// tool names no longer get the You.com mark; ERA's web_* planner keys never
// reach the UI as tool calls.
const YOU_TOOL =
  /you[._-]|youdotcom|(?:^|[^a-z0-9_])(?:web_search|web_content_extractor|web_researcher)$/i;

const YOU_HOSTS = [
  'you.com',
  'www.you.com',
  'api.you.com',
  'ydc-index.io',
  'cdn.you.com',
];

export function isYouComTool(name?: string | null): boolean {
  if (!name) return false;
  return YOU_TOOL.test(name);
}

export function isYouComUrl(url?: string | null): boolean {
  if (!url) return false;
  try {
    const host = new URL(url).hostname.toLowerCase();
    return YOU_HOSTS.some(
      (h) => host === h || host.endsWith(`.${h}`),
    );
  } catch {
    const lowered = url.toLowerCase();
    return (
      lowered.includes('you.com') || lowered.includes('ydc-index.io')
    );
  }
}

export const DEFAULT_DEMO_TICKERS = [
  'NVDA',
  'AAPL',
  'F',
  'PFE',
  'UAL',
  'SPGI',
] as const;

const TICKER_STORAGE_KEY = 'era.demo.tickers';

export function loadDemoTickers(): string[] {
  try {
    const raw = localStorage.getItem(TICKER_STORAGE_KEY);
    if (!raw) return [...DEFAULT_DEMO_TICKERS];
    const parsed = JSON.parse(raw) as unknown;
    if (
      Array.isArray(parsed) &&
      parsed.every((t) => typeof t === 'string' && t.trim())
    ) {
      return parsed.map((t) => t.trim().toUpperCase()).slice(0, 8);
    }
  } catch {
    // ignore
  }
  return [...DEFAULT_DEMO_TICKERS];
}

export function saveDemoTickers(tickers: string[]): void {
  try {
    localStorage.setItem(
      TICKER_STORAGE_KEY,
      JSON.stringify(tickers.map((t) => t.trim().toUpperCase()).slice(0, 8)),
    );
  } catch {
    // ignore
  }
}
