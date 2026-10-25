/** Bottom chart bar: range presets, go-to-date, clock+timezone, ADJ, fullscreen. */

import { CalendarDays, Maximize2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useApp, type RangePreset } from "../../stores/app";

const RANGES: RangePreset[] = ["1D", "5D", "1M", "3M", "6M", "YTD", "1Y", "5Y", "ALL"];
const TZS = ["UTC", "America/New_York", "America/Chicago", "America/Los_Angeles", "Europe/London", "Asia/Tokyo"];

export function RangeBar() {
  const app = useApp();
  const [clock, setClock] = useState(new Date());
  const [tz, setTz] = useState("America/New_York");
  const [datePick, setDatePick] = useState(false);
  const dateRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const t = setInterval(() => setClock(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  // number-key range presets
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement).closest("input,textarea")) return;
      const n = Number(e.key);
      if (n >= 1 && n <= 8) app.set({ range: RANGES[n - 1] });
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [app]);

  return (
    <div className="flex h-8 items-center gap-0.5 border-t border-hairline bg-panel px-2 text-[11px]">
      {RANGES.map((r) => (
        <button
          key={r}
          onClick={() => app.set({ range: r })}
          className={`rounded px-1.5 py-0.5 num ${app.range === r ? "bg-accent/15 font-medium text-accent" : "text-fg-3 hover:text-fg-2"}`}
        >
          {r}
        </button>
      ))}
      <div className="mx-1.5 h-4 w-px bg-hairline" />
      <div className="relative">
        <button
          className="flex items-center gap-1 rounded px-1.5 py-0.5 text-fg-3 hover:text-fg-2"
          title="Go to date"
          onClick={() => { setDatePick(!datePick); setTimeout(() => dateRef.current?.showPicker(), 30); }}
        >
          <CalendarDays size={12} />
        </button>
        <input
          ref={dateRef}
          type="date"
          className={`absolute bottom-0 left-0 opacity-0 ${datePick ? "pointer-events-auto" : "pointer-events-none"}`}
          onChange={(e) => {
            if (e.target.value) {
              app.set({ replay: { ...app.replay, active: true, cursor: e.target.value, playing: false } });
              setDatePick(false);
            }
          }}
        />
      </div>
      <div className="flex-1" />
      <span className="num text-[11px] text-fg-3">
        {clock.toLocaleTimeString("en-US", { hour12: false, timeZone: tz })}
      </span>
      <select
        value={tz}
        onChange={(e) => setTz(e.target.value)}
        className="h-6 rounded bg-transparent px-1 text-[10px] text-fg-3 outline-none"
        aria-label="Timezone"
      >
        {TZS.map((t) => <option key={t} value={t}>{t.replace("America/", "").replace("_", " ")}</option>)}
      </select>
      <div className="mx-1.5 h-4 w-px bg-hairline" />
      <button
        onClick={() => app.set({ adjusted: !app.adjusted })}
        className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${app.adjusted ? "bg-accent/15 text-accent" : "text-fg-3 hover:text-fg-2"}`}
        title="Adjusted vs raw prices (recalculates indicators)"
      >
        ADJ
      </button>
      <button
        className="flex h-6 w-6 items-center justify-center rounded text-fg-3 hover:text-fg-2"
        title="Fullscreen"
        onClick={() => document.documentElement.requestFullscreen?.()}
      >
        <Maximize2 size={13} />
      </button>
    </div>
  );
}
