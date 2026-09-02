import { useTranslation } from 'react-i18next';

import { useLanguage } from '../../hooks/useLanguage';
import type { TripConstraints, TripPlanResponse } from '../../types';
import { formatDate, formatMoney } from '../../utils/format';
import { AGENT_LABELS } from '../../utils/constants';
import { Badge } from '../common/Badge';
import { Card } from '../common/Card';
import { StatusBadge } from './StatusBadge';

interface JourneyOverviewCardProps {
  trip: TripPlanResponse;
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wide text-journey-slate">{label}</dt>
      <dd className="mt-0.5 text-sm font-medium text-journey-ink">{value}</dd>
    </div>
  );
}

export function JourneyOverviewCard({ trip }: JourneyOverviewCardProps) {
  const { t } = useTranslation();
  const { language } = useLanguage();
  const constraints: TripConstraints = trip.constraints;
  const overview = trip.final_journey?.overview;

  const title =
    overview?.title ??
    [constraints.origin, constraints.destination].filter(Boolean).join(' → ') ??
    t('trip.overview');

  return (
    <Card className="p-5 sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-journey-ink sm:text-2xl">{title}</h1>
          {overview?.headline ? (
            <p className="mt-1 text-sm text-journey-slate">{overview.headline}</p>
          ) : null}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge status={trip.review_status} />
          <Badge tone="brand">{t('trip.revision', { count: trip.revision })}</Badge>
        </div>
      </div>

      <dl className="mt-5 grid grid-cols-2 gap-4 sm:grid-cols-4">
        <Detail label={t('planner.origin')} value={constraints.origin ?? '—'} />
        <Detail label={t('planner.destination')} value={constraints.destination ?? '—'} />
        <Detail
          label={t('planner.departureDate')}
          value={formatDate(constraints.departure_date, language)}
        />
        <Detail
          label={t('planner.returnDate')}
          value={formatDate(constraints.return_date, language)}
        />
        <Detail
          label={t('planner.travelers')}
          value={t('trip.travellers', { count: constraints.travelers })}
        />
        <Detail
          label={t('planner.budget')}
          value={formatMoney(constraints.budget, constraints.currency, language)}
        />
        <Detail
          label={t('planner.travelStyle')}
          value={constraints.travel_style ? t(`styles.${constraints.travel_style}`) : '—'}
        />
        <Detail
          label={t('planner.interests')}
          value={
            constraints.interests.length
              ? constraints.interests.map((item) => t(`interests.${item}`)).join(', ')
              : '—'
          }
        />
      </dl>

      {trip.selected_agents.length ? (
        <div className="mt-5 border-t border-slate-100 pt-4">
          <p className="text-xs uppercase tracking-wide text-journey-slate">{t('trip.agents')}</p>
          <div className="mt-2 flex flex-wrap gap-2">
            {trip.selected_agents.map((agent) => (
              <Badge key={agent} tone="neutral">
                {AGENT_LABELS[agent] ?? agent}
              </Badge>
            ))}
          </div>
          {trip.execution_reason ? (
            <p className="mt-2 text-sm text-journey-slate">{trip.execution_reason}</p>
          ) : null}
        </div>
      ) : null}
    </Card>
  );
}
