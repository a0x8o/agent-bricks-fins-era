/** Bar Replay dock — selection + playback controls + simulated trades.
 *  "Simulation — no orders are sent." Data is prefetched; playback is local.
 */

import { Pause, Play, SkipBack, SkipForward, StepForward, X } from "lucide-react";
import { useEffect, useState } from "react";
import { usePrices } from "../../hooks/usePrices";
import { fmtDelta, fmtPrice, pctClass } from "../../lib/format";
import { useApp } from "../../stores/app";

const SPEEDS = [
  { v: 10, label: "10× — 10 updates/sec" },
  { v: 3, label: "3×" },
  { v: 1, label: "1×" },
  { v: 0.5, label: "0.5×" },
  { v: 0.3, label: "0.3×" },
  { v: 0.1, label: "0.1× — 1 update per 10 sec" },
];

interface Trade {
  qty: number;      // +long / -short
  avg: number;
  realized: number;
}

export function ReplayBar() {
  const app = useApp();
  const { replay } = app;
  // prefetch the full window once; reveal bars locally — playback never hits the network
  const all = usePrices(app.symbol, app.range, app.interval);
  const bars = all.data?.bars ?? [];
  const [trade, setTrade] = useState<Trade>({ qty: 0, avg: 0, realized: 0 });

  const idx = replay.cursor ? bars.findIndex((b) => b.time >= replay.cursor!) : -1;
  const curBar = idx >= 0 ? bars[idx] : null;

  const step = (n: number) => {
    if (!bars.length) return;
    const next = Math.min((idx < 0 ? 0 : idx) + n, bars.length - 1);
    app.set({ replay: { ...replay, cursor: bars[next].time } });
  };

  useEffect(() => {
    if (!replay.playing) return;
    const ms = 1000 / replay.speed;
    const t = setInterval(() => step(1), ms);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [replay.playing, replay.speed, idx, bars.length]);

  // keyboard: space play/pause, → step, shift+→ 10 bars
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement).closest("input,textarea")) return;
      if (e.code === "Space" && replay.active && replay.cursor) {
        e.preventDefault();
        app.set({ replay: { ...replay, playing: !replay.playing } });
      }
      if (e.key === "ArrowRight" && replay.active && replay.cursor) {
        e.preventDefault();
        step(e.shiftKey ? 10 : 1);
      }
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [replay, idx]);

  const unrealized = curBar && trade.qty !== 0 ? (curBar.close - trade.avg) * trade.qty : 0;
  const buy = (q: number) => {
    if (!curBar) return;
    const newQty = trade.qty + q;
    const avg = trade.qty + q === 0 ? 0 : (trade.avg * trade.qty + curBar.close * q) / newQty;
    setTrade({ qty: newQty, avg, realized: trade.realized });
  };
  const flatten = () => {
    if (!curBar || trade.qty === 0) return;
    setTrade({ qty: 0, avg: 0, realized: trade.realized + unrealized });
  };

  return (
    <div className="absolute inset-x-0 bottom-0 z-10 border-t border-hairline bg-elevated/95 px-2 py-1.5 backdrop-blur"
      style={{ boxShadow: "0 -8px 24px -12px var(--accent)" }}>
      {!replay.cursor ? (
        <div className="flex items-center gap-2 text-[11px] text-fg-2">
          <span className="text-accent">✂</span>
          Pick a start point on the chart — click a bar, or use the calendar in the range bar.
          <button className="rounded bg-accent px-2 py-0.5 text-[10px] text-white"
            onClick={() => bars.length && app.set({ replay: { ...replay, cursor: bars[Math.floor(bars.length * 0.6)].time } })}>
            random
          </button>
          <button className="rounded bg-hairline px-2 py-0.5 text-[10px]" onClick={() => app.set({ replay: { ...replay, active: false } })}>cancel</button>
        </div>
      ) : (
        <div className="flex items-center gap-1.5 text-[11px]">
          <button title="Jump to start" className="rp-btn" onClick={() => bars.length && app.set({ replay: { ...replay, cursor: bars[0].time } })}>
            <SkipBack size={13} />
          </button>
          <button title="Play/Pause (Space)" className="rp-btn" onClick={() => app.set({ replay: { ...replay, playing: !replay.playing } })}>
            {replay.playing ? <Pause size={13} /> : <Play size={13} />}
          </button>
          <button title="Step one bar (→)" className="rp-btn" onClick={() => step(1)}>
            <StepForward size={13} />
          </button>
          <button title="Jump to real time" className="rp-btn" onClick={() => bars.length && app.set({ replay: { ...replay, cursor: bars.at(-1)!.time } })}>
            <SkipForward size={13} />
          </button>
          <select
            value={replay.speed}
            onChange={(e) => app.set({ replay: { ...replay, speed: Number(e.target.value) } })}
            className="h-6 rounded border border-hairline bg-base px-1 text-[10px] outline-none"
            title="Playback speed"
          >
            {SPEEDS.map((s) => <option key={s.v} value={s.v}>{s.label}</option>)}
          </select>
          <span className="num ml-1 text-fg-3">{replay.cursor}</span>

          <div className="mx-2 h-4 w-px bg-hairline" />
          <span className="text-[9px] uppercase tracking-wide text-fg-3">Simulation — no orders are sent</span>
          <button className="rounded bg-down/20 px-2 py-0.5 text-[10px] font-semibold text-down hover:bg-down/30" onClick={() => buy(-1)}>Sell</button>
          <button className="rounded bg-up/20 px-2 py-0.5 text-[10px] font-semibold text-up hover:bg-up/30" onClick={() => buy(1)}>Buy</button>
          <button className="rounded bg-hairline px-2 py-0.5 text-[10px] text-fg-2 hover:bg-hairline/70" onClick={flatten}>Flatten</button>
          <span className="num text-[10px] text-fg-2">
            pos {trade.qty} @ {fmtPrice(trade.avg)}
          </span>
          <span className={`num text-[10px] ${pctClass(unrealized + trade.realized)}`}>
            P&L {fmtDelta(unrealized + trade.realized)}
          </span>
          <div className="flex-1" />
          <button title="Exit replay" className="rp-btn" onClick={() => { app.set({ replay: { ...replay, active: false, cursor: null, playing: false } }); setTrade({ qty: 0, avg: 0, realized: 0 }); }}>
            <X size={13} />
          </button>
        </div>
      )}
      <style>{`.rp-btn{display:flex;height:24px;width:24px;align-items:center;justify-content:center;border-radius:4px;color:var(--fg-2)} .rp-btn:hover{background:var(--hairline);color:var(--fg)}`}</style>
    </div>
  );
}
