import { expect, test } from '../fixtures';

/**
 * Pro-mode SQL tabs. Default Playwright env is simple mode with no warehouse,
 * so these assert the documented degrade path: 503 rather than 500 / empty 200.
 * A live warehouse is out of scope for CI; notebook 06b covers that path.
 */
test.describe('pro-mode SQL routes (unconfigured)', () => {
  test('GET /api/graph returns 503 when GraphRAG SQL is not configured', async ({
    adaContext,
  }) => {
    const response = await adaContext.request.get('/api/graph');
    expect(response.status()).toBe(503);
    const body = await response.json();
    expect(body.error).toMatch(/not configured/i);
  });

  test('GET /api/series/meta returns 503 when ticker SQL is not configured', async ({
    adaContext,
  }) => {
    const response = await adaContext.request.get('/api/series/meta');
    expect(response.status()).toBe(503);
    const body = await response.json();
    expect(body.error).toMatch(/not configured/i);
  });

  test('GET /api/series returns 503 when ticker SQL is not configured', async ({
    adaContext,
  }) => {
    const response = await adaContext.request.get(
      '/api/series?metric=price_close',
    );
    expect(response.status()).toBe(503);
  });
});
