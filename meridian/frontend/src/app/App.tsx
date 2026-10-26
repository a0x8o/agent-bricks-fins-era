import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";
import { Panel, PanelGroup, PanelResizeHandle } from "react-resizable-panels";
import { BottomDock } from "../components/dock/BottomDock";
import { GeniePanel } from "../components/genie/GeniePanel";
import { CommandPalette } from "../components/CommandPalette";
import { DrawingRail } from "../components/DrawingRail";
import { RightRail } from "../components/RightRail";
import { TopBar } from "../components/TopBar";
import { ChartGrid } from "../components/charts/ChartGrid";
import { SymbolCard } from "../components/symbol-card/SymbolCard";
import { Watchlist } from "../components/watchlist/Watchlist";
import { getHealth, getMe } from "../lib/api";
import { useApp } from "../stores/app";

export default function App() {
  const { theme, palette, genieOpen, set } = useApp();
  const me = useQuery({ queryKey: ["me"], queryFn: getMe, staleTime: 300_000 });
  const health = useQuery({ queryKey: ["health"], queryFn: getHealth, refetchInterval: 60_000 });

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.documentElement.dataset.palette = palette;
  }, [theme, palette]);

  // global shortcuts
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if (e.key === "g" && !e.metaKey && !e.ctrlKey && !(e.target as HTMLElement).closest("input,textarea"))
        set({ genieOpen: !useApp.getState().genieOpen });
      if (e.key === "/" && !(e.target as HTMLElement).closest("input,textarea")) {
        e.preventDefault();
        set({ genieOpen: true });
        document.getElementById("genie-composer")?.focus();
      }
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [set]);

  return (
    <div className="flex h-screen flex-col bg-base text-fg">
      {me.data?.auth_mode === "service_principal" && (
        <div className="bg-warn/15 px-3 py-1 text-center text-[11px] text-warn">
          Service-principal mode — queries run as the app identity, not as you.
        </div>
      )}
      <TopBar me={me.data} warehouseState={health.data?.warehouse} />
      <div className="flex min-h-0 flex-1">
        <DrawingRail />
        <PanelGroup direction="horizontal" className="flex-1" autoSaveId="meridian-h">
          <Panel defaultSize={62} minSize={30}>
            <PanelGroup direction="vertical" autoSaveId="meridian-v">
              <Panel defaultSize={72} minSize={35}>
                <ChartGrid />
              </Panel>
              <PanelResizeHandle className="h-px bg-hairline transition-colors data-[resize-handle-state=drag]:bg-accent" />
              <Panel defaultSize={28} minSize={12} collapsible>
                <BottomDock />
              </Panel>
            </PanelGroup>
          </Panel>
          <PanelResizeHandle className="w-px bg-hairline transition-colors data-[resize-handle-state=drag]:bg-accent" />
          <Panel defaultSize={16} minSize={10} collapsible>
            <div className="flex h-full flex-col">
              <div className="min-h-0 flex-[3] overflow-hidden">
                <Watchlist />
              </div>
              <div className="min-h-0 flex-[2] border-t border-hairline">
                <SymbolCard />
              </div>
            </div>
          </Panel>
          {genieOpen && (
            <>
              <PanelResizeHandle className="w-px bg-hairline transition-colors data-[resize-handle-state=drag]:bg-accent" />
              <Panel defaultSize={22} minSize={14}>
                <GeniePanel />
              </Panel>
            </>
          )}
        </PanelGroup>
        <RightRail />
      </div>
      <CommandPalette />
    </div>
  );
}
