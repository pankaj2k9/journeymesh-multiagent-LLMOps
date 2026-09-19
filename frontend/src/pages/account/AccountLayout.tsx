import { useTranslation } from 'react-i18next';
import { NavLink, Outlet } from 'react-router-dom';

import { useAuth } from '../../auth/useAuth';

/**
 * The signed-in area: one shell for the dashboard, history, settings and, for
 * an administrator, the admin panel - so they read as sections of one place
 * rather than unrelated pages in the public menu.
 */
export function AccountLayout() {
  const { t } = useTranslation();
  const { user, signOut } = useAuth();

  const sections = [
    { to: '/dashboard', key: 'nav.overview', end: true },
    { to: '/dashboard/history', key: 'nav.history', end: false },
    { to: '/dashboard/settings', key: 'nav.settings', end: false },
    ...(user?.role === 'ADMIN' ? [{ to: '/admin', key: 'nav.admin', end: false }] : []),
  ];

  const tabClass = ({ isActive }: { isActive: boolean }) =>
    `whitespace-nowrap rounded-lg px-3 py-2 text-sm font-medium transition ${
      isActive
        ? 'bg-accent text-accent-contrast shadow-card'
        : 'text-muted hover:bg-elevated hover:text-ink'
    }`;

  const name = user?.display_name || user?.email?.split('@')[0] || '';

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-line bg-surface p-3 shadow-card">
        <div className="flex min-w-0 items-center gap-3 px-1">
          <span
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-accent-soft text-sm font-semibold uppercase text-accent"
            aria-hidden="true"
          >
            {name.slice(0, 1)}
          </span>
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold text-ink">{name}</p>
            <p className="truncate text-xs text-muted">
              {user?.email}
              {user?.role === 'ADMIN' ? ` · ${t('nav.admin')}` : ''}
            </p>
          </div>
        </div>
        <nav className="-mx-1 flex gap-1 overflow-x-auto px-1" aria-label={t('nav.account')}>
          {sections.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.end} className={tabClass}>
              {t(item.key)}
            </NavLink>
          ))}
          <button
            type="button"
            onClick={signOut}
            className="whitespace-nowrap rounded-lg px-3 py-2 text-sm font-medium text-muted transition hover:bg-elevated hover:text-ink"
          >
            {t('auth.signOut')}
          </button>
        </nav>
      </div>

      <Outlet />
    </div>
  );
}

export default AccountLayout;
