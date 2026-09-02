import { useTranslation } from 'react-i18next';

import { useLanguage } from '../../hooks/useLanguage';
import type { FlightResults } from '../../types';
import { formatMoney } from '../../utils/format';
import { Badge } from '../common/Badge';
import { EmptyState } from '../common/EmptyState';
import { Section } from '../common/Card';
import { SourceBadge } from '../common/SourceBadge';

interface FlightsSectionProps {
  flights: FlightResults;
}

export function FlightsSection({ flights }: FlightsSectionProps) {
  const { t } = useTranslation();
  const { language } = useLanguage();

  return (
    <Section
      id="flights"
      title={t('trip.flights')}
      actions={<SourceBadge source={flights.source} />}
    >
      {flights.options.length === 0 ? (
        <EmptyState message={t('flights.empty')} />
      ) : (
        <div className="space-y-3">
          {flights.cheapest_total ? (
            <p className="text-sm text-muted">
              {t('flights.cheapestTotal')}:{' '}
              <span className="font-semibold text-ink">
                {formatMoney(flights.cheapest_total, flights.currency, language)}
              </span>
            </p>
          ) : null}

          <div className="overflow-x-auto">
            <table className="w-full min-w-[34rem] border-collapse text-sm">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wide text-muted">
                  <th className="pb-2 pr-3 font-medium">{t('flights.airline')}</th>
                  <th className="pb-2 pr-3 font-medium">{t('flights.route')}</th>
                  <th className="pb-2 pr-3 font-medium">{t('flights.stops')}</th>
                  <th className="pb-2 font-medium">{t('flights.pricePerTraveller')}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {flights.options.map((option, index) => (
                  <tr key={`${option.airline}-${index}`} className="align-top">
                    <td className="py-3 pr-3">
                      <p className="font-medium text-ink">{option.airline ?? '—'}</p>
                      {option.flight_number ? (
                        <p className="text-xs text-muted">{option.flight_number}</p>
                      ) : null}
                    </td>
                    <td className="py-3 pr-3 text-muted">
                      {[option.origin_iata, option.destination_iata].filter(Boolean).join(' → ') ||
                        '—'}
                    </td>
                    <td className="py-3 pr-3 text-muted">
                      {option.stops === 0
                        ? t('flights.nonstop')
                        : t('flights.stops', { count: option.stops })}
                    </td>
                    <td className="py-3">
                      {option.price_per_traveler ? (
                        <span className="flex flex-wrap items-center gap-2">
                          <span className="font-semibold text-ink">
                            {formatMoney(option.price_per_traveler, option.currency, language)}
                          </span>
                          <SourceBadge source={option.price_source} />
                        </span>
                      ) : (
                        <Badge tone="muted">{t('flights.noPrice')}</Badge>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {flights.notes.length ? (
            <ul className="space-y-1 text-xs text-muted">
              {flights.notes.map((note) => (
                <li key={note}>• {note}</li>
              ))}
            </ul>
          ) : null}
        </div>
      )}
    </Section>
  );
}
