import { lazy, Suspense } from "react";
import { Pin } from "lucide-react";
import { useApp } from "../../stores/app";
import { Skeleton } from "../ui/primitives";

const Screener = lazy(() => import("./Screener"));
const Fundamentals = lazy(() => import("./Fundamentals"));
const Portfolio = lazy(() => import("./Portfolio"));
const Heatmap = lazy(() => import("./Heatmap"));
const PinnedInsights = lazy(() => import("./PinnedInsights"));

const TABS = [
  { id: "screener", label: "Screener" },
  { id: "fundamentals", label: "Fundamentals" },
  { id: "portfolio", label: "Portfolio" },
  { id: "heatmap", label: "Heatmap" },
  { id: "pinned", label: "Pinned Insights" },
];

export function BottomDock() {
  const app = useApp();
  return (
    <div className="flex h-full flex-col bg-panel">
      <div className="flex h-8 items-center gap-0.5 border-b border-hairline px-1">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => app.set({ dockTab: t.id })}
            className={`flex h-7 items-center gap-1 rounded px-2 text-[11px] ${
              app.dockTab === t.id ? "bg-elevated font-medium text-fg" : "text-fg-3 hover:text-fg-2"
            }`}
          >
            {t.id === "pinned" && <Pin size={10} className="text-genie" />}
            {t.label}
          </button>
        ))}
      </div>
      <div className="min-h-0 flex-1 overflow-hidden">
        <Suspense fallback={<div className="space-y-2 p-3"><Skeleton className="h-6 w-1/3" /><Skeleton className="h-40" /></div>}>
          {app.dockTab === "screener" && <Screener />}
          {app.dockTab === "fundamentals" && <Fundamentals />}
          {app.dockTab === "portfolio" && <Portfolio />}
          {app.dockTab === "heatmap" && <Heatmap />}
          {app.dockTab === "pinned" && <PinnedInsights />}
        </Suspense>
      </div>
    </div>
  );
}
