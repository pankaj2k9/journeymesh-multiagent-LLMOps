import { useTranslation } from 'react-i18next';

import { useLanguage } from '../../hooks/useLanguage';
import type { DaySlot, ItineraryPlan } from '../../types';
import { formatDate, formatMoney } from '../../utils/format';
import { Badge } from '../common/Badge';
import { EmptyState } from '../common/EmptyState';
import { Section } from '../common/Card';

interface ItinerarySectionProps {
  itinerary: ItineraryPlan;
}

function SlotBlock({ slot, currency }: { slot: DaySlot; currency?: string | null }) {
  const { t } = useTranslation();
  const { language } = useLanguage();

  return (
    <div className="border-l-2 border-accent/35 pl-4">
      <p className="text-xs font-semibold uppercase tracking-wide text-accent">
        {t(`itinerary.${slot.slot}`)}
      </p>
      <ul className="mt-1.5 space-y-2">
        {slot.activities.map((activity, index) => (
          <li key={`${activity.title}-${index}`}>
            <p className="text-sm font-medium text-ink">{activity.title}</p>
            {activity.description ? (
              <p className="text-xs text-muted">{activity.description}</p>
            ) : null}
            <p className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-muted">
              {activity.duration_minutes ? (
                <span>{t('itinerary.duration', { minutes: activity.duration_minutes })}</span>
              ) : null}
              {activity.estimated_cost ? (
                <span>{formatMoney(activity.estimated_cost, currency, language)}</span>
              ) : null}
              {activity.indoor ? <Badge tone="muted">indoor</Badge> : null}
            </p>
          </li>
        ))}
      </ul>
      {slot.notes ? <p className="mt-1.5 text-xs text-muted">{slot.notes}</p> : null}
    </div>
  );
}

export function ItinerarySection({ itinerary }: ItinerarySectionProps) {
  const { t } = useTranslation();
  const { language } = useLanguage();

  return (
    <Section
      id="itinerary"
      title={t('trip.itinerary')}
      description={
        itinerary.days.length
          ? t('itinerary.pacing', { value: t(`itinerary.pacingValues.${itinerary.pacing}`) })
          : undefined
      }
    >
      {itinerary.days.length === 0 ? (
        <EmptyState message={t('itinerary.empty')} />
      ) : (
        <ol className="grid gap-3 sm:grid-cols-2">
          {itinerary.days.map((day) => (
            <li key={day.day} className="flex flex-col rounded-xl border border-line p-4">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <h3 className="text-sm font-semibold text-ink">
                  {t('itinerary.day', { number: day.day })}
                  {day.title ? <span className="ml-2 font-normal">{day.title}</span> : null}
                </h3>
                <span className="text-xs text-muted">
                  {formatDate(day.date, language)}
                </span>
              </div>

              {day.weather_note ? (
                <p className="mt-1 text-xs text-muted">{day.weather_note}</p>
              ) : null}

              <div className="mt-3 space-y-3">
                {day.slots.map((slot) => (
                  <SlotBlock key={slot.slot} slot={slot} currency={itinerary.currency} />
                ))}
              </div>

              {/* Pushed to the bottom so the cost line sits on the card's
                  edge whichever column a day lands in, and two days of
                  different lengths still line up. */}
              <div className="mt-auto flex flex-wrap items-center gap-3 pt-3 text-xs text-muted">
                {day.estimated_day_cost ? (
                  <span>
                    {t('itinerary.dayCost', {
                      amount: formatMoney(day.estimated_day_cost, itinerary.currency, language),
                    })}
                  </span>
                ) : null}
                {day.rest_note ? <span>{day.rest_note}</span> : null}
              </div>
            </li>
          ))}
        </ol>
      )}

      {itinerary.notes.length ? (
        <ul className="mt-3 space-y-1 text-xs text-muted">
          {itinerary.notes.map((note) => (
            <li key={note}>• {note}</li>
          ))}
        </ul>
      ) : null}
    </Section>
  );
}
