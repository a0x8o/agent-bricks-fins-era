import {
  Crosshair, Lock, Magnet, Minus, Paintbrush, PencilRuler, Ruler,
  Slash, Type, ZoomIn, Trash2, EyeOff,
} from "lucide-react";
import { useState } from "react";

const TOOLS = [
  { id: "crosshair", icon: Crosshair, label: "Crosshair" },
  { id: "trendline", icon: Slash, label: "Trendline" },
  { id: "hline", icon: Minus, label: "Horizontal line" },
  { id: "channel", icon: PencilRuler, label: "Regression channel" },
  { id: "brush", icon: Paintbrush, label: "Brush" },
  { id: "text", icon: Type, label: "Text" },
  { id: "ruler", icon: Ruler, label: "Measure" },
  { id: "zoom", icon: ZoomIn, label: "Zoom" },
];

export function DrawingRail() {
  const [tool, setTool] = useState("crosshair");
  const [magnet, setMagnet] = useState(true);
  const [locked, setLocked] = useState(false);
  const [hidden, setHidden] = useState(false);

  const pick = (id: string) => {
    setTool(id);
    window.dispatchEvent(new CustomEvent("meridian:tool", { detail: id }));
  };

  return (
    <nav className="flex w-9 flex-col items-center gap-0.5 border-r border-hairline bg-panel py-2" aria-label="Drawing tools">
      {TOOLS.map(({ id, icon: Icon, label }) => (
        <button
          key={id}
          title={label}
          onClick={() => pick(id)}
          className={`flex h-7 w-7 items-center justify-center rounded ${
            tool === id ? "bg-accent/15 text-accent" : "text-fg-3 hover:bg-elevated hover:text-fg-2"
          }`}
        >
          <Icon size={14} />
        </button>
      ))}
      <div className="my-1 h-px w-5 bg-hairline" />
      <button title="Magnet (snap to OHLC)" onClick={() => setMagnet(!magnet)}
        className={`flex h-7 w-7 items-center justify-center rounded ${magnet ? "text-accent" : "text-fg-3 hover:bg-elevated"}`}>
        <Magnet size={14} />
      </button>
      <button title={locked ? "Unlock drawings" : "Lock drawings"} onClick={() => setLocked(!locked)}
        className={`flex h-7 w-7 items-center justify-center rounded ${locked ? "text-warn" : "text-fg-3 hover:bg-elevated"}`}>
        <Lock size={14} />
      </button>
      <button title="Hide drawings" onClick={() => setHidden(!hidden)}
        className={`flex h-7 w-7 items-center justify-center rounded ${hidden ? "text-warn" : "text-fg-3 hover:bg-elevated"}`}>
        <EyeOff size={14} />
      </button>
      <div className="flex-1" />
      <button title="Delete all drawings" className="flex h-7 w-7 items-center justify-center rounded text-fg-3 hover:bg-elevated hover:text-down">
        <Trash2 size={14} />
      </button>
    </nav>
  );
}
