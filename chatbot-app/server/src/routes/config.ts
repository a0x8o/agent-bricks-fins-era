import {
  Router,
  type Request,
  type Response,
  type Router as RouterType,
} from 'express';
import { isDatabaseAvailable } from '@chat-template/db';
import {
  getAppMode,
  getEmbedUrls,
  isProMode,
  isSqlBackedEnabled,
} from '../lib/pro-config';

export const configRouter: RouterType = Router();

/**
 * GET /api/config - Get application configuration
 * Returns feature flags based on environment configuration.
 *
 * In pro mode this also advertises which workspace-panel features are
 * available (each gated on its backing config) and the iframe embed URLs for
 * the Dashboard tab. In simple mode the pro fields are all off/empty, so the
 * client renders exactly as before.
 */
configRouter.get('/', async (_req: Request, res: Response) => {
  const proMode = isProMode();
  const sqlBacked = proMode && isSqlBackedEnabled();
  const embed = proMode
    ? await getEmbedUrls()
    : { genieUrl: null, dashboardUrl: null };

  res.json({
    appMode: getAppMode(),
    features: {
      chatHistory: isDatabaseAvailable(),
      proMode,
      // SQL-backed panel tabs. The Dashboard tab is now rendered natively from
      // /api/dashboard-data (no iframes), so it needs SQL, not embed URLs.
      graph: sqlBacked,
      dataExplorer: sqlBacked,
      dashboard: sqlBacked,
    },
    embed,
  });
});
