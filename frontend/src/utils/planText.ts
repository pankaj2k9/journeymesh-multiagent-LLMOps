import type { TripDetailResponse } from '../types';

/**
 * Render a journey as plain Markdown.
 *
 * One function feeds Copy and Download, so the two can never drift. It reads
 * the approved journey when there is one and the draft otherwise, and it
 * carries the provenance of each figure across - an estimate stays labelled as
 * an estimate outside the interface too.
 */

type Translate = (key: string, options?: Record<string, unknown>) => string;

function heading(text: string, level = 2): string {
  return `${'#'.repeat(level)} ${text}`;
}

function money(amount: number | null | undefined, currency: string | null | undefined): string {
  if (amount === null || amount === undefined) return '—';
  return `${currency ?? ''} ${Math.round(amount).toLocaleString()}`.trim();
}

export function buildPlanMarkdown(trip: TripDetailResponse, t: Translate): string {
  const journey = trip.final_journey;
  const constraints = trip.constraints;
  const flights = journey?.flights ?? trip.flights;
  const hotels = journey?.hotels ?? trip.hotels;
  const weather = journey?.weather ?? trip.weather;
  const budget = journey?.budget ?? trip.budget;
  const itinerary = journey?.itinerary ?? trip.itinerary;
  const tips = journey?.travel_tips?.length ? journey.travel_tips : itinerary.travel_tips;

  const approved = trip.review_status === 'approved';
  const lines: string[] = [];

  lines.push(
    heading(
      journey?.overview.title ??
        [constraints.origin, constraints.destination].filter(Boolean).join(' → ') ??
        t('trip.overview'),
      1,
    ),
  );
  lines.push('');
  lines.push(approved ? t('trip.finalTitle') : t('trip.draftTitle'));
  lines.push('');
  lines.push(`${t('trip.threadId')}: ${trip.trip_id}`);
  lines.push(`${t('trip.revision', { count: trip.revision })}`);
  lines.push('');

  // ---- Journey at a glance ------------------------------------------------
  lines.push(heading(t('trip.overview')));
  lines.push('');
  lines.push(`- ${t('planner.origin')}: ${constraints.origin ?? '—'}`);
  lines.push(`- ${t('planner.destination')}: ${constraints.destination ?? '—'}`);
  lines.push(`- ${t('planner.departureDate')}: ${constraints.departure_date ?? '—'}`);
  lines.push(`- ${t('planner.returnDate')}: ${constraints.return_date ?? '—'}`);
  lines.push(`- ${t('planner.travelers')}: ${constraints.travelers}`);
  lines.push(`- ${t('planner.budget')}: ${money(constraints.budget, constraints.currency)}`);
  lines.push('');

  // ---- Flights ------------------------------------------------------------
  if (flights.options.length) {
    lines.push(heading(t('trip.flights')));
    lines.push('');
    flights.options.forEach((option) => {
      const route = [option.origin_iata, option.destination_iata].filter(Boolean).join(' → ');
      const stops = option.stops === 0 ? t('flights.nonstop') : `${option.stops}`;
      lines.push(
        `- ${option.airline ?? '—'} ${route} · ${stops} · ` +
          `${money(option.price_per_traveler, option.currency)} (${option.price_source})`,
      );
    });
    lines.push('');
  }

  // ---- Hotels -------------------------------------------------------------
  if (hotels.options.length) {
    lines.push(heading(t('trip.hotels')));
    lines.push('');
    hotels.options.forEach((option) => {
      lines.push(
        `- ${option.name}${option.area ? `, ${option.area}` : ''} · ` +
          `${money(option.price_per_night, option.currency)} ${t('hotels.perNight')} ` +
          `(${option.price_source})`,
      );
    });
    lines.push('');
  }

  // ---- Weather ------------------------------------------------------------
  if (weather.forecast.length || weather.current) {
    lines.push(heading(t('trip.weather')));
    lines.push('');
    if (weather.current?.condition) {
      lines.push(`- ${t('weather.current')}: ${weather.current.condition}`);
    }
    weather.forecast.forEach((day) => {
      lines.push(
        `- ${day.date}: ${day.condition ?? '—'} ` +
          `${day.temp_min_c ?? '—'}–${day.temp_max_c ?? '—'}°C`,
      );
    });
    if (weather.packing_recommendations.length) {
      lines.push('');
      lines.push(`${t('weather.packing')}: ${weather.packing_recommendations.join(', ')}`);
    }
    lines.push('');
  }

  // ---- Budget -------------------------------------------------------------
  if (budget.estimated_total) {
    lines.push(heading(t('trip.budget')));
    lines.push('');
    lines.push(`- ${t('budgetPanel.total')}: ${money(budget.estimated_total, budget.currency)}`);
    lines.push(
      `- ${t(`budgetPanel.status.${budget.budget_status}`, {
        defaultValue: budget.budget_status,
      })}`,
    );
    lines.push(
      `- ${t('budgetPanel.confirmed')}: ${money(budget.confirmed_cost_total, budget.currency)}`,
    );
    lines.push(
      `- ${t('budgetPanel.estimated')}: ${money(budget.estimated_cost_total, budget.currency)}`,
    );
    lines.push('');
    lines.push(`${t('budgetPanel.breakdown')}:`);
    Object.entries(budget.breakdown).forEach(([key, value]) => {
      if (key === 'total') return;
      lines.push(
        `  - ${t(`budgetPanel.lines.${key}`, { defaultValue: key })}: ` +
          `${money(value, budget.currency)}`,
      );
    });
    lines.push('');
  }

  // ---- Itinerary ----------------------------------------------------------
  if (itinerary.days.length) {
    lines.push(heading(t('trip.itinerary')));
    lines.push('');
    itinerary.days.forEach((day) => {
      const dayLabel = t('itinerary.day', { number: day.day });
      lines.push(heading(`${dayLabel}${day.title ? ` — ${day.title}` : ''}`, 3));
      if (day.summary) lines.push(day.summary);
      day.slots.forEach((slot) => {
        if (!slot.activities.length) return;
        lines.push('');
        lines.push(`**${t(`itinerary.${slot.slot}`)}**`);
        slot.activities.forEach((activity) => {
          const where = activity.location ? ` (${activity.location})` : '';
          lines.push(`- ${activity.title}${where}`);
        });
      });
      lines.push('');
    });
  }

  // ---- Tips ---------------------------------------------------------------
  if (tips.length) {
    lines.push(heading(t('trip.tips')));
    lines.push('');
    tips.forEach((tip) => lines.push(`- ${tip}`));
    lines.push('');
  }

  if (journey?.closing_note) {
    lines.push(journey.closing_note);
    lines.push('');
  }

  return lines.join('\n').replace(/\n{3,}/g, '\n\n').trim() + '\n';
}

/** A filesystem-safe name for the downloaded plan. */
export function planFileName(trip: TripDetailResponse): string {
  const place = (trip.constraints.destination ?? 'journey')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '');
  const suffix = trip.review_status === 'approved' ? 'final' : 'draft';
  return `journeymesh-${place || 'journey'}-${suffix}.md`;
}
