// Load environment variables FIRST before any other imports
import './env';

// Prevent unhandled promise rejections from crashing the Node process.
// The AI SDK stream pipeline can surface rejections from onFinish callbacks
// that are already caught inside the handler — this is a safety net.
process.on('unhandledRejection', (reason) => {
  console.error('[FATAL] Unhandled promise rejection (process kept alive):', reason);
});

import express, {
  type Request,
  type Response,
  type NextFunction,
  type Express,
} from 'express';
import cors from 'cors';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { dirname } from 'node:path';
import { chatRouter } from './routes/chat';
import { historyRouter } from './routes/history';
import { sessionRouter } from './routes/session';
import { messagesRouter } from './routes/messages';
import { configRouter } from './routes/config';
import { graphRouter } from './routes/graph';
import { seriesRouter } from './routes/series';
import { dashboardDataRouter } from './routes/dashboard-data';
import { ChatSDKError } from '@chat-template/core/errors';
import { isDatabaseAvailable } from '@chat-template/db';

// ESM-compatible __dirname
const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const app: Express = express();
const isDevelopment = process.env.NODE_ENV !== 'production';
// Either let PORT be set by env or use 3001 for development and 3000 for production
// The CHAT_APP_PORT can be used to override the port for the chat app.
const PORT =
  process.env.CHAT_APP_PORT ||
  process.env.PORT ||
  (isDevelopment ? 3001 : 3000);

// CORS configuration
app.use(
  cors({
    origin: isDevelopment ? 'http://localhost:3000' : true,
    credentials: true,
  }),
);

// Body parsing middleware
app.use(express.json({ limit: '10mb' }));
app.use(express.urlencoded({ extended: true }));

// Health check endpoint (for Playwright tests)
app.get('/ping', (_req, res) => {
  res.status(200).send('pong');
});

// API routes
app.use('/api/chat', chatRouter);
app.use('/api/history', historyRouter);
app.use('/api/session', sessionRouter);
app.use('/api/messages', messagesRouter);
app.use('/api/config', configRouter);
app.use('/api/graph', graphRouter);
app.use('/api/series', seriesRouter);
app.use('/api/dashboard-data', dashboardDataRouter);

// Serve static files in production
if (!isDevelopment) {
  const clientBuildPath = path.join(__dirname, '../../client/dist');
  app.use(express.static(clientBuildPath));

  // SPA fallback - serve index.html for all non-API routes
  app.get(/^\/(?!api).*/, (_req, res) => {
    res.sendFile(path.join(clientBuildPath, 'index.html'));
  });
}

// Error handling middleware
app.use((err: Error, _req: Request, res: Response, _next: NextFunction) => {
  console.error('Error:', err);

  if (err instanceof ChatSDKError) {
    const response = err.toResponse();
    return res.status(response.status).json(response.json);
  }

  res.status(500).json({
    error: 'Internal Server Error',
    message: isDevelopment ? err.message : 'An unexpected error occurred',
  });
});

// Start MSW mock server in test mode
async function startServer() {
  if (process.env.PLAYWRIGHT === 'True') {
    console.log('[Test Mode] Starting MSW mock server for API mocking...');
    try {
      // Dynamically import MSW setup from tests directory (using relative path from server root)
      const modulePath = path.join(
        dirname(dirname(__dirname)),
        'tests',
        'api-mocking',
        'api-mock-server.ts',
      );
      console.log('[Test Mode] Attempting to load MSW from:', modulePath);

      const { mockServer } = await import(modulePath);

      mockServer.listen({
        onUnhandledRequest: (request: Request) => {
          console.warn(
            `[MSW] Unhandled ${request.method} request to ${request.url}`,
          );
        },
      });

      console.log('[Test Mode] MSW mock server started successfully');
      console.log(
        '[Test Mode] Registered handlers:',
        mockServer.listHandlers().length,
      );
    } catch (error) {
      console.error('[Test Mode] Failed to start MSW:', error);
      console.error(
        '[Test Mode] Error details:',
        error instanceof Error ? error.stack : error,
      );
    }
  }

  // Run DB migration at startup (where SP OAuth credentials are available)
  if (isDatabaseAvailable()) {
    try {
      console.log('[Startup] Database detected — running migrations...');
      const { getConnectionUrl, getSchemaName } = await import('@chat-template/db');
      const { default: postgres } = await import('postgres');
      const { drizzle } = await import('drizzle-orm/postgres-js');
      const { migrate } = await import('drizzle-orm/postgres-js/migrator');
      const url = await getConnectionUrl();
      const schemaName = getSchemaName();
      const schemaConn = postgres(url, { max: 1, connect_timeout: 15 });
      await schemaConn`CREATE SCHEMA IF NOT EXISTS ${schemaConn(schemaName)}`;
      await schemaConn`CREATE SCHEMA IF NOT EXISTS drizzle`;
      await schemaConn.end();
      const migrationConn = postgres(url, { max: 1, connect_timeout: 15 });
      const db = drizzle(migrationConn);
      const path = await import('node:path');
      const { dirname } = await import('node:path');
      const { fileURLToPath } = await import('node:url');
      const __fn = fileURLToPath(import.meta.url);
      const __dn = dirname(__fn);
      const migrationsFolder = path.join(__dn, '../../packages/db/migrations');
      await migrate(db, { migrationsFolder });
      await migrationConn.end();
      console.log('[Startup] Migrations completed successfully');
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      if (msg.includes('permission denied for schema drizzle')) {
        console.warn('[Startup] Migration tracker schema inaccessible — app tables intact, continuing.');
      } else {
        console.error('[Startup] Migration failed (non-fatal):', msg);
      }
    }
  } else {
    console.log('[Startup] No database configured — running in ephemeral mode');
  }

  app.listen(PORT, () => {
    console.log(`Server is running on http://localhost:${PORT}`);
    console.log(`Environment: ${isDevelopment ? 'development' : 'production'}`);
  });
}

startServer();

export default app;
