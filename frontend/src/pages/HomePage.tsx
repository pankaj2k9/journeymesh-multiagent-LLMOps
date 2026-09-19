import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useLocation, useNavigate } from 'react-router-dom';

import { Button } from '../components/common/Button';
import { Callout } from '../components/common/Callout';
import { HeroFlight } from '../components/home/HeroFlight';
import { GuardrailBlockedCard } from '../components/planner/GuardrailBlockedCard';
import { PlannerForm } from '../components/planner/PlannerForm';
import { PlanningProgress } from '../components/planner/PlanningProgress';
import { usePlaces } from '../hooks/usePlaces';
import { usePlanTrip } from '../hooks/useTrips';
import type { GuardrailBlockedResponse, PlanRequestBody } from '../types';
import { isBlocked } from '../types';
import { describeApiError, isRetryable } from '../utils/apiError';

function Step({ title, body, index }: { title: string; body: string; index: number }) {
  return (
    <li
      className="jm-rise rounded-2xl border border-line bg-surface p-4 shadow-card transition hover:-translate-y-1 hover:shadow-raised"
      style={{ animationDelay: `${index * 90}ms` }}
    >
      <span className="inline-flex h-7 w-7 items-center justify-center rounded-full bg-accent-soft text-sm font-semibold text-accent">
        {index}
      </span>
      <h3 className="mt-3 text-sm font-semibold text-ink">{title}</h3>
      <p className="mt-1 text-sm text-muted">{body}</p>
    </li>
  );
}

export function HomePage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { hash } = useLocation();
  const planTrip = usePlanTrip();
  const countries = usePlaces();
  const [blocked, setBlocked] = useState<GuardrailBlockedResponse | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [retryable, setRetryable] = useState(false);
  // Kept so a failed run can be retried with the same request rather than
  // asking the traveller to fill the form in again.
  const [lastRequest, setLastRequest] = useState<PlanRequestBody | null>(null);
  const [route, setRoute] = useState({ origin: '', destination: '' });
  const onRouteChange = useCallback((origin: string, destination: string) => {
    setRoute({ origin, destination });
  }, []);

  // `/#planner` from elsewhere lands on the form, not the top of the page.
  useEffect(() => {
    if (hash === '#planner') document.getElementById('planner')?.scrollIntoView();
  }, [hash]);

  const runPlan = (body: PlanRequestBody) => {
    setBlocked(null);
    setFailure(null);
    setLastRequest(body);
    planTrip.mutate(body, {
      onSuccess: (result) => {
        if (isBlocked(result)) {
          setBlocked(result);
          return;
        }
        navigate(`/trip/${result.trip_id}`);
      },
      onError: (error) => {
        setFailure(describeApiError(error, t));
        setRetryable(isRetryable(error));
      },
    });
  };

  return (
    <div className="space-y-8">
      <section className="jm-hero grid items-center gap-6 p-6 sm:p-8 lg:grid-cols-[1.05fr_1fr]">
        <div className="jm-rise text-center lg:text-left">
          <span className="inline-flex items-center gap-2 rounded-full border border-line bg-surface/80 px-3 py-1 text-xs font-medium text-accent backdrop-blur">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent" aria-hidden="true" />
            {t('home.heroEyebrow')}
          </span>
          <h1 className="text-balance mt-4 text-3xl font-bold leading-tight text-ink sm:text-4xl lg:text-5xl">
            {t('home.heroTitle')}
          </h1>
          <p className="mx-auto mt-3 max-w-xl text-sm text-muted sm:text-base lg:mx-0">
            {t('home.heroSubtitle')}
          </p>
          <div className="mt-5 flex flex-wrap justify-center gap-2 lg:justify-start">
            <Button
              size="lg"
              onClick={() =>
                document.getElementById('planner')?.scrollIntoView({ behavior: 'smooth' })
              }
            >
              {t('home.heroCta')}
            </Button>
          </div>
        </div>
        <HeroFlight origin={route.origin} destination={route.destination} countries={countries} />
      </section>

      {failure ? (
        <Callout
          tone="danger"
          title={t('errors.title')}
          actions={
            retryable && lastRequest ? (
              <Button
                variant="secondary"
                size="sm"
                loading={planTrip.isPending}
                onClick={() => runPlan(lastRequest)}
              >
                {t('errors.retry')}
              </Button>
            ) : undefined
          }
        >
          {failure}
        </Callout>
      ) : null}

      <section id="planner" className="scroll-mt-24">
        <PlannerForm
          onSubmit={runPlan}
          submitting={planTrip.isPending}
          onRouteChange={onRouteChange}
          countries={countries}
        />
      </section>

      {blocked ? <GuardrailBlockedCard blocked={blocked} /> : null}

      {planTrip.isPending ? <PlanningProgress /> : null}

      <section>
        <h2 className="text-lg font-semibold text-ink">{t('home.howItWorksTitle')}</h2>
        <ol className="mt-3 grid gap-3 sm:grid-cols-3">
          <Step index={1} title={t('home.step1Title')} body={t('home.step1Body')} />
          <Step index={2} title={t('home.step2Title')} body={t('home.step2Body')} />
          <Step index={3} title={t('home.step3Title')} body={t('home.step3Body')} />
        </ol>
      </section>
    </div>
  );
}

export default HomePage;
