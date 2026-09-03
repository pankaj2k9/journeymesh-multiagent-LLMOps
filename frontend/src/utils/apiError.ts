import { ApiError } from '../api/client';

type Translate = (key: string, options?: Record<string, unknown>) => string;

/**
 * One place that turns a failure into something a traveller can read.
 *
 * Every long-running action - planning, approving, revising - reports through
 * this, so a timeout reads the same wherever it happens and no call site has
 * to remember the full list of cases. Anything unrecognised falls back to the
 * generic message rather than leaking an internal string.
 */
export function describeApiError(error: unknown, t: Translate): string {
  if (error instanceof ApiError) {
    if (error.isTimeout) return t('errors.timeout');
    if (error.code === 'network_error') return t('errors.network');
    if (error.isRateLimited) return t('errors.rateLimited');
    if (error.isRevisionLimit) return t('errors.revisionLimit');
    if (error.isNotFound) return t('errors.notFound');
    if (error.status >= 500) return t('errors.server');
    if (error.message && error.message !== 'network_unreachable') return error.message;
  }
  return t('errors.title');
}

/** True when retrying the same request is a reasonable next step. */
export function isRetryable(error: unknown): boolean {
  if (!(error instanceof ApiError)) return true;
  if (error.isRevisionLimit) return false;
  return error.isNetwork || error.isRateLimited || error.status >= 500 || error.status === 0;
}
