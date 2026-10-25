import { useEffect, useRef, useState } from "react";
import { Search } from "lucide-react";
import { useSecurities } from "../hooks/usePrices";
import { useApp } from "../stores/app";

/** ⌘K palette — symbol search + actions. */
export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [idx, setIdx] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const app = useApp();
  const results = useSecurities(q, open);

  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setOpen((o) => !o);
        setQ("");
        setIdx(0);
      }
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, []);

  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 30);
  }, [open]);

  if (!open) return null;
  const items = results.data ?? [];
  const pick = (sym: string) => {
    app.setSymbol(sym);
    setOpen(false);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-[15vh]">
      <div className="absolute inset-0 bg-black/50" onClick={() => setOpen(false)} />
      <div className="relative w-[480px] overflow-hidden rounded-lg border border-hairline bg-elevated shadow-2xl">
        <div className="flex items-center gap-2 border-b border-hairline px-3 py-2.5">
          <Search size={14} className="text-fg-3" />
          <input
            ref={inputRef}
            value={q}
            onChange={(e) => { setQ(e.target.value); setIdx(0); }}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") { e.preventDefault(); setIdx(Math.min(idx + 1, items.length - 1)); }
              if (e.key === "ArrowUp") { e.preventDefault(); setIdx(Math.max(idx - 1, 0)); }
              if (e.key === "Enter" && items[idx]) pick(items[idx].symbol);
            }}
            placeholder="Search symbols, actions…"
            className="w-full bg-transparent text-[13px] outline-none placeholder:text-fg-3"
          />
          <kbd className="rounded bg-base px-1.5 py-0.5 text-[9px] text-fg-3">esc</kbd>
        </div>
        <div className="max-h-72 overflow-auto py-1">
          {results.isLoading && <div className="px-3 py-2 text-[11px] text-fg-3">Searching…</div>}
          {items.map((s, i) => (
            <button
              key={s.symbol}
              onClick={() => pick(s.symbol)}
              className={`flex w-full items-center justify-between px-3 py-1.5 text-left ${
                i === idx ? "bg-accent/15" : "hover:bg-hairline"
              }`}
            >
              <span className="num text-[12px] font-medium">{s.symbol}</span>
              <span className="truncate pl-3 text-[11px] text-fg-3">{s.name}</span>
              <span className="pl-2 text-[9px] uppercase text-fg-3">{s.asset_class}</span>
            </button>
          ))}
          {results.isSuccess && !items.length && (
            <div className="px-3 py-4 text-center text-[11px] text-fg-3">No matches for “{q}”</div>
          )}
        </div>
      </div>
    </div>
  );
}
