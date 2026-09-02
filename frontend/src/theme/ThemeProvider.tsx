import { createContext, useCallback, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';

import { applyTheme, initialTheme, oppositeTheme, storeTheme, type Theme } from './theme';

export interface ThemeContextValue {
  /** The active theme: light or dark. */
  theme: Theme;
  setTheme: (theme: Theme) => void;
  /** Flip between light and dark - what the header button does. */
  toggleTheme: () => void;
}

export const ThemeContext = createContext<ThemeContextValue | null>(null);

interface ThemeProviderProps {
  children: ReactNode;
  /** Test seam: start from an explicit theme instead of storage. */
  initial?: Theme;
}

export function ThemeProvider({ children, initial }: ThemeProviderProps) {
  const [theme, setThemeState] = useState<Theme>(() => initial ?? initialTheme());

  // The blocking script in index.html has already done this for the first
  // paint; this keeps the document in step from then on.
  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  const setTheme = useCallback((next: Theme) => {
    setThemeState(next);
    storeTheme(next);
  }, []);

  const toggleTheme = useCallback(() => {
    setThemeState((current) => {
      const next = oppositeTheme(current);
      storeTheme(next);
      return next;
    });
  }, []);

  const value = useMemo<ThemeContextValue>(
    () => ({ theme, setTheme, toggleTheme }),
    [theme, setTheme, toggleTheme],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}
