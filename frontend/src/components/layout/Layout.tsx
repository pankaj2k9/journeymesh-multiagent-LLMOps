import { useEffect, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { useLocation } from 'react-router-dom';

import { Footer } from './Footer';
import { Header } from './Header';

interface LayoutProps {
  children: ReactNode;
}

const PAGE_TITLE_KEYS: Record<string, string> = {
  '/dashboard': 'nav.dashboard',
  '/dashboard/history': 'nav.history',
  '/dashboard/settings': 'nav.settings',
  '/admin': 'nav.admin',
  '/user/login': 'auth.signIn',
  '/admin/login': 'auth.adminSignIn',
  '/blog': 'nav.blog',
  '/about': 'nav.about',
};

export function Layout({ children }: LayoutProps) {
  const { t } = useTranslation();
  const { pathname } = useLocation();

  // "History · Travel Crew AI", and the full product line on the home page, in
  // whichever language is active.
  useEffect(() => {
    const key = PAGE_TITLE_KEYS[pathname];
    document.title = key
      ? `${t(key)} · ${t('app.name')}`
      : `${t('app.name')} - ${t('app.tagline').replace(/\.$/, '')}`;
  }, [pathname, t]);

  return (
    <div className="flex min-h-screen flex-col bg-canvas">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-lg focus:bg-surface focus:px-4 focus:py-2 focus:text-sm focus:shadow"
      >
        {t('app.skipToContent')}
      </a>
      <Header />
      <main id="main" className="mx-auto w-full max-w-6xl flex-1 px-4 py-6 sm:px-6 sm:py-8">
        {children}
      </main>
      <Footer />
    </div>
  );
}
