import {
  Bell, Calendar, Clock3, HelpCircle, Layers, ListChecks,
  Newspaper, Sparkles,
} from "lucide-react";
import { useApp } from "../stores/app";

const ICONS = [
  { id: "watchlist", icon: ListChecks, label: "Watchlist" },
  { id: "alerts", icon: Bell, label: "Alerts" },
  { id: "objects", icon: Layers, label: "Object tree" },
  { id: "genie", icon: Sparkles, label: "Genie", accent: true },
  { id: "datawin", icon: Clock3, label: "Data window" },
  { id: "calendar", icon: Calendar, label: "Calendar" },
  { id: "news", icon: Newspaper, label: "News" },
  { id: "help", icon: HelpCircle, label: "Help" },
];

export function RightRail() {
  const app = useApp();
  return (
    <nav className="flex w-9 flex-col items-center gap-0.5 border-l border-hairline bg-panel py-2" aria-label="Utility panels">
      {ICONS.map(({ id, icon: Icon, label, accent }) => (
        <button
          key={id}
          title={label}
          onClick={() => {
            if (id === "genie") app.set({ genieOpen: !app.genieOpen });
            else app.set({ dockTab: id, dockOpen: true });
          }}
          className={`flex h-7 w-7 items-center justify-center rounded ${
            id === "genie" && app.genieOpen
              ? "bg-genie/15 text-genie"
              : accent
                ? "text-genie/70 hover:bg-elevated hover:text-genie"
                : "text-fg-3 hover:bg-elevated hover:text-fg-2"
          }`}
        >
          <Icon size={14} />
        </button>
      ))}
    </nav>
  );
}
