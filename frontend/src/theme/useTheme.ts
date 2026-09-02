import { useContext } from 'react';

import { ThemeContext, type ThemeContextValue } from './ThemeProvider';

/**
 * Read and change the theme.
 *
 * Throws outside a ThemeProvider rather than silently defaulting, so a missing
 * provider is a build-time-obvious mistake instead of a subtle one.
 */
export function useTheme(): ThemeContextValue {
  const context = useContext(ThemeContext);
  if (context === null) {
    throw new Error('useTheme must be used inside a ThemeProvider');
  }
  return context;
}
