import { SESSION_STORAGE_KEY } from './constants';

function randomId(): string {
  const globalCrypto = typeof crypto !== 'undefined' ? crypto : undefined;
  if (globalCrypto && 'randomUUID' in globalCrypto) {
    return globalCrypto.randomUUID();
  }
  return `jm-${Math.random().toString(36).slice(2)}${Date.now().toString(36)}`;
}

/**
 * A browser-local id used to group a visitor's journeys. It is not an account
 * and carries no personal data.
 */
export function getSessionId(): string {
  if (typeof window === 'undefined') return 'server';
  try {
    const existing = window.localStorage.getItem(SESSION_STORAGE_KEY);
    if (existing) return existing;
    const created = randomId();
    window.localStorage.setItem(SESSION_STORAGE_KEY, created);
    return created;
  } catch {
    return 'anonymous';
  }
}

export function resetSessionId(): string {
  if (typeof window === 'undefined') return 'server';
  try {
    window.localStorage.removeItem(SESSION_STORAGE_KEY);
  } catch {
    /* storage unavailable - a fresh id is generated below anyway */
  }
  return getSessionId();
}
