import { Trans, useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import { ADMIN_LOGIN_PATH, USER_LOGIN_PATH } from '../../auth/RequireAuth';
import { useAuth } from '../../auth/useAuth';

interface FooterLink {
  to: string;
  key: string;
}

function Column({ title, links }: { title: string; links: FooterLink[] }) {
  const { t } = useTranslation();
  return (
    <nav aria-label={title}>
      <h2 className="text-xs font-semibold uppercase tracking-wider text-ink">{title}</h2>
      <ul className="mt-3 space-y-2">
        {links.map((link) => (
          <li key={link.to}>
            <Link to={link.to} className="text-sm text-muted transition hover:text-accent">
              {t(link.key)}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}

export function Footer() {
  const { t } = useTranslation();
  const { signedIn } = useAuth();

  const explore: FooterLink[] = [
    { to: '/#planner', key: 'footer.planTrip' },
    { to: '/blog', key: 'nav.blog' },
    { to: '/about', key: 'nav.about' },
  ];

  const account: FooterLink[] = signedIn
    ? [
        { to: '/dashboard', key: 'nav.dashboard' },
        { to: '/dashboard/history', key: 'nav.history' },
        { to: '/dashboard/settings', key: 'nav.settings' },
      ]
    : [
        { to: USER_LOGIN_PATH, key: 'auth.signIn' },
        { to: `${USER_LOGIN_PATH}?next=/dashboard`, key: 'footer.myJourneys' },
      ];

  const guides: FooterLink[] = [
    { to: '/blog/domestic-vs-international-checklist', key: 'footer.checklist' },
    { to: '/blog/set-a-travel-budget-that-holds', key: 'footer.budgetGuide' },
    { to: '/blog/plan-a-trip-with-an-ai-crew', key: 'footer.howItWorks' },
  ];

  return (
    <footer data-app-footer className="mt-12 border-t border-line bg-surface">
      <div className="mx-auto grid max-w-6xl gap-8 px-4 py-10 sm:px-6 md:grid-cols-[1.4fr_1fr_1fr_1fr]">
        <div>
          <Link to="/" className="inline-flex items-center gap-2.5" aria-label={t('app.name')}>
            <img src="/favicon.svg" alt="" width={36} height={36} className="rounded-[10px]" />
            <span className="text-base font-semibold text-ink">{t('app.name')}</span>
          </Link>
          <p className="mt-3 max-w-xs text-sm text-muted">{t('app.tagline')}</p>
          <p className="mt-3 max-w-xs text-xs text-faint">{t('common.footerNote')}</p>
        </div>

        <Column title={t('footer.explore')} links={explore} />
        <Column title={t('footer.account')} links={account} />
        <Column title={t('footer.guides')} links={guides} />
      </div>

      <div className="border-t border-line">
        <div className="mx-auto flex max-w-6xl flex-col gap-2 px-4 py-4 text-xs text-muted sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <p>
            © {new Date().getFullYear()} {t('app.name')} ·{' '}
            <Trans
              i18nKey="common.poweredBy"
              values={{ author: 'Pankaj' }}
              components={{
                site: (
                  <a
                    className="text-accent underline-offset-2 hover:underline"
                    href="https://pankajpramanik.com"
                    target="_blank"
                    rel="noreferrer noopener"
                  />
                ),
              }}
            />
          </p>
          <Link to={ADMIN_LOGIN_PATH} className="transition hover:text-accent">
            {t('footer.adminLogin')}
          </Link>
        </div>
      </div>
    </footer>
  );
}
