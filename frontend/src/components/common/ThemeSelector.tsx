import { useTranslation } from 'react-i18next';

import { THEMES, useTheme } from '../../theme';
import type { Theme } from '../../theme';

const LABEL_KEY: Record<Theme, string> = {
  light: 'theme.light',
  dark: 'theme.dark',
  system: 'theme.system',
};

/**
 * An explicit three-way choice, for the settings page.
 *
 * The header button cycles - fast, one target. Here the modes are laid out so
 * one can be picked directly, which is easier with a screen reader or a switch
 * device.
 */
export function ThemeSelector({ className = '' }: { className?: string }) {
  const { t } = useTranslation();
  const { theme, setTheme } = useTheme();

  return (
    <div
      role="radiogroup"
      aria-label={t('theme.label')}
      className={`inline-flex rounded-xl bg-elevated p-1 ${className}`.trim()}
    >
      {THEMES.map((option) => {
        const selected = theme === option;
        return (
          <button
            key={option}
            type="button"
            role="radio"
            aria-checked={selected}
            onClick={() => setTheme(option)}
            className={`rounded-lg px-3 py-1.5 text-sm font-medium transition ${
              selected
                ? 'bg-surface text-accent shadow-sm'
                : 'text-muted hover:text-ink'
            }`}
          >
            {t(LABEL_KEY[option])}
          </button>
        );
      })}
    </div>
  );
}
