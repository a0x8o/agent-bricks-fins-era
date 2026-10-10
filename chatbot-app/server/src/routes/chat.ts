import {
  Router,
  type Request,
  type Response,
  type Router as RouterType,
} from 'express';
import {
  convertToModelMessages,
  createUIMessageStream,
  streamText,
  generateText,
  type LanguageModelUsage,
  pipeUIMessageStreamToResponse,
} from 'ai';
import {
  authMiddleware,
  requireAuth,
  requireChatAccess,
} from '../middleware/auth';
import {
  deleteChatById,
  getMessagesByChatId,
  saveChat,
  saveMessages,
  updateChatLastContextById,
  updateChatVisiblityById,
  isDatabaseAvailable,
} from '@chat-template/db';
import {
  type ChatMessage,
  checkChatAccess,
  convertToUIMessages,
  generateUUID,
  myProvider,
  postRequestBodySchema,
  type PostRequestBody,
  StreamCache,
  type VisibilityType,
} from '@chat-template/core';
import {
  DATABRICKS_TOOL_CALL_ID,
  DATABRICKS_TOOL_DEFINITION,
} from '@chat-template/ai-sdk-providers/tools';
import { ChatSDKError } from '@chat-template/core/errors';
import {
  askGenie,
  type GenieFullResponse,
  type GenieMessageStatus,
  setGenieTokenOverride,
} from '../lib/genie-client';
import { generateVegaLiteSpec } from '../lib/auto-chart';

export const chatRouter: RouterType = Router();

const streamCache = new StreamCache();

/** In-memory map: chatId → Genie conversationId (for multi-turn). */
const genieConversations = new Map<string, string>();
// Apply auth middleware to all chat routes
chatRouter.use(authMiddleware);

/**
 * GET /api/chat/genie-health - Diagnostic endpoint.
 * Tests Genie API connectivity with both user token and SP token.
 * Visit in browser to see which auth path works.
 */
chatRouter.get('/genie-health', requireAuth, async (req: Request, res: Response) => {
  const genieSpaceId = process.env.GENIE_SPACE_ID;
  if (!genieSpaceId) {
    res.json({ ok: false, error: 'GENIE_SPACE_ID not set' });
    return;
  }

  const userToken = req.headers['x-forwarded-access-token'] as string | undefined;
  const results: Record<string, unknown> = {
    genieSpaceId,
    userTokenPresent: !!userToken,
    userTokenPrefix: userToken ? userToken.substring(0, 12) + '...' : null,
    forwardedHeaders: {} as Record<string, string>,
  };

  // Collect all x-forwarded headers
  for (const [k, v] of Object.entries(req.headers)) {
    if (k.startsWith('x-forwarded')) {
      (results.forwardedHeaders as Record<string, string>)[k] = typeof v === 'string' ? v.substring(0, 40) + (v.length > 40 ? '...' : '') : String(v);
    }
  }

  // Test 1: try user token
  if (userToken) {
    try {
      setGenieTokenOverride(userToken);
      const resp = await askGenie(genieSpaceId, 'health check', undefined);
      results.userTokenTest = { ok: true, conversationId: resp.message.conversation_id };
    } catch (err) {
      results.userTokenTest = { ok: false, error: err instanceof Error ? err.message : String(err) };
    } finally {
      setGenieTokenOverride(null);
    }
  }

  // Test 2: try SP token (no override)
  try {
    setGenieTokenOverride(null);
    const resp = await askGenie(genieSpaceId, 'health check', undefined);
    results.spTokenTest = { ok: true, conversationId: resp.message.conversation_id };
  } catch (err) {
    results.spTokenTest = { ok: false, error: err instanceof Error ? err.message : String(err) };
  }

  console.log('[Genie Health]', JSON.stringify(results, null, 2));
  res.json(results);
});

/**
 * POST /api/chat - Send a message and get streaming response
 *
 * Note: Works in ephemeral mode when database is disabled.
 * Streaming continues normally, but no chat/message persistence occurs.
 */
chatRouter.post('/', requireAuth, async (req: Request, res: Response) => {
  const dbAvailable = isDatabaseAvailable();
  if (!dbAvailable) {
    console.log('[Chat] Running in ephemeral mode - no persistence');
  }

  console.log(`CHAT POST REQUEST ${Date.now()}`);

  let requestBody: PostRequestBody;

  try {
    requestBody = postRequestBodySchema.parse(req.body);
  } catch (_) {
    console.error('Error parsing request body:', _);
    const error = new ChatSDKError('bad_request:api');
    const response = error.toResponse();
    return res.status(response.status).json(response.json);
  }

  try {
    const {
      id,
      message,
      selectedChatModel,
      selectedVisibilityType,
    }: {
      id: string;
      message: ChatMessage;
      selectedChatModel: string;
      selectedVisibilityType: VisibilityType;
    } = requestBody;

    const session = req.session;
    if (!session) {
      const error = new ChatSDKError('unauthorized:chat');
      const response = error.toResponse();
      return res.status(response.status).json(response.json);
    }

    let chat: Awaited<ReturnType<typeof checkChatAccess>>['chat'] = null as any;
    let allowed = true;
    let reason: string | undefined = 'not_found';
    try {
      ({ chat, allowed, reason } = await checkChatAccess(id, session?.user.id));
    } catch (err) {
      console.error('[Chat] checkChatAccess failed (continuing ephemeral):', err);
    }

    if (reason !== 'not_found' && !allowed) {
      const error = new ChatSDKError('forbidden:chat');
      const response = error.toResponse();
      return res.status(response.status).json(response.json);
    }

    if (!chat) {
      if (isDatabaseAvailable()) {
        try {
          // Title generation calls a serving endpoint; never let it block the chat.
          const fallbackTitle =
            (message.parts?.find((p: { type: string }) => p.type === 'text') as { text?: string } | undefined)
              ?.text?.slice(0, 60) || 'New chat';
          const title = await Promise.race([
            generateTitleFromUserMessage({ message }).catch((e) => {
              console.warn('[Chat] Title generation failed:', e);
              return fallbackTitle;
            }),
            new Promise<string>((resolve) => setTimeout(() => resolve(fallbackTitle), 8000)),
          ]);
          await saveChat({
            id,
            userId: session.user.id,
            title,
            visibility: selectedVisibilityType,
          });
          console.log(`[Chat] Saved chat ${id} with title "${title}"`);
        } catch (err) {
          console.error('[Chat] saveChat failed (continuing):', err);
        }
      }
    } else {
      if (chat.userId !== session.user.id) {
        const error = new ChatSDKError('forbidden:chat');
        const response = error.toResponse();
        return res.status(response.status).json(response.json);
      }
    }

    let messagesFromDb: Awaited<ReturnType<typeof getMessagesByChatId>> = [];
    try {
      messagesFromDb = await getMessagesByChatId({ id });
    } catch (err) {
      console.error('[Chat] getMessagesByChatId failed (continuing):', err);
    }
    const uiMessages = [...convertToUIMessages(messagesFromDb), message];

    try {
      await saveMessages({
        messages: [
          {
            chatId: id,
            id: message.id,
            role: 'user',
            parts: message.parts,
            attachments: [],
            createdAt: new Date(),
          },
        ],
      });
    } catch (err) {
      console.error('[Chat] saveMessages (user) failed (continuing):', err);
    }

    // Clear any previous active stream for this chat
    streamCache.clearActiveStream(id);

    let finalUsage: LanguageModelUsage | undefined;
    const streamId = generateUUID();

    // ── Genie-gated path ──────────────────────────────────────────────
    const genieSpaceId = process.env.GENIE_SPACE_ID;

    if (genieSpaceId) {
      // Route through Databricks Genie API
      console.log(`[Chat] Routing to Genie space ${genieSpaceId}`);

      // ── Token resolution ─────────────────────────────────────────────
      // Priority: user's forwarded token (has genie scope + workspace perms)
      // Fallback: GENIE_PAT env var, then SP token (needs workspace ACL).
      const userAccessToken =
        req.headers['x-forwarded-access-token'] as string | undefined;
      console.log(
        `[Chat] Token diag: x-forwarded-access-token ${userAccessToken ? 'PRESENT (' + userAccessToken.substring(0, 8) + '...)' : 'ABSENT'}`,
      );
      // Log all x-forwarded headers for diagnostics
      for (const [k, v] of Object.entries(req.headers)) {
        if (k.startsWith('x-forwarded')) {
          console.log(`[Chat] Header ${k}: ${typeof v === 'string' ? v.substring(0, 30) : v}`);
        }
      }
      if (userAccessToken) {
        console.log('[Chat] Using user forwarded access token for Genie');
        setGenieTokenOverride(userAccessToken);
      } else {
        console.log('[Chat] No user token — using SP token for Genie');
        setGenieTokenOverride(null);
      }

      // Extract plain-text question from the latest user message
      const userQuestion =
        message.parts
          ?.filter((p: { type: string }) => p.type === 'text')
          .map((p: { type: string; text?: string }) => p.text ?? '')
          .join(' ')
          .trim() || 'Hello';

      // Reuse Genie conversation for multi-turn
      const existingConvId = genieConversations.get(id);

      const stream = createUIMessageStream({
        generateId: generateUUID,
        execute: async ({ writer }) => {
          // AI SDK v5 UI message stream protocol (same shape the repo's
          // Databricks providers emit): parts are bracketed by *-start/*-end
          // and deltas carry { id, delta }. v4-style { textDelta } chunks fail
          // client schema validation -> onError -> resume loop -> blank reply.
          const reasoningId = `genie-reasoning-${generateUUID()}`;
          let reasoningOpen = false;
          const closeReasoning = () => {
            if (reasoningOpen) {
              writer.write({ type: 'reasoning-end', id: reasoningId });
              reasoningOpen = false;
            }
          };
          const writeText = (text: string) => {
            closeReasoning();
            const textId = `genie-text-${generateUUID()}`;
            writer.write({ type: 'text-start', id: textId });
            writer.write({ type: 'text-delta', id: textId, delta: text });
            writer.write({ type: 'text-end', id: textId });
          };
          try {
            const genieResponse = await askGenie(
              genieSpaceId,
              userQuestion,
              existingConvId,
              (status: GenieMessageStatus, _attempt: number) => {
                const statusLabels: Record<string, string> = {
                  QUEUED: 'Queued\u2026',
                  FILTERING_CONTEXT: 'Understanding context\u2026',
                  ASKING_AI: 'Generating response\u2026',
                  EXECUTING_QUERY: 'Running SQL query\u2026',
                };
                const label = statusLabels[status];
                if (label) {
                  if (!reasoningOpen) {
                    writer.write({ type: 'reasoning-start', id: reasoningId });
                    reasoningOpen = true;
                  }
                  writer.write({ type: 'reasoning-delta', id: reasoningId, delta: label + '\n' });
                }
              },
            );

            // Remember conversation for multi-turn
            if (genieResponse.message.conversation_id) {
              genieConversations.set(id, genieResponse.message.conversation_id);
            }

            if (genieResponse.error) {
              writeText(`**Error from Genie:** ${genieResponse.error}`);
              return;
            }

            // Build a rich markdown response
            const parts: string[] = [];

            // Narrative text
            if (genieResponse.narrativeText) {
              parts.push(genieResponse.narrativeText);
            }

            // SQL query
            if (genieResponse.sql) {
              parts.push(
                '\n\n**SQL Query:**\n```sql\n' +
                  genieResponse.sql +
                  '\n```',
              );
            }

            // Query result as a markdown table
            if (
              genieResponse.queryResult?.columns &&
              genieResponse.queryResult?.data_array
            ) {
              const cols = genieResponse.queryResult.columns;
              const rows = genieResponse.queryResult.data_array;

              const header = '| ' + cols.map((c) => c.name).join(' | ') + ' |';
              const sep =
                '| ' + cols.map(() => '---').join(' | ') + ' |';
              const dataRows = rows
                .slice(0, 50) // cap at 50 rows for readability
                .map((r) => '| ' + r.join(' | ') + ' |');

              parts.push(
                '\n\n**Results' +
                  (genieResponse.queryResult.row_count
                    ? ` (${genieResponse.queryResult.row_count} rows` +
                      (rows.length < (genieResponse.queryResult.row_count ?? 0)
                        ? ', showing first ' + rows.length
                        : '') +
                      ')'  
                    : '') +
                  ':**\n' +
                  [header, sep, ...dataRows].join('\n'),
              );

            }

            // Auto-generate chart visualization from query results
            if (
              genieResponse.queryResult?.columns &&
              genieResponse.queryResult?.data_array &&
              genieResponse.queryResult.data_array.length > 0
            ) {
              try {
                const chartSpec = generateVegaLiteSpec(
                  genieResponse.queryResult.columns,
                  genieResponse.queryResult.data_array,
                );
                if (chartSpec) {
                  parts.push(
                    '\n\n```vega-lite\n' + chartSpec + '\n```',
                  );
                }
              } catch (chartErr) {
                console.warn('[Genie] Chart generation failed:', chartErr);
              }
            }

            const fullText = parts.join('') || 'No results returned from Genie.';

            // Emit full text as a single delta
            console.log(`[Genie] Writing response text (${fullText.length} chars)`);
            writeText(fullText);
          } catch (err) {
            console.error('[Genie] Error:', err);
            const errorMsg =
              err instanceof Error ? err.message : JSON.stringify(err);
            // Write error as visible text (not data-error which may be swallowed)
            writeText(`**Genie API Error**\n\n${errorMsg}\n\nPlease try opening the app in an incognito window to refresh your auth token.`);
          } finally {
            closeReasoning();
            setGenieTokenOverride(null);
          }
        },
        onFinish: async ({ responseMessage }) => {
          // Top-level try/catch: the AI SDK propagates onFinish errors as
          // unhandled rejections through the stream pipeline, crashing Node.
          // Nothing in onFinish is worth crashing for.
          try {
            // Clear per-request token override (belt-and-suspenders)
            setGenieTokenOverride(null);
            if (isDatabaseAvailable()) {
              console.log('[Genie] Saving response message');
              try {
                await saveMessages({
                  messages: [
                    {
                      id: responseMessage.id,
                      role: responseMessage.role,
                      parts: responseMessage.parts,
                      createdAt: new Date(),
                      attachments: [],
                      chatId: id,
                    },
                  ],
                });
              } catch (dbErr) {
                console.error('[Genie] Failed to save response message (id=%s, parts=%d):', responseMessage?.id, responseMessage?.parts?.length ?? -1, dbErr);
              if (dbErr instanceof Error && (dbErr as any).cause) {
                console.error('[Genie] DB root cause:', (dbErr as any).cause);
              }
              }
            } else {
              console.log('[Genie] Database not available, skipping response persistence');
            }
          } catch (outerErr) {
            console.error('[Genie] onFinish unexpected error (swallowed):', outerErr);
          } finally {
            streamCache.clearActiveStream(id);
          }
        },
      });

      pipeUIMessageStreamToResponse({
        stream,
        response: res,
        consumeSseStream({ stream }) {
          streamCache.storeStream({ streamId, chatId: id, stream });
        },
      });
    } else {
      // ── Original serving-endpoint path ────────────────────────────────
      const model = await myProvider.languageModel(selectedChatModel);
      const result = streamText({
        model,
        messages: convertToModelMessages(uiMessages),
        onFinish: ({ usage }) => {
          finalUsage = usage;
        },
        tools: {
          [DATABRICKS_TOOL_CALL_ID]: DATABRICKS_TOOL_DEFINITION,
        },
      });

      const stream = createUIMessageStream({
        execute: async ({ writer }) => {
          writer.merge(
            result.toUIMessageStream({
              originalMessages: uiMessages,
              generateMessageId: generateUUID,
              sendReasoning: true,
              sendSources: true,
              onError: (error) => {
                console.error('Stream error:', error);

                const errorMessage =
                  error instanceof Error
                    ? error.message
                    : JSON.stringify(error);

                writer.write({ type: 'data-error', data: errorMessage });

                return errorMessage;
              },
            }),
          );
        },
        onFinish: async ({ responseMessage }) => {
          // Top-level try/catch: the AI SDK propagates onFinish errors as
          // unhandled rejections through the stream pipeline, crashing Node.
          try {
            console.log(
              'Finished message stream! Saving message...',
              JSON.stringify(responseMessage, null, 2),
            );
            if (isDatabaseAvailable()) {
              try {
                await saveMessages({
                  messages: [
                    {
                      id: responseMessage.id,
                      role: responseMessage.role,
                      parts: responseMessage.parts,
                      createdAt: new Date(),
                      attachments: [],
                      chatId: id,
                    },
                  ],
                });
              } catch (dbErr) {
                console.error('Failed to save response message:', dbErr);
              }

              if (finalUsage) {
                try {
                  await updateChatLastContextById({
                    chatId: id,
                    context: finalUsage,
                  });
                } catch (err) {
                  console.warn(
                    'Unable to persist last usage for chat',
                    id,
                    err,
                  );
                }
              }
            } else {
              console.log('[Chat] Database not available, skipping response persistence');
            }
          } catch (outerErr) {
            console.error('[Chat] onFinish unexpected error (swallowed):', outerErr);
          } finally {
            streamCache.clearActiveStream(id);
          }
        },
      });

      pipeUIMessageStreamToResponse({
        stream,
        response: res,
        consumeSseStream({ stream }) {
          streamCache.storeStream({
            streamId,
            chatId: id,
            stream,
          });
        },
      });
    }
  } catch (error) {
    if (error instanceof ChatSDKError) {
      const response = error.toResponse();
      return res.status(response.status).json(response.json);
    }

    console.error('Unhandled error in chat API:', error);

    const chatError = new ChatSDKError('offline:chat');
    const response = chatError.toResponse();
    return res.status(response.status).json(response.json);
  }
});

/**
 * DELETE /api/chat?id=:id - Delete a chat
 */
chatRouter.delete(
  '/:id',
  [requireAuth, requireChatAccess],
  async (req: Request, res: Response) => {
    const { id } = req.params;

    const deletedChat = await deleteChatById({ id });
    return res.status(200).json(deletedChat);
  },
);

/**
 * GET /api/chat/:id
 */

chatRouter.get(
  '/:id',
  [requireAuth, requireChatAccess],
  async (req: Request, res: Response) => {
    const { id } = req.params;

    const { chat } = await checkChatAccess(id, req.session?.user.id);

    return res.status(200).json(chat);
  },
);

/**
 * GET /api/chat/:id/stream - Resume a stream
 */
chatRouter.get(
  '/:id/stream',
  [requireAuth],
  async (req: Request, res: Response) => {
    const { id: chatId } = req.params;
    const cursor = req.headers['x-resume-stream-cursor'] as string;

    console.log(`[Stream Resume] Cursor: ${cursor}`);

    console.log(`[Stream Resume] GET request for chat ${chatId}`);

    // Check if there's an active stream for this chat first
    const streamId = streamCache.getActiveStreamId(chatId);

    if (!streamId) {
      console.log(`[Stream Resume] No active stream for chat ${chatId}`);
      const streamError = new ChatSDKError('empty:stream');
      const response = streamError.toResponse();
      return res.status(response.status).json(response.json);
    }

    const { allowed, reason } = await checkChatAccess(
      chatId,
      req.session?.user.id,
    );

    // If chat doesn't exist in DB, it's a temporary chat from the homepage - allow it
    if (reason === 'not_found') {
      console.log(
        `[Stream Resume] Resuming stream for temporary chat ${chatId} (not yet in DB)`,
      );
    } else if (!allowed) {
      console.log(
        `[Stream Resume] User ${req.session?.user.id} does not have access to chat ${chatId} (reason: ${reason})`,
      );
      const streamError = new ChatSDKError('forbidden:chat', reason);
      const response = streamError.toResponse();
      return res.status(response.status).json(response.json);
    }

    // Get all cached chunks for this stream
    const stream = streamCache.getStream(streamId, {
      cursor: cursor ? Number.parseInt(cursor) : undefined,
    });

    if (!stream) {
      console.log(`[Stream Resume] No stream found for ${streamId}`);
      const streamError = new ChatSDKError('empty:stream');
      const response = streamError.toResponse();
      return res.status(response.status).json(response.json);
    }

    console.log(`[Stream Resume] Resuming stream ${streamId}`);

    // Set headers for SSE
    res.setHeader('Content-Type', 'text/event-stream');
    res.setHeader('Cache-Control', 'no-cache');
    res.setHeader('Connection', 'keep-alive');

    // Pipe the cached stream directly to the response
    stream.pipe(res);

    // Handle stream errors
    stream.on('error', (error) => {
      console.error('[Stream Resume] Stream error:', error);
      if (!res.headersSent) {
        res.status(500).end();
      }
    });
  },
);

/**
 * POST /api/chat/title - Generate title from message
 */
chatRouter.post('/title', requireAuth, async (req: Request, res: Response) => {
  try {
    const { message } = req.body;
    const title = await generateTitleFromUserMessage({ message });
    res.json({ title });
  } catch (error) {
    console.error('Error generating title:', error);
    res.status(500).json({ error: 'Failed to generate title' });
  }
});

/**
 * PATCH /api/chat/:id/visibility - Update chat visibility
 */
chatRouter.patch(
  '/:id/visibility',
  [requireAuth, requireChatAccess],
  async (req: Request, res: Response) => {
    try {
      const { id } = req.params;
      const { visibility } = req.body;

      if (!visibility || !['public', 'private'].includes(visibility)) {
        return res.status(400).json({ error: 'Invalid visibility type' });
      }

      await updateChatVisiblityById({ chatId: id, visibility });
      res.json({ success: true });
    } catch (error) {
      console.error('Error updating visibility:', error);
      res.status(500).json({ error: 'Failed to update visibility' });
    }
  },
);

// Helper function to generate title from user message
async function generateTitleFromUserMessage({
  message,
}: {
  message: ChatMessage;
}) {
  const model = await myProvider.languageModel('title-model');
  const { text: title } = await generateText({
    model,
    system: `\n
    - you will generate a short title based on the first message a user begins a conversation with
    - ensure it is not more than 80 characters long
    - the title should be a summary of the user's message
    - do not use quotes or colons. do not include other expository content ("I'll help...")`,
    prompt: JSON.stringify(message),
  });

  return title;
}
