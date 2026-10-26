/** ChartGrid — 1/2/3/4 synchronized chart panes + shared range bar + replay dock. */

import { useState } from "react";
import { useApp } from "../../stores/app";

function barsDimStart(_app: unknown): string | undefined { return undefined; }
import { PriceChart } from "./PriceChart";
import { RangeBar } from "./RangeBar";
import { ReplayBar } from "./ReplayBar";

export function ChartGrid() {
  const app = useApp();
  const [paneSymbols, setPaneSymbols] = useState<Record<number, string>>({});

  const paneCount = { "1": 1, "2h": 2, "2v": 2, "3": 3, "4": 4 }[app.grid];
  const sym = (i: number) => paneSymbols[i] ?? app.symbol;
  const replayActive = app.replay.active;

  const gridCls: Record<string, string> = {
    "1": "grid-cols-1 grid-rows-1",
    "2h": "grid-cols-2 grid-rows-1",
    "2v": "grid-cols-1 grid-rows-2",
    "3": "grid-cols-2 grid-rows-2",
    "4": "grid-cols-2 grid-rows-2",
  };

  return (
    <div className="flex h-full flex-col bg-panel">
      <div className={`grid min-h-0 flex-1 ${gridCls[app.grid]}`}>
        {Array.from({ length: paneCount }).map((_, i) => (
          <div key={i} className={`relative min-h-0 min-w-0 ${i === 2 && app.grid === "3" ? "col-span-2" : ""} ${i > 0 ? "border-l border-t border-hairline" : ""}`}>
            <PaneHeader
              pane={i}
              symbol={sym(i)}
              active={app.activePane === i}
              onSymbol={(s) => setPaneSymbols((m) => ({ ...m, [i]: s }))}
            />
            <div className="absolute inset-x-0 bottom-0 top-7">
              <PriceChart
                symbol={sym(i)}
                range={app.range}
                interval={app.interval}
                chartType={app.chartType}
                adjusted={app.adjusted}
                overlays={app.overlays}
                subPanes={app.subPanes}
                compare={i === 0 ? app.compare : []}
                replayUntil={replayActive ? app.replay.cursor : null}
                dimAfter={replayActive && !app.replay.cursor ? barsDimStart(app) : undefined}
                active={app.activePane === i}
                onFocus={() => app.set({ activePane: i })}
                onSelectTime={replayActive && !app.replay.cursor ? (t) => app.set({ replay: { ...app.replay, cursor: t, playing: false } }) : undefined}
              />
            </div>
            {replayActive && app.activePane === i && <ReplayBar />}
          </div>
        ))}
      </div>
      <RangeBar />
    </div>
  );
}

function PaneHeader({ pane, symbol, active, onSymbol }: {
  pane: number; symbol: string; active: boolean; onSymbol: (s: string) => void;
}) {
  const [edit, setEdit] = useState(false);
  const [v, setV] = useState(symbol);
  return (
    <div className={`flex h-7 items-center gap-2 border-b border-hairline px-2 ${active ? "bg-elevated" : ""}`}>
      {edit ? (
        <input
          autoFocus
          value={v}
          onChange={(e) => setV(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") { onSymbol(v.trim().toUpperCase()); setEdit(false); }
            if (e.key === "Escape") setEdit(false);
          }}
          onBlur={() => setEdit(false)}
          className="h-5 w-20 rounded border border-accent bg-base px-1 text-[11px] outline-none num"
        />
      ) : (
        <button onClick={() => { setV(symbol); setEdit(true); }} className="num text-[12px] font-semibold hover:text-accent" title="Change symbol">
          {symbol}
        </button>
      )}
      <span className="text-[10px] text-fg-3">1D · {pane === 0 ? "main" : `pane ${pane + 1}`}</span>
      {active && <span className="h-1.5 w-1.5 rounded-full bg-accent" title="Active pane" />}
    </div>
  );
}
