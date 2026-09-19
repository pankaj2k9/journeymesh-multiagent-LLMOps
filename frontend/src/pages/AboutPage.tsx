import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import { Button } from '../components/common/Button';
import { Card } from '../components/common/Card';
import { FAQ_IDS, FEATURES, STEPS } from '../utils/about';

/**
 * The About page, written for travellers: what Travel Crew AI does for them,
 * how planning works from their side, where it covers, and the honest limits
 * (prices are estimates; booking happens with the operator).
 */
export function AboutPage() {
  const { t } = useTranslation();

  return (
    <div className="space-y-10">
      {/* ---- Who we are --------------------------------------------------- */}
      <header className="jm-hero p-6 sm:p-10">
        <div className="jm-rise max-w-3xl">
          <p className="text-sm font-medium text-accent">{t('about.eyebrow')}</p>
          <h1 className="text-balance mt-2 text-3xl font-bold text-ink sm:text-4xl">
            {t('about.title')}
          </h1>
          <p className="mt-3 text-base leading-relaxed text-muted sm:text-lg">{t('about.intro')}</p>
          <Link to="/#planner" className="mt-5 inline-block">
            <Button size="lg">{t('about.cta')}</Button>
          </Link>
        </div>
      </header>

      {/* ---- What you can do ---------------------------------------------- */}
      <section aria-labelledby="about-features">
        <h2 id="about-features" className="text-xl font-semibold text-ink">
          {t('about.featuresTitle')}
        </h2>
        <ul className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {FEATURES.map((feature, index) => (
            <li key={feature.id} className="jm-rise" style={{ animationDelay: `${index * 50}ms` }}>
              <Card className="h-full p-5 transition hover:-translate-y-0.5 hover:shadow-raised">
                <span aria-hidden="true" className="text-2xl">
                  {feature.icon}
                </span>
                <h3 className="mt-2 text-sm font-semibold text-ink">
                  {t(`about.features.${feature.id}.title`)}
                </h3>
                <p className="mt-1 text-sm text-muted">{t(`about.features.${feature.id}.body`)}</p>
              </Card>
            </li>
          ))}
        </ul>
      </section>

      {/* ---- How it works -------------------------------------------------- */}
      <section aria-labelledby="about-steps">
        <h2 id="about-steps" className="text-xl font-semibold text-ink">
          {t('about.stepsTitle')}
        </h2>
        <ol className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {STEPS.map((step, index) => (
            <li key={step.id}>
              <Card className="h-full p-5">
                <div className="flex items-center gap-3">
                  <span className="inline-flex h-9 w-9 items-center justify-center rounded-full bg-accent text-sm font-semibold text-accent-contrast">
                    {index + 1}
                  </span>
                  <span aria-hidden="true" className="text-xl">
                    {step.icon}
                  </span>
                </div>
                <h3 className="mt-3 text-sm font-semibold text-ink">
                  {t(`about.steps.${step.id}.title`)}
                </h3>
                <p className="mt-1 text-sm text-muted">{t(`about.steps.${step.id}.body`)}</p>
              </Card>
            </li>
          ))}
        </ol>
      </section>

      {/* ---- Where we cover and our promise --------------------------------- */}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="p-6">
          <h2 className="text-lg font-semibold text-ink">{t('about.coverageTitle')}</h2>
          <p className="mt-2 text-sm leading-relaxed text-muted">{t('about.coverageBody')}</p>
        </Card>
        <Card className="p-6">
          <h2 className="text-lg font-semibold text-ink">{t('about.promiseTitle')}</h2>
          <p className="mt-2 text-sm leading-relaxed text-muted">{t('about.promiseBody')}</p>
        </Card>
      </div>

      {/* ---- Questions ------------------------------------------------------- */}
      <section aria-labelledby="about-faq">
        <h2 id="about-faq" className="text-xl font-semibold text-ink">
          {t('about.faqTitle')}
        </h2>
        <div className="mt-4 divide-y divide-line rounded-2xl border border-line bg-surface">
          {FAQ_IDS.map((id) => (
            <details key={id} className="group px-5 py-4">
              <summary className="flex cursor-pointer list-none items-center justify-between gap-3 text-sm font-medium text-ink">
                {t(`about.faq.${id}.q`)}
                <span aria-hidden="true" className="text-muted transition group-open:rotate-45">
                  +
                </span>
              </summary>
              <p className="mt-2 text-sm leading-relaxed text-muted">{t(`about.faq.${id}.a`)}</p>
            </details>
          ))}
        </div>
      </section>

      {/* ---- Contact --------------------------------------------------------- */}
      <Card className="flex flex-wrap items-center justify-between gap-4 p-6">
        <div>
          <h2 className="text-lg font-semibold text-ink">{t('about.contactTitle')}</h2>
          <p className="mt-1 text-sm text-muted">{t('about.contactBody')}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <a href={`mailto:${t('about.authorEmail')}`}>
            <Button variant="secondary">{t('about.emailUs')}</Button>
          </a>
          <a href="https://pankajpramanik.com" target="_blank" rel="noreferrer noopener">
            <Button variant="ghost">{t('about.authorSite')}</Button>
          </a>
        </div>
      </Card>
    </div>
  );
}

export default AboutPage;
