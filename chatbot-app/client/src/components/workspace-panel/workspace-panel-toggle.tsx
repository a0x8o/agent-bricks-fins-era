import { PanelRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { useAppConfig } from '@/contexts/AppConfigContext';
import { useWorkspacePanel } from '@/contexts/WorkspacePanelContext';

/**
 * Header button that toggles the workspace panel. Renders nothing unless
 * pro mode is on and at least one panel feature is available.
 */
export function WorkspacePanelToggle() {
  const { proEnabled, graphEnabled, dataExplorerEnabled, dashboardEnabled } =
    useAppConfig();
  const { isOpen, toggle } = useWorkspacePanel();

  if (!proEnabled) return null;
  if (!graphEnabled && !dataExplorerEnabled && !dashboardEnabled) return null;

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant={isOpen ? 'secondary' : 'outline'}
            size="icon"
            className="h-8 w-8"
            onClick={toggle}
            aria-pressed={isOpen}
            aria-label="Toggle analyst view"
            data-testid="workspace-panel-toggle"
          >
            <PanelRight className="h-4 w-4" />
          </Button>
        </TooltipTrigger>
        <TooltipContent>
          <p>{isOpen ? 'Hide' : 'Show'} analyst view</p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
