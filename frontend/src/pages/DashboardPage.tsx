import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import { Button } from '../components/common/Button';
import { Callout } from '../components/common/Callout';
import { Card } from '../components/common/Card';
import { EmptyState } from '../components/common/EmptyState';
import { SkeletonCard } from '../components/common/Skeleton';
import { StatCard } from '../components/common/StatCard';
import { TripCardView } from '../components/dashboard/TripCardView';
import { useAuth } from '../auth/useAuth';
import { useDashboard } from '../hooks/useDashboard';
import type { TripCard } from '../types';

export function DashboardPage() {
  const { t } = useTranslation();
  const { user, signedIn } = useAuth();
  const { data, isLoading, isError, refetch } = useDashboard();

  if (isLoading) {
    return (
      <div className="space-y-4" role="status" aria-label={t('common.loading')}>
        <SkeletonCard />
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
        </div>
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="space-y-3">
        <Callout tone="danger" title={t('errors.title')}>
          {t('errors.network')}
        </Callout>
        <Button variant="secondary" onClick={() => void refetch()}>
          {t('errors.retry')}
        </Button>
      </div>
    );
  }

  const nothingYet = data.counts.total === 0;

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-ink sm:text-2xl">
            {signedIn
              ? t('dashboard.welcomeBack', {
                  name: user?.display_name || user?.email?.split('@')[0],
                })
              : t('dashboard.welcome')}
          </h1>
          <p className="mt-1 text-sm text-muted">{t('dashboard.subtitle')}</p>
        </div>
        <Link to="/">
          <Button>{t('dashboard.planNew')}</Button>
        </Link>
      </header>

      <div className="grid gap-3 sm:grid-cols-3">
        <StatCard label={t('dashboard.upcoming')} value={String(data.counts.upcoming)} icon="✈︎" />
        <StatCard label={t('dashboard.drafts')} value={String(data.counts.drafts)} icon="✎" />
        <StatCard label={t('dashboard.past')} value={String(data.counts.past)} icon="✓" />
      </div>

      {nothingYet ? (
        <EmptyState
          message={t('dashboard.empty')}
          action={
            <Link to="/">
              <Button>{t('dashboard.planFirst')}</Button>
            </Link>
          }
        />
      ) : (
        <>
          <TripGroup title={t('dashboard.upcomingTrips')} trips={data.upcoming} />
          <TripGroup title={t('dashboard.draftTrips')} trips={data.drafts} />
          <TripGroup title={t('dashboard.pastTrips')} trips={data.past} collapsedByDefault />
        </>
      )}

      {/* Both arrive in a later phase. Rendered as quiet placeholders so the
          dashboard's shape is already the shape it will keep. */}
      <div className="grid gap-3 lg:grid-cols-2">
        <Card className="p-4">
          <h2 className="text-sm font-semibold text-ink">{t('dashboard.priceWatches')}</h2>
          <p className="mt-1 text-xs text-muted">{t('dashboard.comingSoon')}</p>
        </Card>
        <Card className="p-4">
          <h2 className="text-sm font-semibold text-ink">{t('dashboard.notifications')}</h2>
          <p className="mt-1 text-xs text-muted">{t('dashboard.comingSoon')}</p>
        </Card>
      </div>
    </div>
  );
}

function TripGroup({
  title,
  trips,
  collapsedByDefault = false,
}: {
  title: string;
  trips: TripCard[];
  collapsedByDefault?: boolean;
}) {
  if (trips.length === 0) return null;

  const body = (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
      {trips.map((trip) => (
        <TripCardView key={trip.trip_id} trip={trip} />
      ))}
    </div>
  );

  if (collapsedByDefault) {
    return (
      <details className="group">
        <summary className="cursor-pointer list-none py-2 text-sm font-semibold text-ink">
          <span className="inline-flex items-center gap-2">
            <span aria-hidden="true" className="text-muted transition group-open:rotate-90">
              ›
            </span>
            {title} ({trips.length})
          </span>
        </summary>
        <div className="pt-2">{body}</div>
      </details>
    );
  }

  return (
    <section className="space-y-3">
      <h2 className="text-sm font-semibold text-ink">
        {title} <span className="text-muted">({trips.length})</span>
      </h2>
      {body}
    </section>
  );
}

export default DashboardPage;
