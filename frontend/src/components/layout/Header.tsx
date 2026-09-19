import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { NavLink } from 'react-router-dom';

import { USER_LOGIN_PATH } from '../../auth/RequireAuth';
import { useAuth } from '../../auth/useAuth';
import { ThemeToggle } from '../common/ThemeToggle';
import { LanguageSelector } from '../language/LanguageSelector';

// The public menu. Dashboard, history and settings live in the signed-in area
// (see AccountLayout), reached from the account button on the right.
const NAV = [
  { to: '/', key: 'nav.plan', end: true },
  { to: '/blog', key: 'nav.blog', end: false },
  { to: '/about', key: 'nav.about', end: false },
];

export function Header() {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const { signedIn, user } = useAuth();
  const accountLinks = signedIn
    ? [
        { to: '/dashboard', key: 'nav.dashboard', end: false },
        ...(user?.role === 'ADMIN' ? [{ to: '/admin', key: 'nav.admin', end: false }] : []),
      ]
    : [{ to: USER_LOGIN_PATH, key: 'auth.signIn', end: false }];

  const linkClass = ({ isActive }: { isActive: boolean }) =>
    `rounded-lg px-3 py-2 text-sm font-medium transition ${
      isActive ? 'bg-accent-soft text-accent' : 'text-muted hover:text-ink'
    }`;

  return (
    <header
      data-app-header
      className="sticky top-0 z-30 border-b border-line bg-surface/90 backdrop-blur"
    >
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3 sm:px-6">
        <NavLink to="/" className="flex items-center gap-2.5" aria-label={t('app.name')}>
          <img src="/logo-mark.png" alt="" width={36} height={36} />
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
          {signedIn ? (
            <NavLink
              to="/dashboard"
              title={user?.email}
              className="hidden items-center gap-2 rounded-full border border-line bg-surface py-1 pl-1 pr-3 text-sm font-medium text-ink shadow-card transition hover:border-accent sm:flex"
            >
              <span
                className="flex h-7 w-7 items-center justify-center rounded-full bg-accent text-xs font-semibold uppercase text-accent-contrast"
                aria-hidden="true"
              >
                {(user?.display_name || user?.email || '?').slice(0, 1)}
              </span>
              {t('nav.dashboard')}
            </NavLink>
          ) : (
            <NavLink
              to={USER_LOGIN_PATH}
              className="hidden rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-contrast shadow-card transition hover:bg-accent-strong sm:block"
            >
              {t('auth.signIn')}
            </NavLink>
          )}
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
          {[...NAV, ...accountLinks].map((item) => (
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
