/** API client — typed fetch with the app's error envelope. */

export class ApiError extends Error {
  code: string;
  requestId: string;
  retryable: boolean;
  status: number;
  constructor(status: number, code: string, message: string, requestId = "", retryable = false) {
    super(message);
    this.status = status;
    this.code = code;
    this.requestId = requestId;
    this.retryable = retryable;
  }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`/api${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!resp.ok) {
    let code = "HTTP_ERROR";
    let message = `HTTP ${resp.status}`;
    let retryable = resp.status >= 500;
    let requestId = resp.headers.get("x-request-id") ?? "";
    try {
      const body = await resp.json();
      if (body?.error) {
        code = body.error.code ?? code;
        message = body.error.message ?? message;
        retryable = body.error.retryable ?? retryable;
        requestId = body.error.request_id || requestId;
      }
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(resp.status, code, message, requestId, retryable);
  }
  return resp.json() as Promise<T>;
}

export interface Me {
  user: string;
  auth_mode: "obo" | "service_principal" | "mock";
  obo_token_present: boolean;
  app_mode: string;
  genie_space_id: string | null;
  catalog: string;
  schema: string;
  features: { streaming: boolean; persistence: boolean };
}

export const getMe = () => api<Me>("/me");
export const getHealth = () =>
  api<{ status: string; app_mode: string; warehouse?: string | null; genie?: string | null }>(
    "/health/deep",
  );
