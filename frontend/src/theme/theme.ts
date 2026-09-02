/**
 * Theme primitives.
 *
 * The rules JourneyMesh follows:
 *   - first visit  -> follow the operating system
 *   - user chooses -> remember that choice in localStorage, forever
 *   - "system"     -> keep following the OS, including live changes
 *
 * Theme and language are stored under separate keys and never touch each
 * other's state.
 */

export type Theme = 'light' | 'dark' | 'system';
export type ResolvedTheme = 'light' | 'dark';

export const THEMES: Theme[] = ['light', 'dark', 'system'];

/** Independent of `journeymesh_language`, by design. */
export const THEME_STORAGE_KEY = 'journeymesh_theme';

/** Key used before the storage keys were standardised. Read once, then migrated. */
const LEGACY_THEME_KEY = 'journeymesh.theme';

export const DARK_CLASS = 'dark';

/** Browser chrome colour, kept in step with the active theme. */
export const THEME_COLORS: Record<ResolvedTheme, string> = {
  light: '#17365d',
  dark: '#0b1220',
};

export function isTheme(value: unknown): value is Theme {
  return typeof value === 'string' && (THEMES as string[]).includes(value);
}

/** What the operating system is currently asking for. */
export function systemPrefersDark(): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
    return false;
  }
  try {
    return window.matchMedia('(prefers-color-scheme: dark)').matches;
  } catch {
    return false;
  }
}

export function readStoredTheme(): Theme | null {
  if (typeof window === 'undefined') return null;
  try {
    const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
    if (isTheme(stored)) return stored;

    const legacy = window.localStorage.getItem(LEGACY_THEME_KEY);
    if (isTheme(legacy)) {
      window.localStorage.setItem(THEME_STORAGE_KEY, legacy);
      window.localStorage.removeItem(LEGACY_THEME_KEY);
      return legacy;
    }
  } catch {
    /* storage unavailable (private mode, blocked cookies) - fall back below */
  }
  return null;
}

export function storeTheme(theme: Theme): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, theme);
  } catch {
    /* the choice simply is not remembered */
  }
}

/** The preference, defaulting to following the system. */
export function initialTheme(): Theme {
  return readStoredTheme() ?? 'system';
}

/** Turn a preference into the theme actually being displayed. */
export function resolveTheme(theme: Theme): ResolvedTheme {
  if (theme === 'system') return systemPrefersDark() ? 'dark' : 'light';
  return theme;
}

/**
 * Put the resolved theme on the document.
 *
 * `color-scheme` matters as much as the class: it is what makes native
 * controls - scrollbars, date pickers, form widgets - follow the theme.
 */
export function applyTheme(resolved: ResolvedTheme): void {
  if (typeof document === 'undefined') return;

  const root = document.documentElement;
  root.classList.toggle(DARK_CLASS, resolved === 'dark');
  root.style.colorScheme = resolved;
  root.dataset.theme = resolved;

  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute('content', THEME_COLORS[resolved]);
}

/**
 * The same logic as above, as a string, for the blocking script in index.html.
 *
 * It runs before React so the first paint is already correct - no flash of the
 * wrong theme. A test asserts this stays identical to what index.html ships.
 */
export const THEME_INIT_SCRIPT = `(function(){try{var k='${THEME_STORAGE_KEY}';var s=window.localStorage.getItem(k);var t=(s==='light'||s==='dark'||s==='system')?s:'system';var d=t==='dark'||(t==='system'&&window.matchMedia('(prefers-color-scheme: dark)').matches);var e=document.documentElement;e.classList.toggle('${DARK_CLASS}',d);e.style.colorScheme=d?'dark':'light';e.dataset.theme=d?'dark':'light';var m=document.querySelector('meta[name="theme-color"]');if(m)m.setAttribute('content',d?'${THEME_COLORS.dark}':'${THEME_COLORS.light}');}catch(e){}})();`;
