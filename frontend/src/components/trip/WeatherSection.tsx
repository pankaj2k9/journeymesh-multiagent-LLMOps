import { useTranslation } from 'react-i18next';

import type { WeatherInfo } from '../../types';
import { formatPercent, formatTemperature } from '../../utils/format';
import { EmptyState } from '../common/EmptyState';
import { Section } from '../common/Card';
import { SourceBadge } from '../common/SourceBadge';

interface WeatherSectionProps {
  weather: WeatherInfo;
}

export function WeatherSection({ weather }: WeatherSectionProps) {
  const { t } = useTranslation();
  const hasData = Boolean(weather.current) || weather.forecast.length > 0;

  return (
    <Section
      id="weather"
      title={t('trip.weather')}
      actions={<SourceBadge source={weather.source} />}
    >
      {!hasData ? (
        <EmptyState message={t('weather.empty')} />
      ) : (
        <div className="space-y-4">
          {weather.current ? (
            <div className="rounded-xl bg-slate-50 px-4 py-3">
              <p className="text-xs uppercase tracking-wide text-journey-slate">
                {t('weather.current')}
              </p>
              <p className="mt-1 text-lg font-semibold text-journey-ink">
                {formatTemperature(weather.current.temperature_c)}{' '}
                <span className="text-sm font-normal text-journey-slate">
                  {weather.current.condition}
                </span>
              </p>
              <p className="text-xs text-journey-slate">
                {t('weather.humidity')}: {formatPercent(weather.current.humidity_pct)}
              </p>
            </div>
          ) : null}

          {weather.forecast.length ? (
            <div className="overflow-x-auto">
              <ul className="flex gap-3">
                {weather.forecast.map((day) => (
                  <li
                    key={day.date}
                    className="min-w-[9rem] flex-1 rounded-xl border border-slate-200 px-3 py-3"
                  >
                    <p className="text-xs font-medium text-journey-slate">{day.date}</p>
                    <p className="mt-1 text-sm font-semibold text-journey-ink">
                      {formatTemperature(day.temp_max_c)} / {formatTemperature(day.temp_min_c)}
                    </p>
                    <p className="mt-1 text-xs text-journey-slate">{day.condition}</p>
                    <p className="mt-1 text-xs text-journey-slate">
                      {t('weather.rainChance')}: {formatPercent(day.precipitation_chance_pct)}
                    </p>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          <div className="grid gap-4 sm:grid-cols-2">
            {weather.packing_recommendations.length ? (
              <div>
                <h3 className="text-sm font-semibold text-journey-ink">{t('weather.packing')}</h3>
                <ul className="mt-2 space-y-1 text-sm text-journey-slate">
                  {weather.packing_recommendations.map((item) => (
                    <li key={item}>• {item}</li>
                  ))}
                </ul>
              </div>
            ) : null}
            {weather.travel_suggestions.length ? (
              <div>
                <h3 className="text-sm font-semibold text-journey-ink">
                  {t('weather.suggestions')}
                </h3>
                <ul className="mt-2 space-y-1 text-sm text-journey-slate">
                  {weather.travel_suggestions.map((item) => (
                    <li key={item}>• {item}</li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>

          {weather.notes.length ? (
            <ul className="space-y-1 text-xs text-journey-slate">
              {weather.notes.map((note) => (
                <li key={note}>• {note}</li>
              ))}
            </ul>
          ) : null}
        </div>
      )}
    </Section>
  );
}
