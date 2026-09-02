import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it } from 'vitest';

// Imported as raw text so the shipped HTML itself is what gets asserted.
import indexHtml from '../../index.html?raw';
import { ThemeToggle } from '../components/common/ThemeToggle';
import i18n from '../i18n/config';
import { LANGUAGE_STORAGE_KEY } from '../utils/constants';
import {
  DARK_CLASS,
  THEME_INIT_SCRIPT,
  THEME_STORAGE_KEY,
  ThemeProvider,
  initialTheme,
  resolveTheme,
  useTheme,
} from '../theme';

// ---------------------------------------------------------------------------
// A controllable prefers-color-scheme, so "system" can actually be exercised.
// ---------------------------------------------------------------------------
type Listener = (event: MediaQueryListEvent) => void;

let systemDark = false;
let listeners: Listener[] = [];

function mockMatchMedia(): void {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    configurable: true,
    value: (query: string) => ({
      matches: query.includes('prefers-color-scheme: dark') ? systemDark : false,
      media: query,
      onchange: null,
      addEventListener: (_: string, listener: Listener) => listeners.push(listener),
      removeEventListener: (_: string, listener: Listener) => {
        listeners = listeners.filter((item) => item !== listener);
      },
      addListener: (listener: Listener) => listeners.push(listener),
      removeListener: (listener: Listener) => {
        listeners = listeners.filter((item) => item !== listener);
      },
      dispatchEvent: () => false,
    }),
  });
}

/** Flip the operating system theme while the app is open. */
function setSystemDark(value: boolean): void {
  systemDark = value;
  act(() => {
    listeners.forEach((listener) => listener({ matches: value } as MediaQueryListEvent));
  });
}

function isDark(): boolean {
  return document.documentElement.classList.contains(DARK_CLASS);
}

function Probe() {
  const { theme, resolvedTheme } = useTheme();
  return (
    <div>
      <span data-testid="theme">{theme}</span>
      <span data-testid="resolved">{resolvedTheme}</span>
    </div>
  );
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
  systemDark = false;
  listeners = [];
  mockMatchMedia();
  window.localStorage.clear();
  document.documentElement.className = '';
  document.documentElement.removeAttribute('style');
  document.documentElement.removeAttribute('data-theme');
});

// ---------------------------------------------------------------------------
// Rendering each mode
// ---------------------------------------------------------------------------
describe('theme modes', () => {
  it('renders light mode and leaves the dark class off', () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, 'light');
    renderThemed();

    expect(screen.getByTestId('theme')).toHaveTextContent('light');
    expect(screen.getByTestId('resolved')).toHaveTextContent('light');
    expect(isDark()).toBe(false);
    expect(document.documentElement.style.colorScheme).toBe('light');
  });

  it('renders dark mode and applies the dark class', () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, 'dark');
    renderThemed();

    expect(screen.getByTestId('resolved')).toHaveTextContent('dark');
    expect(isDark()).toBe(true);
    expect(document.documentElement.style.colorScheme).toBe('dark');
  });

  it('follows prefers-color-scheme in system mode', () => {
    systemDark = true;
    window.localStorage.setItem(THEME_STORAGE_KEY, 'system');
    renderThemed();

    expect(screen.getByTestId('theme')).toHaveTextContent('system');
    expect(screen.getByTestId('resolved')).toHaveTextContent('dark');
    expect(isDark()).toBe(true);
  });

  it('defaults to the system theme on a first visit', () => {
    expect(initialTheme()).toBe('system');

    systemDark = true;
    renderThemed();
    expect(screen.getByTestId('theme')).toHaveTextContent('system');
    expect(isDark()).toBe(true);
  });

  it('updates live when the operating system changes and mode is system', () => {
    renderThemed();
    expect(isDark()).toBe(false);

    setSystemDark(true);
    expect(isDark()).toBe(true);
    expect(screen.getByTestId('resolved')).toHaveTextContent('dark');

    setSystemDark(false);
    expect(isDark()).toBe(false);
  });

  it('ignores operating-system changes once a theme is chosen explicitly', async () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, 'light');
    renderThemed();

    setSystemDark(true);
    expect(isDark()).toBe(false);
    expect(screen.getByTestId('resolved')).toHaveTextContent('light');
  });
});

// ---------------------------------------------------------------------------
// The toggle
// ---------------------------------------------------------------------------
describe('theme toggle', () => {
  it('cycles light, dark, then system', async () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, 'light');
    renderThemed();
    const button = screen.getByRole('button');

    await userEvent.click(button);
    expect(screen.getByTestId('theme')).toHaveTextContent('dark');
    expect(isDark()).toBe(true);

    await userEvent.click(button);
    expect(screen.getByTestId('theme')).toHaveTextContent('system');

    await userEvent.click(button);
    expect(screen.getByTestId('theme')).toHaveTextContent('light');
    expect(isDark()).toBe(false);
  });

  it('adds and removes the dark class as it goes', async () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, 'light');
    renderThemed();

    expect(document.documentElement.classList.contains(DARK_CLASS)).toBe(false);
    await userEvent.click(screen.getByRole('button'));
    expect(document.documentElement.classList.contains(DARK_CLASS)).toBe(true);
    await userEvent.click(screen.getByRole('button'));
    await userEvent.click(screen.getByRole('button'));
    expect(document.documentElement.classList.contains(DARK_CLASS)).toBe(false);
  });

  it('persists a manual choice to localStorage', async () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, 'light');
    renderThemed();

    await userEvent.click(screen.getByRole('button'));
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark');
  });

  it('keeps the chosen theme across a reload', async () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, 'light');
    const first = renderThemed();

    await userEvent.click(screen.getByRole('button'));
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark');
    first.unmount();

    // A reload: fresh render, same storage.
    document.documentElement.className = '';
    renderThemed();
    expect(screen.getByTestId('resolved')).toHaveTextContent('dark');
    expect(isDark()).toBe(true);
  });

  it('describes what pressing it will do, in the active language', async () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, 'light');
    renderThemed();

    const button = screen.getByRole('button');
    expect(button).toHaveAccessibleName(/switch to dark mode/i);
    expect(button).toHaveAttribute('title', expect.stringMatching(/switch to dark mode/i));

    await userEvent.click(button);
    expect(screen.getByRole('button')).toHaveAccessibleName(/use system theme/i);

    await userEvent.click(screen.getByRole('button'));
    expect(screen.getByRole('button')).toHaveAccessibleName(/switch to light mode/i);
  });

  it('exposes the current mode for assistive technology', () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, 'dark');
    renderThemed();
    expect(screen.getByRole('button')).toHaveAttribute('data-theme-state', 'dark');
    expect(screen.getByRole('button')).toHaveAttribute('data-resolved-theme', 'dark');
  });
});

// ---------------------------------------------------------------------------
// Independence from language
// ---------------------------------------------------------------------------
describe('theme and language are independent', () => {
  it('changing the theme does not change the language', async () => {
    await i18n.changeLanguage('bn');
    window.localStorage.setItem(LANGUAGE_STORAGE_KEY, 'bn');
    window.localStorage.setItem(THEME_STORAGE_KEY, 'light');

    renderThemed();
    await userEvent.click(screen.getByRole('button'));

    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark');
    expect(window.localStorage.getItem(LANGUAGE_STORAGE_KEY)).toBe('bn');
    expect(i18n.language).toBe('bn');

    await i18n.changeLanguage('en');
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
    expect(THEME_STORAGE_KEY).not.toBe(LANGUAGE_STORAGE_KEY);
  });

  it('labels the toggle in the selected language', async () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, 'light');
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
// Robustness
// ---------------------------------------------------------------------------
describe('theme robustness', () => {
  it('ignores a corrupt stored value', () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, 'neon');
    expect(initialTheme()).toBe('system');
  });

  it('resolves a preference without a matchMedia implementation', () => {
    // @ts-expect-error - deliberately removing the API
    delete window.matchMedia;
    expect(resolveTheme('system')).toBe('light');
    expect(resolveTheme('dark')).toBe('dark');
    mockMatchMedia();
  });

  it('ships a blocking initialiser that matches the theme module', () => {
    const html = indexHtml;
    const match = html.match(/<script>(\(function\(\)\{try\{var k=.*?)<\/script>/s);

    expect(match, 'index.html must contain the inline theme initialiser').not.toBeNull();
    expect(match?.[1]).toBe(THEME_INIT_SCRIPT);
    // It must run before the bundle, or the flash it prevents comes back.
    expect(html.indexOf('journeymesh_theme')).toBeLessThan(html.indexOf('/src/main.tsx'));
  });
});
