import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import type { BadgeTone } from '../common/Badge';
import { Badge } from '../common/Badge';
import { Button } from '../common/Button';
import { Card } from '../common/Card';
import { ProgressBar } from '../common/ProgressBar';
import { useLanguage } from '../../hooks/useLanguage';
import type { BudgetVerdict, TripCard } from '../../types';
import { formatDate } from '../../utils/format';
import { barPercent, formatMoneyString } from '../../utils/money';

const VERDICT_TONE: Record<BudgetVerdict, BadgeTone> = {
  within_budget: 'positive',
  near_limit: 'caution',
  over_budget: 'negative',
  no_budget_set: 'muted',
};

/**
 * One journey on the dashboard.
 *
 * Everything shown is read from the card the API sent. The percentages, the
 * verdict and the arrangement progress are computed server-side by the
 * services that own those definitions, so this component formats and never
 * calculates - which is why it cannot drift from the trip's own budget page.
 */
export function TripCardView({ trip }: { trip: TripCard }) {
  const { t } = useTranslation();
  const { language } = useLanguage();

  const route =
    [trip.origin, trip.destination].filter(Boolean).join(' → ') ||
    trip.destination ||
    t('dashboard.untitledTrip');

  const budgetTone = VERDICT_TONE[trip.budget.verdict];
  const used = trip.budget.percentage_used;

  return (
    <Card className="flex h-full flex-col gap-4 p-4 sm:p-5">
      <header className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="truncate text-base font-semibold text-ink">{route}</h3>
          <p className="mt-0.5 text-xs text-muted">
            {trip.departure_date
              ? `${formatDate(trip.departure_date, language)}${
                  trip.return_date ? ` – ${formatDate(trip.return_date, language)}` : ''
                }`
              : t('dashboard.noDatesYet')}
            {' · '}
            {t('trip.travellers', { count: trip.travelers })}
          </p>
        </div>
        <Countdown days={trip.days_until_departure} bucket={trip.bucket} />
      </header>

      <div className="space-y-3">
        <div>
          <div className="flex items-baseline justify-between gap-2 text-xs">
            <span className="font-medium text-muted">{t('dashboard.budget')}</span>
            <span className="tabular-nums text-ink">
              {trip.budget.total_budget === null
                ? t('dashboard.noBudget')
                : t('dashboard.remainingOf', {
                    remaining: formatMoneyString(
                      trip.budget.remaining_budget,
                      trip.budget.currency,
                      language,
                    ),
                    total: formatMoneyString(
                      trip.budget.total_budget,
                      trip.budget.currency,
                      language,
                    ),
                  })}
            </span>
          </div>
          {used !== null ? (
            <ProgressBar
              className="mt-1.5"
              value={barPercent(used)}
              tone={budgetTone}
              label={t('dashboard.budgetUsedLabel')}
              valueText={t('dashboard.percentUsed', { percent: Math.round(used) })}
            />
          ) : null}
        </div>

        <div>
          <div className="flex items-baseline justify-between gap-2 text-xs">
            <span className="font-medium text-muted">{t('dashboard.arranged')}</span>
            <span className="tabular-nums text-ink">{trip.booking.percent}%</span>
          </div>
          <ProgressBar
            className="mt-1.5"
            value={trip.booking.percent}
            tone="brand"
            label={t('dashboard.arrangedLabel')}
          />
          <div className="mt-2 flex flex-wrap gap-1.5">
            <Badge tone={trip.booking.flight_selected ? 'positive' : 'muted'}>
              ✈︎ {t('dashboard.flights')}
            </Badge>
            <Badge tone={trip.booking.hotel_selected ? 'positive' : 'muted'}>
              ⌂ {t('dashboard.stay')}
            </Badge>
            {trip.booking.activity_count > 0 ? (
              <Badge tone="positive">
                ★ {t('dashboard.activityCount', { count: trip.booking.activity_count })}
              </Badge>
            ) : null}
          </div>
        </div>
      </div>

      {trip.next_item ? (
        <p className="rounded-xl bg-elevated px-3 py-2 text-xs text-muted">
          <span className="font-medium text-ink">{t('dashboard.next')}: </span>
          {trip.next_item.title}
        </p>
      ) : null}

      <footer className="mt-auto flex flex-wrap items-center gap-2 pt-1">
        <Link to={`/trip/${trip.trip_id}`}>
          <Button size="sm" variant="secondary">
            {t('dashboard.open')}
          </Button>
        </Link>
        <Link to={`/trip/${trip.trip_id}?tab=budget`}>
          <Button size="sm" variant="ghost">
            {t('dashboard.openBudget')}
          </Button>
        </Link>
        <Link to={`/trip/${trip.trip_id}?print=1`}>
          <Button size="sm" variant="ghost">
            {t('dashboard.downloadPdf')}
          </Button>
        </Link>
      </footer>
    </Card>
  );
}

function Countdown({ days, bucket }: { days: number | null; bucket: string }) {
  const { t } = useTranslation();
  if (bucket === 'past') {
    return <Badge tone="muted">{t('dashboard.completed')}</Badge>;
  }
  if (days === null) {
    return <Badge tone="muted">{t('dashboard.draft')}</Badge>;
  }
  if (days === 0) {
    return <Badge tone="brand">{t('dashboard.departsToday')}</Badge>;
  }
  if (days < 0) {
    return <Badge tone="muted">{t('dashboard.completed')}</Badge>;
  }
  return (
    <Badge tone={days <= 14 ? 'caution' : 'neutral'}>
      {t('dashboard.inDays', { count: days })}
    </Badge>
  );
}
