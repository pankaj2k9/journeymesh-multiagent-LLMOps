/**
 * Where the access and refresh tokens live.
 *
 * `localStorage`, deliberately and with the trade-off stated: a token in
 * storage is readable by any script that gets onto the page, which an
 * httpOnly cookie would not be. The alternative here is worse, though - this
 * is a single-page app served from the same origin as the API and a cookie
 * would need CSRF protection on every mutating request, which is a larger
 * surface to get wrong. The mitigations that matter are elsewhere: a short
 * access-token lifetime, a `token_version` the server can bump to strand every
 * token at once, and a strict CSP.
 *
 * Every read and write is wrapped, because storage throws in private mode and
 * a sign-in must not take the page down with it.
 */

const ACCESS_KEY = 'journeymesh.auth.access';
const REFRESH_KEY = 'journeymesh.auth.refresh';

type Listener = () => void;

const listeners = new Set<Listener>();

function read(key: string): string | null {
  if (typeof window === 'undefined') return null;
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function write(key: string, value: string | null): void {
  if (typeof window === 'undefined') return;
  try {
    if (value === null) window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, value);
  } catch {
    /* storage unavailable - the session simply lasts this page load */
  }
}

export function accessToken(): string | null {
  return read(ACCESS_KEY);
}

export function refreshToken(): string | null {
  return read(REFRESH_KEY);
}

export function storeTokens(access: string, refresh: string): void {
  write(ACCESS_KEY, access);
  write(REFRESH_KEY, refresh);
  notify();
}

export function clearTokens(): void {
  write(ACCESS_KEY, null);
  write(REFRESH_KEY, null);
  notify();
}

export function isSignedIn(): boolean {
  return accessToken() !== null;
}

/** Subscribe to sign-in and sign-out, including from another browser tab. */
export function subscribe(listener: Listener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function notify(): void {
  listeners.forEach((listener) => listener());
}

if (typeof window !== 'undefined') {
  // Signing out in one tab signs out the others; otherwise a second tab keeps
  // showing a dashboard whose requests have all started returning 401.
  window.addEventListener('storage', (event) => {
    if (event.key === ACCESS_KEY || event.key === REFRESH_KEY) notify();
  });
}
