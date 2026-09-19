import { useTranslation } from 'react-i18next';

import { useLanguage } from '../../hooks/useLanguage';
import type { RoutePlan, TransportMode, TransportOption } from '../../types';
import { formatMoney } from '../../utils/format';
import { Badge } from '../common/Badge';
import { Section } from '../common/Card';
import { SourceBadge } from '../common/SourceBadge';

export const MODE_ICON: Record<TransportMode, string> = {
  flight: '✈️',
  train: '🚆',
  bus: '🚌',
  car: '🚗',
  cng: '🛺',
  auto_rickshaw: '🛺',
  tuk_tuk: '🛺',
  rickshaw: '🚲',
  taxi: '🚕',
  ferry: '⛴️',
};

function hours(value: number, t: (key: string, options?: Record<string, unknown>) => string) {
  const whole = Math.floor(value);
  const minutes = Math.round((value - whole) * 60);
  if (whole === 0) return t('transport.minutes', { count: minutes });
  return minutes
    ? t('transport.hoursMinutes', { hours: whole, minutes })
    : t('transport.hours', { count: whole });
}

function OptionCard({ option, plan }: { option: TransportOption; plan: RoutePlan }) {
  const { t } = useTranslation();
  const { language } = useLanguage();
  const money = (value: number) => formatMoney(value, plan.currency, language);

  return (
    <li
      className={`rounded-2xl border p-4 ${
        option.recommended
          ? 'border-accent bg-accent-soft/40 shadow-card'
          : 'border-line bg-surface'
      }`}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="flex items-center gap-2 font-semibold text-ink">
            <span aria-hidden="true">{MODE_ICON[option.main_mode]}</span>
            {t(`transport.modes.${option.main_mode}`)}
            {option.recommended ? <Badge tone="brand">{t('transport.recommended')}</Badge> : null}
          </p>
          {option.reason && option.recommended ? (
            <p className="mt-0.5 text-xs text-muted">{option.reason}</p>
          ) : null}
        </div>
        <div className="text-right">
          <p className="text-base font-semibold text-ink">{money(option.one_way_per_traveler)}</p>
          <p className="text-xs text-muted">{t('transport.perTravellerOneWay')}</p>
        </div>
      </div>

      {/* The legs, in order: a flight and the bus after it, or a road and a ferry. */}
      <ol className="mt-3 space-y-1.5">
        {option.legs.map((leg, index) => (
          <li key={index} className="flex flex-wrap items-center gap-x-2 text-sm">
            <span aria-hidden="true">{MODE_ICON[leg.mode]}</span>
            <span className="text-ink">
              {t(`transport.modes.${leg.mode}`)}: {leg.from_place} → {leg.to_place}
            </span>
            <span className="text-xs text-muted">
              ~{leg.distance_km} km · {hours(leg.duration_hours, t)} ·{' '}
              {money(leg.cost_per_traveler)}
              {leg.vehicles && leg.vehicles > 1
                ? ` · ${t('transport.vehicles', { count: leg.vehicles })}`
                : ''}
            </span>
          </li>
        ))}
      </ol>

      <p className="mt-3 border-t border-line pt-2 text-xs text-muted">
        {hours(option.duration_hours, t)} · ~{option.distance_km} km ·{' '}
        <span className="font-medium text-ink">
          {plan.round_trip
            ? t('transport.returnTotal', {
                amount: money(option.trip_total_for_group),
                count: plan.travelers,
              })
            : t('transport.oneWayTotal', {
                amount: money(option.trip_total_for_group),
                count: plan.travelers,
              })}
        </span>
      </p>
    </li>
  );
}

/** Every way to get there, best first, with the recommended one highlighted. */
export function GettingThere({ plan }: { plan: RoutePlan | null | undefined }) {
  const { t } = useTranslation();
  if (!plan || (plan.options.length === 0 && plan.notes.length === 0)) return null;

  return (
    <Section title={t('transport.title')} actions={<SourceBadge source={plan.source} />}>
      {plan.options.length > 0 ? (
        <ul className="grid gap-3 lg:grid-cols-2">
          {plan.options.map((option, index) => (
            <OptionCard key={`${option.main_mode}-${index}`} option={option} plan={plan} />
          ))}
        </ul>
      ) : null}
      {plan.notes.length > 0 ? (
        <ul className="mt-3 space-y-1 text-xs text-muted">
          {plan.notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      ) : null}
    </Section>
  );
}
