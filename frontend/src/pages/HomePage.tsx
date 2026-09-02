import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';

import { ApiError } from '../api/client';
import { Callout } from '../components/common/Callout';
import { PlannerForm } from '../components/planner/PlannerForm';
import { usePlanTrip } from '../hooks/useTrips';
import type { GuardrailBlockedResponse, PlanRequestBody } from '../types';
import { isBlocked } from '../types';

function Step({ title, body, index }: { title: string; body: string; index: number }) {
  return (
    <li className="rounded-2xl border border-slate-200 bg-white p-4">
      <span className="inline-flex h-7 w-7 items-center justify-center rounded-full bg-mesh-50 text-sm font-semibold text-mesh-700">
        {index}
      </span>
      <h3 className="mt-3 text-sm font-semibold text-journey-ink">{title}</h3>
      <p className="mt-1 text-sm text-journey-slate">{body}</p>
    </li>
  );
}

export function HomePage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const planTrip = usePlanTrip();
  const [blocked, setBlocked] = useState<GuardrailBlockedResponse | null>(null);
  const [failure, setFailure] = useState<string | null>(null);

  const handleSubmit = (body: PlanRequestBody) => {
    setBlocked(null);
    setFailure(null);
    planTrip.mutate(body, {
      onSuccess: (result) => {
        if (isBlocked(result)) {
          setBlocked(result);
          return;
        }
        navigate(`/trip/${result.trip_id}`);
      },
      onError: (error) => {
        if (error instanceof ApiError) {
          if (error.isRateLimited) {
            setFailure(t('errors.rateLimited'));
            return;
          }
          if (error.code === 'network_error') {
            setFailure(t('errors.network'));
            return;
          }
          setFailure(error.message || t('errors.title'));
          return;
        }
        setFailure(t('errors.title'));
      },
    });
  };

  return (
    <div className="space-y-8">
      <section className="text-center sm:text-left">
        <h1 className="text-2xl font-semibold text-journey-ink sm:text-3xl">
          {t('home.heroTitle')}
        </h1>
        <p className="mx-auto mt-2 max-w-2xl text-sm text-journey-slate sm:mx-0 sm:text-base">
          {t('home.heroSubtitle')}
        </p>
      </section>

      {blocked ? (
        <Callout tone="warning" title={t('errors.blocked')}>
          <p>{blocked.message}</p>
          {blocked.guidance ? <p className="mt-1">{blocked.guidance}</p> : null}
        </Callout>
      ) : null}

      {failure ? (
        <Callout tone="danger" title={t('errors.title')}>
          {failure}
        </Callout>
      ) : null}

      <PlannerForm onSubmit={handleSubmit} submitting={planTrip.isPending} />

      <section>
        <h2 className="text-lg font-semibold text-journey-ink">{t('home.howItWorksTitle')}</h2>
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
