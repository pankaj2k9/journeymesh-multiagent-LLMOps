import { useTranslation } from 'react-i18next';

export function Footer() {
  const { t } = useTranslation();
  return (
    <footer className="border-t border-line bg-surface">
      <div className="mx-auto flex max-w-6xl flex-col gap-2 px-4 py-6 text-sm text-muted sm:flex-row sm:items-center sm:justify-between sm:px-6">
        <p>{t('common.footerNote')}</p>
        <p>
          {t('common.poweredBy', { author: 'Pankaj' })} ·{' '}
          <a
            className="text-accent underline-offset-2 hover:underline"
            href="https://pankajpramanik.com"
            target="_blank"
            rel="noreferrer noopener"
          >
            pankajpramanik.com
          </a>
        </p>
      </div>
    </footer>
  );
}
