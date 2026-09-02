import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import { Badge } from '../components/common/Badge';
import { Button } from '../components/common/Button';
import { Callout } from '../components/common/Callout';
import { Card } from '../components/common/Card';
import { EmptyState } from '../components/common/EmptyState';
import { Spinner } from '../components/common/Spinner';
import { StatusBadge } from '../components/trip/StatusBadge';
import { useLanguage } from '../hooks/useLanguage';
import { useDeleteTrip, useTripList } from '../hooks/useTrips';
import { formatDate, formatMoney } from '../utils/format';

export function HistoryPage() {
  const { t } = useTranslation();
  const { language } = useLanguage();
  const { data, isLoading, isError, refetch } = useTripList({ limit: 50 });
  const remove = useDeleteTrip();

  if (isLoading) return <Spinner label={t('common.loading')} />;

  if (isError) {
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

  const items = data?.items ?? [];

  return (
    <div className="space-y-5">
      <header>
        <h1 className="text-xl font-semibold text-ink sm:text-2xl">{t('history.title')}</h1>
        <p className="mt-1 text-sm text-muted">{t('history.subtitle')}</p>
      </header>

      {items.length === 0 ? (
        <EmptyState
          message={t('history.empty')}
          action={
            <Link to="/">
              <Button>{t('history.emptyAction')}</Button>
            </Link>
          }
        />
      ) : (
        <ul className="space-y-3">
          {items.map((trip) => (
            <li key={trip.trip_id}>
              <Card className="flex flex-wrap items-center justify-between gap-3 p-4">
                <div className="min-w-0">
                  <p className="truncate text-sm font-semibold text-ink">
                    {[trip.origin, trip.destination].filter(Boolean).join(' → ') ||
                      trip.destination ||
                      trip.trip_id.slice(0, 8)}
                  </p>
                  <p className="mt-0.5 text-xs text-muted">
                    {t('history.created', { date: formatDate(trip.created_at, language) })} ·{' '}
                    {t('trip.travellers', { count: trip.travelers })} ·{' '}
                    {formatMoney(trip.budget, trip.currency, language)}
                  </p>
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  <StatusBadge status={trip.review_status} />
                  {trip.evaluation_score !== null && trip.evaluation_score !== undefined ? (
                    <Badge tone="neutral">{Math.round(trip.evaluation_score * 100)}%</Badge>
                  ) : null}
                  <Link to={`/trip/${trip.trip_id}`}>
                    <Button size="sm" variant="secondary">
                      {t('history.open')}
                    </Button>
                  </Link>
                  <Button
                    size="sm"
                    variant="danger"
                    loading={remove.isPending && remove.variables === trip.trip_id}
                    onClick={() => {
                      if (window.confirm(t('history.deleteConfirm'))) {
                        remove.mutate(trip.trip_id);
                      }
                    }}
                  >
                    {t('history.delete')}
                  </Button>
                </div>
              </Card>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default HistoryPage;
