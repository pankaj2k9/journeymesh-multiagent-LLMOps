import { createContext, useCallback, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';

import {
  applyTheme,
  initialTheme,
  resolveTheme,
  storeTheme,
  type ResolvedTheme,
  type Theme,
} from './theme';

export interface ThemeContextValue {
  /** What the user chose: light, dark, or follow the system. */
  theme: Theme;
  /** What is actually on screen right now. */
  resolvedTheme: ResolvedTheme;
  setTheme: (theme: Theme) => void;
  /** Step light -> dark -> system, which is what the header button does. */
  cycleTheme: () => void;
}

export const ThemeContext = createContext<ThemeContextValue | null>(null);

/** The order the header button steps through. Light is where a new visitor starts. */
const ORDER: Theme[] = ['light', 'dark', 'system'];

interface ThemeProviderProps {
  children: ReactNode;
  /** Test seam: start from an explicit preference instead of storage. */
  initial?: Theme;
}

export function ThemeProvider({ children, initial }: ThemeProviderProps) {
  const [theme, setThemeState] = useState<Theme>(() => initial ?? initialTheme());
  const [resolvedTheme, setResolvedTheme] = useState<ResolvedTheme>(() =>
    resolveTheme(initial ?? initialTheme()),
  );

  // Apply the preference whenever it changes. The blocking script in
  // index.html has already done this for the first paint; this keeps the
  // document in step from then on.
  useEffect(() => {
    const resolved = resolveTheme(theme);
    setResolvedTheme(resolved);
    applyTheme(resolved);
  }, [theme]);

  // While following the system, react to the OS switching underneath us.
  useEffect(() => {
    if (theme !== 'system') return;
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return;

    const query = window.matchMedia('(prefers-color-scheme: dark)');
    const onChange = (event: MediaQueryListEvent) => {
      const resolved: ResolvedTheme = event.matches ? 'dark' : 'light';
      setResolvedTheme(resolved);
      applyTheme(resolved);
    };

    // Safari below 14 only has the deprecated listener API.
    if (typeof query.addEventListener === 'function') {
      query.addEventListener('change', onChange);
      return () => query.removeEventListener('change', onChange);
    }
    query.addListener(onChange);
    return () => query.removeListener(onChange);
  }, [theme]);

  const setTheme = useCallback((next: Theme) => {
    setThemeState(next);
    storeTheme(next);
  }, []);

  const cycleTheme = useCallback(() => {
    setThemeState((current) => {
      const next = ORDER[(ORDER.indexOf(current) + 1) % ORDER.length];
      storeTheme(next);
      return next;
    });
  }, []);

  const value = useMemo<ThemeContextValue>(
    () => ({ theme, resolvedTheme, setTheme, cycleTheme }),
    [theme, resolvedTheme, setTheme, cycleTheme],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}
