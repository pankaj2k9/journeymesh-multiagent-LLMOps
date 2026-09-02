import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { NavLink } from 'react-router-dom';

import { ThemeToggle } from '../common/ThemeToggle';
import { LanguageSelector } from '../language/LanguageSelector';

const NAV = [
  { to: '/', key: 'nav.plan', end: true },
  { to: '/history', key: 'nav.history', end: false },
  { to: '/about', key: 'nav.about', end: false },
  { to: '/settings', key: 'nav.settings', end: false },
];

export function Header() {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);

  const linkClass = ({ isActive }: { isActive: boolean }) =>
    `rounded-lg px-3 py-2 text-sm font-medium transition ${
      isActive ? 'bg-accent-soft text-accent' : 'text-muted hover:text-ink'
    }`;

  return (
    <header className="sticky top-0 z-30 border-b border-line bg-surface/90 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3 sm:px-6">
        <NavLink to="/" className="flex items-center gap-2.5" aria-label={t('app.name')}>
          <img src="/favicon.svg" alt="" width={34} height={34} className="rounded-[9px]" />
          <span className="flex flex-col leading-tight">
            <span className="text-base font-semibold text-ink">{t('app.name')}</span>
            <span className="hidden text-xs text-muted sm:block">{t('app.tagline')}</span>
          </span>
        </NavLink>

        <nav className="hidden items-center gap-1 md:flex" aria-label={t('nav.plan')}>
          {NAV.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.end} className={linkClass}>
              {t(item.key)}
            </NavLink>
          ))}
        </nav>

        <div className="flex items-center gap-2">
          <LanguageSelector />
          <ThemeToggle />
          <button
            type="button"
            className="rounded-lg p-2 text-muted transition hover:text-ink md:hidden"
            aria-expanded={open}
            aria-label={open ? t('nav.closeMenu') : t('nav.openMenu')}
            onClick={() => setOpen((value) => !value)}
          >
            <svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true" fill="currentColor">
              {open ? (
                <path d="M4.7 4.7a1 1 0 0 1 1.4 0L10 8.6l3.9-3.9a1 1 0 1 1 1.4 1.4L11.4 10l3.9 3.9a1 1 0 0 1-1.4 1.4L10 11.4l-3.9 3.9a1 1 0 0 1-1.4-1.4L8.6 10 4.7 6.1a1 1 0 0 1 0-1.4Z" />
              ) : (
                <path d="M3 5.5A1 1 0 0 1 4 4.5h12a1 1 0 1 1 0 2H4a1 1 0 0 1-1-1Zm0 4.5a1 1 0 0 1 1-1h12a1 1 0 1 1 0 2H4a1 1 0 0 1-1-1Zm1 3.5a1 1 0 1 0 0 2h12a1 1 0 1 0 0-2H4Z" />
              )}
            </svg>
          </button>
        </div>
      </div>

      {open ? (
        <nav className="border-t border-line bg-surface px-4 py-2 md:hidden">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              onClick={() => setOpen(false)}
              className={({ isActive }) =>
                `block rounded-lg px-3 py-2 text-sm font-medium ${
                  isActive ? 'bg-accent-soft text-accent' : 'text-muted'
                }`
              }
            >
              {t(item.key)}
            </NavLink>
          ))}
        </nav>
      ) : null}
    </header>
  );
}
