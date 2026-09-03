import { getSessionId } from '../utils/session';

/**
 * The API base URL. In development this is empty so requests go through the
 * Vite proxy; in production it points at the deployed FastAPI service.
 * Only VITE_* variables reach the browser, and none of them is a secret.
 */
export const API_BASE_URL: string = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '');

export const API_PREFIX = '/api/v1';

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details?: unknown;

  constructor(message: string, status: number, code = 'error', details?: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.details = details;
  }

  get isRateLimited(): boolean {
    return this.status === 429;
  }

  get isNotFound(): boolean {
    return this.status === 404;
  }

  get isRevisionLimit(): boolean {
    return this.code === 'revision_limit_reached';
  }

  get isTimeout(): boolean {
    return this.code === 'timeout';
  }

  get isNetwork(): boolean {
    return this.code === 'network_error' || this.code === 'timeout';
  }
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'DELETE';
  body?: unknown;
  signal?: AbortSignal;
  /** Milliseconds before the request is abandoned. */
  timeoutMs?: number;
}

/**
 * A planning run does real work - several agents, several providers - so the
 * ceiling is generous. It exists so that a request which will never answer
 * fails as a timeout the interface can report and retry, rather than leaving a
 * spinner turning for ever.
 */
export const DEFAULT_TIMEOUT_MS = 120_000;

export function apiUrl(path: string): string {
  return `${API_BASE_URL}${API_PREFIX}${path}`;
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, signal, timeoutMs = DEFAULT_TIMEOUT_MS } = options;

  const controller = new AbortController();
  const timedOut = { value: false };
  const timer = setTimeout(() => {
    timedOut.value = true;
    controller.abort();
  }, timeoutMs);

  // A caller-supplied signal still wins; the timeout is an additional way out.
  const onAbort = () => controller.abort();
  signal?.addEventListener('abort', onAbort);

  let response: Response;
  try {
    response = await fetch(apiUrl(path), {
      method,
      signal: controller.signal,
      headers: {
        'Content-Type': 'application/json',
        'X-JourneyMesh-Session': getSessionId(),
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch (cause) {
    if (timedOut.value) {
      throw new ApiError('request_timed_out', 0, 'timeout', cause);
    }
    throw new ApiError('network_unreachable', 0, 'network_error', cause);
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener('abort', onAbort);
  }

  const text = await response.text();
  const payload = text ? safeParse(text) : null;

  if (!response.ok) {
    const record = (payload ?? {}) as Record<string, unknown>;
    throw new ApiError(
      typeof record.message === 'string' ? record.message : response.statusText,
      response.status,
      typeof record.error === 'string' ? record.error : 'error',
      record.details,
    );
  }

  return payload as T;
}

function safeParse(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return { message: text };
  }
}
