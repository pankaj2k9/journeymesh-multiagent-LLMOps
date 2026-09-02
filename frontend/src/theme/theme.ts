/**
 * Theme primitives.
 *
 * JourneyMesh has two themes, light and dark. The rules:
 *   - first visit  -> light
 *   - user toggles -> remember that choice in localStorage, forever
 *
 * Theme and language are stored under separate keys and never touch each
 * other's state.
 */

export type Theme = 'light' | 'dark';

export const THEMES: Theme[] = ['light', 'dark'];

/** Where a new visitor starts. */
export const DEFAULT_THEME: Theme = 'light';

/** Independent of `journeymesh_language`, by design. */
export const THEME_STORAGE_KEY = 'journeymesh_theme';

/** Key used before the storage keys were standardised. Read once, then migrated. */
const LEGACY_THEME_KEY = 'journeymesh.theme';

export const DARK_CLASS = 'dark';

/** Browser chrome colour, kept in step with the active theme. */
export const THEME_COLORS: Record<Theme, string> = {
  light: '#17365d',
  dark: '#0b1220',
};

export function isTheme(value: unknown): value is Theme {
  return value === 'light' || value === 'dark';
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

/** The stored preference, or light on a first visit. */
export function initialTheme(): Theme {
  return readStoredTheme() ?? DEFAULT_THEME;
}

/** The opposite of the given theme. */
export function oppositeTheme(theme: Theme): Theme {
  return theme === 'dark' ? 'light' : 'dark';
}

/**
 * Put the theme on the document.
 *
 * `color-scheme` matters as much as the class: it is what makes native
 * controls - scrollbars, date pickers, form widgets - follow the theme.
 */
export function applyTheme(theme: Theme): void {
  if (typeof document === 'undefined') return;

  const root = document.documentElement;
  root.classList.toggle(DARK_CLASS, theme === 'dark');
  root.style.colorScheme = theme;
  root.dataset.theme = theme;

  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute('content', THEME_COLORS[theme]);
}

/**
 * The same logic as above, as a string, for the blocking script in index.html.
 *
 * It runs before React so the first paint is already correct - no flash of the
 * wrong theme for someone who chose dark. A test asserts this stays identical
 * to what index.html ships, and the CSP allows it by hash.
 */
export const THEME_INIT_SCRIPT = `(function(){try{var k='${THEME_STORAGE_KEY}';var s=window.localStorage.getItem(k);var d=s==='dark';var e=document.documentElement;e.classList.toggle('${DARK_CLASS}',d);e.style.colorScheme=d?'dark':'light';e.dataset.theme=d?'dark':'light';var m=document.querySelector('meta[name="theme-color"]');if(m)m.setAttribute('content',d?'${THEME_COLORS.dark}':'${THEME_COLORS.light}');}catch(e){}})();`;
