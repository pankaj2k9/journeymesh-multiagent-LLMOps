import { useTranslation } from 'react-i18next';

import { useTheme } from '../../theme';

/** Sun and moon, drawn inline so the toggle needs no icon dependency. */
function SunIcon() {
  return (
    <svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true" fill="currentColor">
      <path d="M10 3.25a.75.75 0 0 1 .75.75v1a.75.75 0 0 1-1.5 0V4a.75.75 0 0 1 .75-.75Zm0 11a.75.75 0 0 1 .75.75v1a.75.75 0 0 1-1.5 0v-1a.75.75 0 0 1 .75-.75ZM16.75 10a.75.75 0 0 1-.75.75h-1a.75.75 0 0 1 0-1.5h1a.75.75 0 0 1 .75.75Zm-11 0a.75.75 0 0 1-.75.75H4a.75.75 0 0 1 0-1.5h1a.75.75 0 0 1 .75.75Zm8.96-4.71a.75.75 0 0 1 0 1.06l-.7.71a.75.75 0 1 1-1.07-1.06l.71-.71a.75.75 0 0 1 1.06 0ZM7.06 12.94a.75.75 0 0 1 0 1.06l-.71.71a.75.75 0 0 1-1.06-1.06l.71-.71a.75.75 0 0 1 1.06 0Zm7.65 1.77a.75.75 0 0 1-1.06 0l-.71-.71a.75.75 0 1 1 1.06-1.06l.71.71a.75.75 0 0 1 0 1.06ZM7.06 7.06a.75.75 0 0 1-1.06 0l-.71-.71a.75.75 0 0 1 1.06-1.06l.71.7a.75.75 0 0 1 0 1.07ZM10 6.5a3.5 3.5 0 1 0 0 7 3.5 3.5 0 0 0 0-7Z" />
    </svg>
  );
}

function MoonIcon() {
  return (
    <svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true" fill="currentColor">
      <path d="M8.28 3.11a.75.75 0 0 1 .1.96 5.5 5.5 0 0 0 7.55 7.55.75.75 0 0 1 1.06.86A7.5 7.5 0 1 1 7.42 3.01a.75.75 0 0 1 .86.1Z" />
    </svg>
  );
}

interface ThemeToggleProps {
  className?: string;
}

/**
 * A two-state switch: sun while light, moon while dark.
 *
 * The icon shows the theme that is on screen; the accessible label and the
 * tooltip say what pressing it will do, which is what a screen-reader user
 * needs to hear.
 */
export function ThemeToggle({ className = '' }: ThemeToggleProps) {
  const { t } = useTranslation();
  const { theme, toggleTheme } = useTheme();

  const dark = theme === 'dark';
  const Icon = dark ? MoonIcon : SunIcon;
  const label = dark ? t('theme.switchToLight') : t('theme.switchToDark');

  return (
    <button
      type="button"
      onClick={toggleTheme}
      aria-label={label}
      title={label}
      aria-pressed={dark}
      data-theme-state={theme}
      className={`inline-flex h-9 w-9 items-center justify-center rounded-lg border border-line bg-surface text-muted transition hover:border-line-strong hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent ${className}`.trim()}
    >
      <Icon />
      {/* Announced on change, so the new state is spoken rather than inferred. */}
      <span className="sr-only" aria-live="polite">
        {t('theme.current', { mode: t(`theme.${theme}`) })}
      </span>
    </button>
  );
}
