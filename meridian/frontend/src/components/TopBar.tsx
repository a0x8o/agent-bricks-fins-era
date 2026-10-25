import {
  Bell, Camera, ChevronDown, LayoutGrid, Moon, Play, Plus, RotateCcw, RotateCw,
  Search, Settings, Sun, TrendingUp, User,
} from "lucide-react";
import { useState } from "react";
import type { Me } from "../lib/api";
import { useApp } from "../stores/app";

const CHART_TYPES = [
  { id: "candles", label: "Candles" },
  { id: "heikin", label: "Heikin Ashi" },
  { id: "line", label: "Line" },
  { id: "area", label: "Area" },
] as const;
const INDICATORS = ["sma", "ema", "dema", "hma", "bollinger", "envelope", "vwap", "ribbon"];
const OSCILLATORS = ["rsi", "macd", "aroon", "stochastic", "atr", "klinger"];
const GRIDS = [
  { id: "1", label: "1" }, { id: "2h", label: "2 │" }, { id: "2v", label: "2 ─" },
  { id: "3", label: "3" }, { id: "4", label: "4" },
] as const;

export function TopBar({ me, warehouseState }: { me?: Me; warehouseState?: string | null }) {
  const app = useApp();
  const [indOpen, setIndOpen] = useState(false);
  const [typeOpen, setTypeOpen] = useState(false);
  const [gridOpen, setGridOpen] = useState(false);
  const [compareInput, setCompareInput] = useState(false);
  const [cmp, setCmp] = useState("");

  const addOverlay = (type: string) => {
    if (app.overlays.length < 5) app.set({ overlays: [...app.overlays, { type, params: {} }] });
    setIndOpen(false);
  };
  const addSub = (type: string) => {
    if (app.subPanes.length < 2) app.set({ subPanes: [...app.subPanes, { type, params: {} }] });
    setIndOpen(false);
  };
  const addCompare = () => {
    const s = cmp.trim().toUpperCase();
    if (s && app.compare.length < 4 && s !== app.symbol) app.set({ compare: [...app.compare, s] });
    setCmp("");
    setCompareInput(false);
  };

  return (
    <header className="flex h-11 items-center gap-1 border-b border-hairline bg-panel px-2">
      <div className="mr-2 flex items-center gap-1.5">
        <TrendingUp size={16} className="text-accent" />
        <span className="text-[13px] font-semibold tracking-tight">Meridian</span>
      </div>

      <button
        onClick={() => window.dispatchEvent(new KeyboardEvent("keydown", { key: "k", metaKey: true }))}
        className="flex h-7 items-center gap-2 rounded border border-hairline bg-elevated px-2 text-[12px] text-fg-2 hover:border-accent"
      >
        <Search size={12} />
        <span className="num font-medium text-fg">{app.symbol}</span>
        <span className="rounded bg-base px-1 text-[9px] text-fg-3">⌘K</span>
      </button>

      {compareInput ? (
        <input
          autoFocus
          value={cmp}
          onChange={(e) => setCmp(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && addCompare()}
          onBlur={addCompare}
          placeholder="add symbol…"
          className="h-7 w-24 rounded border border-accent bg-elevated px-2 text-[12px] outline-none"
        />
      ) : (
        <IconBtn title="Compare symbol" onClick={() => setCompareInput(true)}><Plus size={14} /></IconBtn>
      )}

      <div className="mx-1 h-5 w-px bg-hairline" />

      {/* interval */}
      <select
        value={app.interval}
        onChange={(e) => app.set({ interval: e.target.value })}
        className="h-7 rounded border border-hairline bg-elevated px-1 text-[11px] outline-none"
        aria-label="Interval"
      >
        {["1D", "1W", "1M"].map((i) => <option key={i}>{i}</option>)}
      </select>

      {/* chart type */}
      <div className="relative">
        <button onClick={() => setTypeOpen(!typeOpen)} className="flex h-7 items-center gap-1 rounded px-2 text-[11px] text-fg-2 hover:bg-elevated">
          {CHART_TYPES.find((t) => t.id === app.chartType)?.label}
          <ChevronDown size={12} />
        </button>
        {typeOpen && (
          <Menu onClose={() => setTypeOpen(false)}>
            {CHART_TYPES.map((t) => (
              <MenuItem key={t.id} onClick={() => { app.set({ chartType: t.id }); setTypeOpen(false); }}>
                {t.label}
              </MenuItem>
            ))}
          </Menu>
        )}
      </div>

      {/* indicators */}
      <div className="relative">
        <button onClick={() => setIndOpen(!indOpen)} className="flex h-7 items-center gap-1 rounded px-2 text-[11px] text-fg-2 hover:bg-elevated">
          Indicators <span className="num text-fg-3">{app.overlays.length + app.subPanes.length}</span>
          <ChevronDown size={12} />
        </button>
        {indOpen && (
          <Menu onClose={() => setIndOpen(false)}>
            <div className="px-2 pt-1 text-[9px] uppercase tracking-wide text-fg-3">Overlays</div>
            {INDICATORS.map((i) => <MenuItem key={i} onClick={() => addOverlay(i)}>{i.toUpperCase()}</MenuItem>)}
            <div className="px-2 pt-1 text-[9px] uppercase tracking-wide text-fg-3">Sub-pane</div>
            {OSCILLATORS.map((i) => <MenuItem key={i} onClick={() => addSub(i)}>{i.toUpperCase()}</MenuItem>)}
          </Menu>
        )}
      </div>

      {/* layout picker */}
      <div className="relative">
        <button onClick={() => setGridOpen(!gridOpen)} className="flex h-7 items-center gap-1 rounded px-2 text-[11px] text-fg-2 hover:bg-elevated" title="Chart layout">
          <LayoutGrid size={13} /><ChevronDown size={12} />
        </button>
        {gridOpen && (
          <Menu onClose={() => setGridOpen(false)}>
            {GRIDS.map((g) => (
              <MenuItem key={g.id} onClick={() => { app.set({ grid: g.id }); setGridOpen(false); }}>
                {g.label}-pane
              </MenuItem>
            ))}
          </Menu>
        )}
      </div>

      <IconBtn title="Alerts" onClick={() => app.set({ dockTab: "alerts", dockOpen: true })}><Bell size={14} /></IconBtn>
      <IconBtn title="Bar Replay" onClick={() => app.set({ replay: { ...app.replay, active: !app.replay.active, playing: false } })} className={app.replay.active ? "text-accent" : ""}>
        <Play size={14} />
      </IconBtn>
      <IconBtn title="Undo"><RotateCcw size={14} /></IconBtn>
      <IconBtn title="Redo"><RotateCw size={14} /></IconBtn>

      <div className="flex-1" />

      {warehouseState && warehouseState !== "mock" && warehouseState !== "RUNNING" && (
        <span className="mr-2 rounded bg-warn/15 px-2 py-0.5 text-[10px] text-warn">warehouse {String(warehouseState).toLowerCase()}</span>
      )}
      {me?.auth_mode === "obo" && (
        <span className="mr-2 rounded bg-up/10 px-2 py-0.5 text-[10px] text-up" title="Queries run as you">
          OBO
        </span>
      )}

      <IconBtn title="Snapshot PNG" onClick={() => document.dispatchEvent(new CustomEvent("meridian:snapshot"))}>
        <Camera size={14} />
      </IconBtn>
      <IconBtn
        title={app.theme === "dark" ? "Light theme" : "Dark theme"}
        onClick={() => app.set({ theme: app.theme === "dark" ? "light" : "dark" })}
      >
        {app.theme === "dark" ? <Sun size={14} /> : <Moon size={14} />}
      </IconBtn>
      <IconBtn title="Color-blind palette"
        onClick={() => app.set({ palette: app.palette === "std" ? "cb" : "std" })}
        className={app.palette === "cb" ? "text-accent" : ""}>
        ◐
      </IconBtn>
      <IconBtn title="Settings"><Settings size={14} /></IconBtn>
      <div className="ml-1 flex items-center gap-1.5 rounded border border-hairline px-2 py-1">
        <User size={13} className="text-fg-3" />
        <span className="max-w-[140px] truncate text-[11px] text-fg-2">{me?.user ?? "…"}</span>
      </div>
    </header>
  );
}

function IconBtn({ children, title, onClick, className = "" }: {
  children: React.ReactNode; title: string; onClick?: () => void; className?: string;
}) {
  return (
    <button
      title={title}
      onClick={onClick}
      className={`flex h-7 w-7 items-center justify-center rounded text-fg-2 hover:bg-elevated hover:text-fg ${className}`}
    >
      {children}
    </button>
  );
}

function Menu({ children, onClose }: { children: React.ReactNode; onClose: () => void }) {
  return (
    <>
      <div className="fixed inset-0 z-40" onClick={onClose} />
      <div className="absolute left-0 top-8 z-50 max-h-80 min-w-40 overflow-auto rounded-md border border-hairline bg-elevated py-1 shadow-xl">
        {children}
      </div>
    </>
  );
}

function MenuItem({ children, onClick }: { children: React.ReactNode; onClick: () => void }) {
  return (
    <button onClick={onClick} className="block w-full px-3 py-1.5 text-left text-[12px] text-fg-2 hover:bg-hairline hover:text-fg">
      {children}
    </button>
  );
}
