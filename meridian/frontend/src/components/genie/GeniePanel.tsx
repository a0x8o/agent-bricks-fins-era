/** Genie panel — conversation thread, status timeline, answer cards, composer. */

import DOMPurify from "dompurify";
import { marked } from "marked";
import {
  BarChart3, Pin, RefreshCw, SendHorizonal, Sparkles, Square, Table2,
  ThumbsDown, ThumbsUp, X,
} from "lucide-react";
import { useRef, useState } from "react";
import { askGenie, sendFeedback, type GenieMessage } from "../../lib/genie";
import { useApp } from "../../stores/app";
import { usePins } from "../../stores/pins";
import { AnswerChart } from "./AnswerChart";
import youLogo from "../../assets/you-logo.png";
import { ResultTable } from "../tables/ResultTable";
import { Chip, EmptyState } from "../ui/primitives";

interface Entry {
  id: string;
  question: string;
  msg?: GenieMessage;
  steps: { label: string; at: number }[];
  error?: { code: string; message: string; retryable: boolean };
  feedback?: 1 | -1;
}

const STARTERS = (sym: string) => [
  `How did ${sym} perform against SPY over the last 6 months?`,
  "Top 10 tech stocks by free cash flow yield",
  "Which sectors drove my portfolio's drawdown in Q3?",
  `Show quarterly revenue and operating margin for ${sym} over 3 years`,
  "Compare P/E versus 1Y return for semiconductor names",
  "Which positions have lost more than 15% from their 52-week high?",
];

export function GeniePanel() {
  const app = useApp();
  const pins = usePins();
  const [entries, setEntries] = useState<Entry[]>([]);
  const [convId, setConvId] = useState<string | null>(null);
  const [lastSuggested, setLastSuggested] = useState<string[]>([]);
  const [input, setInput] = useState("");
  const [running, setRunning] = useState(false);
  const abort = useRef<AbortController | null>(null);
  const bottom = useRef<HTMLDivElement>(null);

  const asOf = app.replay.active && app.replay.cursor ? app.replay.cursor : null;
  const ctxSym = app.genieContextSymbol ? app.symbol : null;

  const ask = async (question: string) => {
    if (!question.trim() || running) return;
    const id = crypto.randomUUID();
    const t0 = Date.now();
    setRunning(true);
    setInput("");
    setEntries((e) => [...e, { id, question, steps: [{ label: "Understanding question", at: 0 }] }]);
    setTimeout(() => bottom.current?.scrollIntoView({ behavior: "smooth" }), 50);
    abort.current = new AbortController();

    // status simulation while the request is in flight — replaced by real SSE when enabled
    const stepTimer = simulateSteps(id, setEntries);
    try {
      const msg = await askGenie(question, ctxSym, asOf, convId ?? undefined);
      setConvId(msg.conversation_id);
      if (msg.suggested.length) setLastSuggested(msg.suggested);
      setEntries((e) =>
        e.map((en) =>
          en.id === id
            ? { ...en, msg, steps: [...en.steps, { label: "Done", at: (Date.now() - t0) / 1000 }] }
            : en,
        ),
      );
    } catch (err: any) {
      setEntries((e) =>
        e.map((en) =>
          en.id === id
            ? { ...en, error: { code: err.code ?? "ERROR", message: err.message, retryable: err.retryable ?? false } }
            : en,
        ),
      );
    } finally {
      clearInterval(stepTimer);
      setRunning(false);
      setTimeout(() => bottom.current?.scrollIntoView({ behavior: "smooth" }), 50);
    }
  };

  return (
    <section className="flex h-full flex-col bg-panel" aria-label="Genie assistant">
      {/* header */}
      <div className="flex h-9 items-center gap-1.5 border-b border-hairline px-2">
        <Sparkles size={13} className="text-genie" />
        <span className="text-[11px] font-semibold">Genie</span>
        <img src={youLogo} alt="You.com" title="Live web grounding by You.com" className="ml-auto h-3.5 w-3.5 rounded-[3px] opacity-80" />
        {ctxSym && (
          <Chip tone="genie" onRemove={() => app.set({ genieContextSymbol: false })}>
            {ctxSym}
          </Chip>
        )}
        {asOf && <Chip tone="warn">As of {asOf}</Chip>}
        <div className="flex-1" />
        <button
          className="rounded px-1.5 py-0.5 text-[10px] text-fg-3 hover:bg-elevated hover:text-fg"
          onClick={() => { setEntries([]); setConvId(null); setLastSuggested([]); }}
          title="New chat"
        >
          New chat
        </button>
        <button className="text-fg-3 hover:text-fg" onClick={() => app.set({ genieOpen: false })} title="Close (G)">
          <X size={13} />
        </button>
      </div>

      {/* thread */}
      <div className="min-h-0 flex-1 overflow-auto p-2">
        {!entries.length && (
          <div className="flex h-full flex-col">
            <EmptyState
              icon={<Sparkles size={20} />}
              title="Ask about the data"
              hint="Answers come with generated SQL, the result table, and a chart you can pin to the workspace."
            />
            <div className="grid grid-cols-1 gap-1.5 p-2">
              {STARTERS(app.symbol).map((s) => (
                <button
                  key={s}
                  onClick={() => ask(s)}
                  className="rounded border border-hairline bg-elevated px-2.5 py-1.5 text-left text-[11px] text-fg-2 hover:border-genie hover:text-fg"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}
        {entries.map((en) => (
          <div key={en.id} className="mb-3">
            <div className="mb-1.5 flex justify-end">
              <div className="max-w-[92%] rounded-lg rounded-br-sm bg-accent/15 px-2.5 py-1.5 text-[12px]">
                {en.question}
              </div>
            </div>
            {en.msg ? (
              <AnswerCard entry={en} onFollowUp={(q) => ask(q)} onPin={() =>
                pins.pin({
                  title: en.question.slice(0, 60), question: en.question,
                  sql: en.msg!.sql, chartSpec: en.msg!.chart_specs?.[0] ?? null,
                })
              } onRetry={() => ask(en.question)} onFeedback={(r) => {
                sendFeedback(en.msg!.conversation_id, en.msg!.message_id, r);
                setEntries((e) => e.map((x) => (x.id === en.id ? { ...x, feedback: r } : x)));
              }} />
            ) : en.error ? (
              <div className="rounded-lg border border-down/30 bg-down/10 px-2.5 py-2 text-[11px]">
                <div className="font-medium text-down">{en.error.code}</div>
                <div className="mt-0.5 text-fg-2">{en.error.message}</div>
                {en.error.retryable && (
                  <button onClick={() => ask(en.question)} className="mt-1.5 flex items-center gap-1 rounded bg-elevated px-2 py-0.5 text-[10px] hover:bg-hairline">
                    <RefreshCw size={10} /> Retry
                  </button>
                )}
              </div>
            ) : (
              <StatusTimeline steps={en.steps} />
            )}
          </div>
        ))}
        <div ref={bottom} />
      </div>

      {lastSuggested.length > 0 && (
        <div className="flex flex-wrap items-center gap-1 border-t border-hairline px-2 py-1.5">
          <img src={youLogo} alt="" title="Suggested by Genie · web by You.com" className="h-3 w-3 rounded-[2px] opacity-70" />
          {lastSuggested.slice(0, 4).map((s) => (
            <button
              key={s}
              onClick={() => ask(s)}
              className="rounded-full border border-genie/30 bg-genie/5 px-2 py-0.5 text-[9px] text-genie/90 transition-colors hover:border-genie hover:bg-genie/15 hover:text-genie"
            >
              {s}
            </button>
          ))}
        </div>
      )}
      {/* composer */}
      <div className="border-t border-hairline p-2">
        <div className="rounded-md border border-hairline bg-elevated focus-within:border-genie">
          <textarea
            id="genie-composer"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                ask(input);
              }
            }}
            rows={2}
            placeholder={`Ask about ${ctxSym ?? "the data"}…  (Enter to send)`}
            className="w-full resize-none bg-transparent px-2.5 py-2 text-[12px] outline-none placeholder:text-fg-3"
          />
          <div className="flex items-center justify-between px-2 pb-1.5">
            <span className="num text-[9px] text-fg-3">{input.length}/4000</span>
            {running ? (
              <button className="flex items-center gap-1 rounded bg-down/20 px-2 py-0.5 text-[10px] text-down" onClick={() => abort.current?.abort()}>
                <Square size={9} /> Stop
              </button>
            ) : (
              <button
                className="flex items-center gap-1 rounded bg-genie px-2 py-0.5 text-[10px] font-medium text-white disabled:opacity-40"
                disabled={!input.trim()}
                onClick={() => ask(input)}
              >
                <SendHorizonal size={10} /> Send
              </button>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}

function simulateSteps(id: string, setEntries: React.Dispatch<React.SetStateAction<Entry[]>>) {
  const labels = ["Understanding question", "Finding relevant tables", "Writing SQL", "Running query"];
  let i = 0;
  const t0 = Date.now();
  return setInterval(() => {
    i += 1;
    if (i < labels.length) {
      setEntries((e) =>
        e.map((en) =>
          en.id === id && !en.msg && !en.error
            ? { ...en, steps: [...en.steps, { label: labels[i], at: (Date.now() - t0) / 1000 }] }
            : en,
        ),
      );
    }
  }, 1800);
}

function StatusTimeline({ steps }: { steps: { label: string; at: number }[] }) {
  return (
    <div className="rounded-lg border border-hairline bg-elevated px-2.5 py-2">
      {steps.map((s, i) => (
        <div key={i} className="flex items-center gap-2 py-0.5 text-[11px]">
          <span className={`h-1.5 w-1.5 rounded-full ${i === steps.length - 1 ? "animate-pulse bg-genie" : "bg-fg-3"}`} />
          <span className={i === steps.length - 1 ? "text-fg" : "text-fg-3"}>{s.label}</span>
          <span className="num ml-auto text-[9px] text-fg-3">{s.at.toFixed(1)}s</span>
        </div>
      ))}
    </div>
  );
}

function AnswerCard({ entry, onPin, onRetry, onFeedback, onFollowUp }: {
  entry: Entry;
  onPin: () => void;
  onRetry: () => void;
  onFeedback: (r: 1 | -1) => void;
  onFollowUp: (q: string) => void;
}) {
  const msg = entry.msg!;
  const [showSql, setShowSql] = useState(false);
  const [view, setView] = useState<"chart" | "table">("chart");
  const [chartIdx, setChartIdx] = useState(0);
  const html = msg.text ? DOMPurify.sanitize(marked.parse(msg.text, { async: false }) as string) : null;
  const spec = msg.chart_specs?.[chartIdx];

  return (
    <div className="rounded-lg border border-hairline bg-elevated">
      {/* trust header */}
      <div className="flex items-center gap-1.5 border-b border-hairline px-2.5 py-1.5 text-[9px] text-fg-3">
        <span className="text-genie">✦</span>
        {msg.sql ? (
          <span title={msg.tables_used.join(", ")}>
            Query-backed · {msg.tables_used.length} source{msg.tables_used.length === 1 ? "" : "s"}
          </span>
        ) : (
          <span className="text-warn">Narrative only — not query-backed</span>
        )}
        {msg.as_of && <Chip tone="warn">as of {msg.as_of}</Chip>}
        {msg.lookahead_warning && <Chip tone="down">Possible look-ahead</Chip>}
        {msg.result?.truncated && <Chip tone="warn">truncated</Chip>}
      </div>

      {html && (
        <div
          className="prose-sm px-2.5 py-2 text-[12px] leading-relaxed text-fg [&_code]:text-genie"
          dangerouslySetInnerHTML={{ __html: html }}
        />
      )}

      {msg.result && msg.result.row_count > 0 && (
        <div className="border-t border-hairline">
          <div className="flex items-center gap-1 px-2 py-1">
            <ViewToggle icon={<BarChart3 size={11} />} active={view === "chart"} onClick={() => setView("chart")} label="chart" />
            <ViewToggle icon={<Table2 size={11} />} active={view === "table"} onClick={() => setView("table")} label="table" />
            {msg.chart_specs && msg.chart_specs.length > 1 && view === "chart" && (
              <select
                value={chartIdx}
                onChange={(e) => setChartIdx(Number(e.target.value))}
                className="ml-1 h-5 rounded border border-hairline bg-base px-1 text-[9px] outline-none"
                title="Chart type"
              >
                {msg.chart_specs.map((s, i) => (
                  <option key={i} value={i}>{s.kind}{s.normalized ? " (rebased)" : ""}</option>
                ))}
              </select>
            )}
            <span className="num ml-auto text-[9px] text-fg-3">{msg.result.row_count} rows</span>
          </div>
          {view === "chart" && spec && spec.kind !== "table" ? (
            <AnswerChart spec={spec} result={msg.result} />
          ) : (
            <ResultTable result={msg.result} compact />
          )}
        </div>
      )}

      {msg.sql && (
        <div className="border-t border-hairline">
          <button onClick={() => setShowSql(!showSql)} className="flex w-full items-center gap-1 px-2.5 py-1 text-[10px] text-fg-3 hover:text-fg-2">
            {showSql ? "▾" : "▸"} View SQL
          </button>
          {showSql && (
            <div className="px-2.5 pb-2">
              {msg.query_description && <div className="mb-1 text-[10px] text-fg-3 italic">{msg.query_description}</div>}
              <pre className="num overflow-auto rounded bg-base p-2 text-[10px] leading-relaxed text-fg-2">{msg.sql}</pre>
              <button
                className="mt-1 rounded bg-hairline px-2 py-0.5 text-[9px] hover:bg-hairline/70"
                onClick={() => navigator.clipboard.writeText(msg.sql!)}
              >
                copy SQL
              </button>
            </div>
          )}
        </div>
      )}

      {msg.suggested.length > 0 && (
        <div className="flex flex-wrap gap-1 border-t border-hairline px-2.5 py-1.5">
          {msg.suggested.slice(0, 3).map((s) => (
            <button
              key={s}
              onClick={() => onFollowUp(s)}
              className="rounded-full border border-hairline px-2 py-0.5 text-[9px] text-fg-3 transition-colors hover:border-genie hover:bg-genie/10 hover:text-genie"
            >
              {s}
            </button>
          ))}
        </div>
      )}

      {/* actions */}
      <div className="flex items-center gap-0.5 border-t border-hairline px-1.5 py-1">
        <Action title="Pin to workspace" onClick={onPin}><Pin size={11} /></Action>
        <Action title="Retry" onClick={onRetry}><RefreshCw size={11} /></Action>
        <div className="flex-1" />
        <Action title="Good answer" active={entry.feedback === 1} onClick={() => onFeedback(1)}><ThumbsUp size={11} /></Action>
        <Action title="Bad answer" active={entry.feedback === -1} onClick={() => onFeedback(-1)}><ThumbsDown size={11} /></Action>
      </div>
    </div>
  );
}

function ViewToggle({ icon, label, active, onClick }: { icon: React.ReactNode; label: string; active: boolean; onClick: () => void }) {
  return (
    <button onClick={onClick} className={`flex items-center gap-1 rounded px-1.5 py-0.5 text-[9px] ${active ? "bg-genie/15 text-genie" : "text-fg-3 hover:text-fg-2"}`}>
      {icon}{label}
    </button>
  );
}

function Action({ children, title, onClick, active }: { children: React.ReactNode; title: string; onClick: () => void; active?: boolean }) {
  return (
    <button title={title} onClick={onClick} className={`flex h-6 w-6 items-center justify-center rounded ${active ? "text-genie" : "text-fg-3 hover:bg-hairline hover:text-fg-2"}`}>
      {children}
    </button>
  );
}
