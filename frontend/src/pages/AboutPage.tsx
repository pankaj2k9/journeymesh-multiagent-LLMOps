import { useTranslation } from 'react-i18next';

import { Card } from '../components/common/Card';

const AGENT_KEYS = [
  'supervisor',
  'flight',
  'hotel',
  'weather',
  'budget',
  'itinerary',
  'final',
] as const;

export function AboutPage() {
  const { t } = useTranslation();

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-xl font-semibold text-ink sm:text-2xl">{t('about.title')}</h1>
        <p className="mt-2 max-w-3xl text-sm text-muted">{t('about.intro')}</p>
      </header>

      <Card className="p-5">
        <h2 className="text-base font-semibold text-ink">
          {t('about.architectureTitle')}
        </h2>
        <p className="mt-2 text-sm text-muted">{t('about.architectureBody')}</p>
      </Card>

      <Card className="p-5">
        <h2 className="text-base font-semibold text-ink">{t('about.agentsTitle')}</h2>
        <ul className="mt-2 space-y-1.5 text-sm text-muted">
          {AGENT_KEYS.map((key) => (
            <li key={key}>• {t(`about.agents.${key}`)}</li>
          ))}
        </ul>
      </Card>

      <div className="grid gap-4 sm:grid-cols-2">
        <Card className="p-5">
          <h2 className="text-base font-semibold text-ink">{t('about.safetyTitle')}</h2>
          <p className="mt-2 text-sm text-muted">{t('about.safetyBody')}</p>
        </Card>
        <Card className="p-5">
          <h2 className="text-base font-semibold text-ink">{t('about.languagesTitle')}</h2>
          <p className="mt-2 text-sm text-muted">{t('about.languagesBody')}</p>
        </Card>
      </div>

      <Card className="p-5">
        <h2 className="text-base font-semibold text-ink">{t('about.authorTitle')}</h2>
        <p className="mt-2 text-sm text-ink">{t('about.authorName')}</p>
        <p className="text-sm text-muted">
          <a className="hover:underline" href={`mailto:${t('about.authorEmail')}`}>
            {t('about.authorEmail')}
          </a>
        </p>
        <p className="text-sm">
          <a
            className="text-accent hover:underline"
            href="https://pankajpramanik.com"
            target="_blank"
            rel="noreferrer noopener"
          >
            {t('about.authorSite')}
          </a>
        </p>
      </Card>
    </div>
  );
}

export default AboutPage;
