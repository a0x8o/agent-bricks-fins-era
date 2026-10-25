import { useMemo } from "react";
import { useQuote } from "../../hooks/usePrices";
import { fmtDelta, fmtPct, fmtPrice, pctClass } from "../../lib/format";
import { useApp } from "../../stores/app";
import { Skeleton } from "../ui/primitives";

function cells(q: ReturnType<typeof useQuote>["data"]) {
  if (!q) return null;
  return [
    { label: "1W", v: q.perf.w1 }, { label: "1M", v: q.perf.m1 }, { label: "3M", v: q.perf.m3 },
    { label: "6M", v: q.perf.m6 }, { label: "YTD", v: q.perf.ytd }, { label: "1Y", v: q.perf.y1 },
  ];
}
export function SymbolCard() {
  const app = useApp();
  const until = app.replay.active ? app.replay.cursor : null;
  const { data: q, isLoading } = useQuote(app.symbol, until);

  const perf = useMemo(() => cells(q), [q]);

  if (isLoading)
    return (
      <div className="space-y-2 p-3">
        <Skeleton className="h-8 w-32" />
        <Skeleton className="h-4 w-48" />
        <Skeleton className="h-24" />
      </div>
    );
  if (!q) return null;

  const [int_, dec] = fmtPrice(q.last).split(".");

  return (
    <div className="flex h-full flex-col overflow-auto p-3" aria-label="Symbol detail">
      <div className="flex items-baseline gap-2">
        <span className="num text-[22px] font-semibold leading-none tracking-tight">
          {int_}
          <span className="text-[15px] align-top">.{dec}</span>
        </span>
        <span className={`num text-[11px] ${pctClass(q.change_pct)}`}>
          {fmtDelta(q.change)} ({fmtPct(q.change_pct)})
        </span>
        <span
          className={`ml-auto h-1.5 w-1.5 rounded-full ${q.market_status === "open" ? "bg-up" : "bg-fg-3"}`}
          title={`Market ${q.market_status}`}
        />
      </div>
      <div className="mt-0.5 flex items-center gap-2 text-[10px] text-fg-3">
        <span className="truncate">{q.name}</span>
        <span>·</span>
        <span>{q.currency}</span>
        <span>·</span>
        <span className="num">as of {q.as_of}</span>
      </div>

      {q.news_headline && (
        <div className="mt-2 truncate rounded border border-hairline bg-elevated px-2 py-1 text-[10px] text-fg-2" title={q.news_headline}>
          {q.news_headline}
        </div>
      )}

      {/* performance grid */}
      <div className="mt-3 grid grid-cols-3 gap-1">
        {(perf ?? []).map((c) => (
          <div
            key={c.label}
            className="rounded px-2 py-1.5 text-center"
            style={{
              background: c.v == null ? "var(--elevated)" : c.v >= 0 ? `rgba(34,197,94,${Math.min(Math.abs(c.v) / 40, 0.35)})` : `rgba(239,68,68,${Math.min(Math.abs(c.v) / 40, 0.35)})`,
            }}
          >
            <div className="text-[9px] uppercase tracking-wide text-fg-3">{c.label}</div>
            <div className={`num text-[11px] font-medium ${pctClass(c.v)}`}>{fmtPct(c.v)}</div>
          </div>
        ))}
      </div>

      {/* technicals gauge */}
      <div className="mt-3">
        <TechnicalsGauge score={q.technicals.score} label={q.technicals.label} />
      </div>
    </div>
  );
}

function TechnicalsGauge({ score, label }: { score: number; label: string }) {
  // score -1..1 → needle angle -90..90
  const angle = score * 90;
  const zones = [
    { from: -90, to: -54, color: "var(--down)" },
    { from: -54, to: -18, color: "var(--down)", opacity: 0.55 },
    { from: -18, to: 18, color: "var(--fg-3)", opacity: 0.35 },
    { from: 18, to: 54, color: "var(--up)", opacity: 0.55 },
    { from: 54, to: 90, color: "var(--up)" },
  ];
  const arc = (a0: number, a1: number, r: number) => {
    const cx = 60, cy = 56;
    const p = (a: number) => `${cx + r * Math.cos(((a - 90) * Math.PI) / 180)},${cy + r * Math.sin(((a - 90) * Math.PI) / 180)}`;
    return `M ${p(a0)} A ${r} ${r} 0 0 1 ${p(a1)}`;
  };
  const text = label.replace("_", " ");
  return (
    <div className="rounded border border-hairline bg-elevated p-2">
      <div className="mb-1 flex items-center justify-between text-[9px] uppercase tracking-wide text-fg-3">
        <span>Technicals</span>
        <span className={score > 0.15 ? "text-up" : score < -0.15 ? "text-down" : ""}>{text}</span>
      </div>
      <svg viewBox="0 0 120 62" className="w-full" role="img" aria-label={`Technicals: ${text}`}>
        {zones.map((z, i) => (
          <path key={i} d={arc(z.from, z.to, 50)} stroke={z.color} strokeWidth="7" fill="none" opacity={z.opacity ?? 0.9} />
        ))}
        <g transform={`rotate(${angle} 60 56)`} style={{ transition: "transform .4s ease-out" }}>
          <line x1="60" y1="56" x2="60" y2="14" stroke="var(--fg)" strokeWidth="2" strokeLinecap="round" />
          <circle cx="60" cy="56" r="4" fill="var(--fg)" />
        </g>
      </svg>
      <div className="flex justify-between text-[8px] text-fg-3">
        <span>Strong sell</span><span>Neutral</span><span>Strong buy</span>
      </div>
    </div>
  );
}
