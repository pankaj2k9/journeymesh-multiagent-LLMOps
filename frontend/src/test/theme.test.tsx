import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';

// Imported as raw text so the shipped HTML itself is what gets asserted.
import indexHtml from '../../index.html?raw';
import { ThemeSelector } from '../components/common/ThemeSelector';
import { ThemeToggle } from '../components/common/ThemeToggle';
import i18n from '../i18n/config';
import { LANGUAGE_STORAGE_KEY } from '../utils/constants';
import {
  DARK_CLASS,
  DEFAULT_THEME,
  THEME_INIT_SCRIPT,
  THEME_STORAGE_KEY,
  ThemeProvider,
  initialTheme,
  useTheme,
} from '../theme';

function isDark(): boolean {
  return document.documentElement.classList.contains(DARK_CLASS);
}

function Probe() {
  const { theme } = useTheme();
  return <span data-testid="theme">{theme}</span>;
}

function renderThemed(ui = <ThemeToggle />) {
  return render(
    <ThemeProvider>
      {ui}
      <Probe />
    </ThemeProvider>,
  );
}

beforeEach(() => {
  window.localStorage.clear();
  document.documentElement.className = '';
  document.documentElement.removeAttribute('style');
  document.documentElement.removeAttribute('data-theme');
});

// ---------------------------------------------------------------------------
// The two themes
// ---------------------------------------------------------------------------
describe('themes', () => {
  it('starts in light mode on a first visit', () => {
    expect(DEFAULT_THEME).toBe('light');
    expect(initialTheme()).toBe('light');

    renderThemed();
    expect(screen.getByTestId('theme')).toHaveTextContent('light');
    expect(isDark()).toBe(false);
    expect(document.documentElement.style.colorScheme).toBe('light');
  });

  it('renders dark mode and applies the dark class', () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, 'dark');
    renderThemed();

    expect(screen.getByTestId('theme')).toHaveTextContent('dark');
    expect(isDark()).toBe(true);
    expect(document.documentElement.style.colorScheme).toBe('dark');
    expect(document.documentElement.dataset.theme).toBe('dark');
  });

  it('ignores a value it does not recognise', () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, 'system');
    expect(initialTheme()).toBe('light');

    window.localStorage.setItem(THEME_STORAGE_KEY, 'neon');
    expect(initialTheme()).toBe('light');
  });
});

// ---------------------------------------------------------------------------
// The toggle
// ---------------------------------------------------------------------------
describe('theme toggle', () => {
  it('switches between light and dark', async () => {
    renderThemed();
    const button = screen.getByRole('button');

    await userEvent.click(button);
    expect(screen.getByTestId('theme')).toHaveTextContent('dark');
    expect(isDark()).toBe(true);

    await userEvent.click(button);
    expect(screen.getByTestId('theme')).toHaveTextContent('light');
    expect(isDark()).toBe(false);
  });

  it('persists the choice', async () => {
    renderThemed();
    await userEvent.click(screen.getByRole('button'));
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark');
  });

  it('keeps the chosen theme across a reload', async () => {
    const first = renderThemed();
    await userEvent.click(screen.getByRole('button'));
    first.unmount();

    // A reload: fresh render, same storage.
    document.documentElement.className = '';
    renderThemed();
    expect(screen.getByTestId('theme')).toHaveTextContent('dark');
    expect(isDark()).toBe(true);
  });

  it('says what pressing it will do', async () => {
    renderThemed();
    const button = screen.getByRole('button');

    expect(button).toHaveAccessibleName(/switch to dark mode/i);
    expect(button).toHaveAttribute('title', expect.stringMatching(/switch to dark mode/i));
    expect(button).toHaveAttribute('aria-pressed', 'false');

    await userEvent.click(button);
    const pressed = screen.getByRole('button');
    expect(pressed).toHaveAccessibleName(/switch to light mode/i);
    expect(pressed).toHaveAttribute('aria-pressed', 'true');
  });

  it('exposes the current theme as a data attribute', () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, 'dark');
    renderThemed();
    expect(screen.getByRole('button')).toHaveAttribute('data-theme-state', 'dark');
  });
});

// ---------------------------------------------------------------------------
// The explicit selector on the settings page
// ---------------------------------------------------------------------------
describe('theme selector', () => {
  it('offers both themes and marks the active one', () => {
    render(
      <ThemeProvider>
        <ThemeSelector />
        <Probe />
      </ThemeProvider>,
    );

    expect(screen.getAllByRole('radio')).toHaveLength(2);
    expect(screen.getByRole('radio', { name: /^light$/i })).toBeChecked();
  });

  it('selects a theme directly and persists it', async () => {
    render(
      <ThemeProvider>
        <ThemeSelector />
        <Probe />
      </ThemeProvider>,
    );

    await userEvent.click(screen.getByRole('radio', { name: /^dark$/i }));

    expect(screen.getByTestId('theme')).toHaveTextContent('dark');
    expect(isDark()).toBe(true);
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark');
  });

  it('is grouped and labelled for assistive technology', () => {
    render(
      <ThemeProvider>
        <ThemeSelector />
      </ThemeProvider>,
    );
    expect(screen.getByRole('radiogroup')).toHaveAccessibleName(/theme/i);
  });
});

// ---------------------------------------------------------------------------
// Independence from language
// ---------------------------------------------------------------------------
describe('theme and language are independent', () => {
  it('changing the theme does not change the language', async () => {
    await act(async () => {
      await i18n.changeLanguage('bn');
    });
    window.localStorage.setItem(LANGUAGE_STORAGE_KEY, 'bn');

    renderThemed();
    await userEvent.click(screen.getByRole('button'));

    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark');
    expect(window.localStorage.getItem(LANGUAGE_STORAGE_KEY)).toBe('bn');
    expect(i18n.language).toBe('bn');

    await act(async () => {
      await i18n.changeLanguage('en');
    });
  });

  it('changing the language does not change the theme', async () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, 'dark');
    renderThemed();
    expect(isDark()).toBe(true);

    await act(async () => {
      await i18n.changeLanguage('hi');
    });

    expect(isDark()).toBe(true);
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark');

    await act(async () => {
      await i18n.changeLanguage('en');
    });
  });

  it('uses separate storage keys', () => {
    expect(THEME_STORAGE_KEY).toBe('journeymesh_theme');
    expect(LANGUAGE_STORAGE_KEY).toBe('journeymesh_language');
  });

  it('labels the toggle in the selected language', async () => {
    await act(async () => {
      await i18n.changeLanguage('hi');
    });

    renderThemed();
    expect(screen.getByRole('button').getAttribute('aria-label')).toMatch(/[ऀ-ॿ]/);

    await act(async () => {
      await i18n.changeLanguage('en');
    });
  });
});

// ---------------------------------------------------------------------------
// No flash of the wrong theme
// ---------------------------------------------------------------------------
describe('theme flash prevention', () => {
  it('ships a blocking initialiser that matches the theme module', () => {
    const match = indexHtml.match(/<script>(\(function\(\)\{try\{var k=.*?)<\/script>/s);

    expect(match, 'index.html must contain the inline theme initialiser').not.toBeNull();
    expect(match?.[1]).toBe(THEME_INIT_SCRIPT);
  });

  it('runs the initialiser before the bundle', () => {
    expect(indexHtml.indexOf('journeymesh_theme')).toBeLessThan(indexHtml.indexOf('/src/main.tsx'));
  });
});
