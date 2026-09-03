import { useTranslation } from 'react-i18next';

import { Card } from '../components/common/Card';
import { Badge } from '../components/common/Badge';
import { CAPABILITIES, ENGINEERING_TOPICS, FLOW_STEPS, STACK } from '../utils/about';

/**
 * The About page.
 *
 * Written to be read by someone deciding whether this project is serious:
 * what it does, how a request travels through it, what it is built from, and
 * what it deliberately does not claim. Everything listed here exists in the
 * repository - there is no aspirational technology on this page.
 *
 * It uses only the existing Card and Badge primitives and the semantic theme
 * tokens, so it looks like the rest of JourneyMesh in both themes and needs no
 * styling of its own.
 */
export function AboutPage() {
  const { t } = useTranslation();

  return (
    <div className="space-y-8">
      {/* ---- Introduction -------------------------------------------------- */}
      <header className="max-w-3xl">
        <h1 className="text-2xl font-semibold text-ink sm:text-3xl">{t('about.title')}</h1>
        <p className="mt-1 text-base text-accent sm:text-lg">{t('about.subtitle')}</p>
        <p className="mt-4 text-sm leading-relaxed text-muted sm:text-base">
          {t('about.intro')}
        </p>
      </header>

      {/* ---- How it works -------------------------------------------------- */}
      <section aria-labelledby="how-it-works">
        <h2 id="how-it-works" className="text-lg font-semibold text-ink">
          {t('about.howItWorksTitle')}
        </h2>
        <p className="mt-1 text-sm text-muted">{t('about.howItWorksBody')}</p>

        <ol className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
          {FLOW_STEPS.map((step, index) => (
            <li key={step.id}>
              <Card className="h-full p-4">
                <div className="flex items-start gap-3">
                  <span
                    aria-hidden="true"
                    className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-accent-soft text-base"
                  >
                    {step.icon}
                  </span>
                  <div className="min-w-0">
                    <p className="text-xs font-medium uppercase tracking-wide text-faint">
                      {t('about.stepLabel', { number: index + 1 })}
                    </p>
                    <p className="mt-0.5 text-sm font-semibold text-ink">
                      {t(`about.flow.${step.id}.title`)}
                    </p>
                    <p className="mt-1 text-sm text-muted">
                      {t(`about.flow.${step.id}.body`)}
                    </p>
                  </div>
                </div>
              </Card>
            </li>
          ))}
        </ol>
      </section>

      {/* ---- Core capabilities --------------------------------------------- */}
      <section aria-labelledby="capabilities">
        <h2 id="capabilities" className="text-lg font-semibold text-ink">
          {t('about.capabilitiesTitle')}
        </h2>

        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          {CAPABILITIES.map((capability) => (
            <Card key={capability.id} className="p-5">
              <h3 className="flex items-center gap-2 text-sm font-semibold text-ink">
                <span aria-hidden="true">{capability.icon}</span>
                {t(`about.capabilities.${capability.id}.title`)}
              </h3>
              <p className="mt-2 text-sm text-muted">
                {t(`about.capabilities.${capability.id}.body`)}
              </p>
            </Card>
          ))}
        </div>
      </section>

      {/* ---- Technology stack ----------------------------------------------- */}
      <section aria-labelledby="stack">
        <h2 id="stack" className="text-lg font-semibold text-ink">
          {t('about.stackTitle')}
        </h2>
        <p className="mt-1 text-sm text-muted">{t('about.stackBody')}</p>

        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          {STACK.map((group) => (
            <Card key={group.id} className="p-5">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-muted">
                {t(`about.stack.${group.id}`)}
              </h3>
              <ul className="mt-2 flex flex-wrap gap-2">
                {group.items.map((item) => (
                  <li key={item}>
                    <Badge tone="neutral">{item}</Badge>
                  </li>
                ))}
              </ul>
            </Card>
          ))}
        </div>
      </section>

      {/* ---- Engineering focus ---------------------------------------------- */}
      <section aria-labelledby="engineering">
        <Card className="p-5 sm:p-6">
          <h2 id="engineering" className="text-lg font-semibold text-ink">
            {t('about.engineeringTitle')}
          </h2>
          <p className="mt-2 text-sm text-muted">{t('about.engineeringBody')}</p>
          <ul className="mt-4 flex flex-wrap gap-2">
            {ENGINEERING_TOPICS.map((topic) => (
              <li key={topic}>
                <Badge tone="brand">{t(`about.topics.${topic}`)}</Badge>
              </li>
            ))}
          </ul>
        </Card>
      </section>

      {/* ---- Languages, disclaimer, author ---------------------------------- */}
      <div className="grid gap-4 sm:grid-cols-2">
        <Card className="p-5">
          <h2 className="text-base font-semibold text-ink">{t('about.languagesTitle')}</h2>
          <p className="mt-2 text-sm text-muted">{t('about.languagesBody')}</p>
        </Card>
        <Card className="p-5">
          <h2 className="text-base font-semibold text-ink">{t('about.disclaimerTitle')}</h2>
          <p className="mt-2 text-sm text-muted">{t('about.disclaimer')}</p>
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
