import { useTranslation } from 'react-i18next';

import { useLanguage } from '../../hooks/useLanguage';
import type { HotelResults } from '../../types';
import { formatMoney } from '../../utils/format';
import { Badge } from '../common/Badge';
import { EmptyState } from '../common/EmptyState';
import { Section } from '../common/Card';
import { SourceBadge } from '../common/SourceBadge';

interface HotelsSectionProps {
  hotels: HotelResults;
}

export function HotelsSection({ hotels }: HotelsSectionProps) {
  const { t } = useTranslation();
  const { language } = useLanguage();

  return (
    <Section
      id="hotels"
      title={t('trip.hotels')}
      description={
        hotels.price_ceiling_per_night
          ? t('hotels.priceCeiling', {
              amount: formatMoney(hotels.price_ceiling_per_night, hotels.currency, language),
            })
          : undefined
      }
      actions={<SourceBadge source={hotels.source} />}
    >
      {hotels.options.length === 0 ? (
        <EmptyState message={t('hotels.empty')} />
      ) : (
        <ul className="grid gap-3 sm:grid-cols-2">
          {hotels.options.map((hotel, index) => (
            <li
              key={`${hotel.name}-${index}`}
              className={`rounded-xl border p-4 ${
                index === hotels.recommended_index
                  ? 'border-accent/45 bg-accent-soft/60'
                  : 'border-line'
              }`}
            >
              <div className="flex items-start justify-between gap-2">
                <h3 className="text-sm font-semibold text-ink">{hotel.name}</h3>
                {index === hotels.recommended_index ? (
                  <Badge tone="brand">{t('hotels.recommended')}</Badge>
                ) : null}
              </div>

              <div className="mt-2 flex flex-wrap items-center gap-2 text-sm">
                {hotel.price_per_night ? (
                  <>
                    <span className="font-semibold text-ink">
                      {formatMoney(hotel.price_per_night, hotel.currency, language)}
                    </span>
                    <span className="text-muted">{t('hotels.perNight')}</span>
                    <SourceBadge source={hotel.price_source} />
                  </>
                ) : (
                  <Badge tone="muted">{t('flights.noPrice')}</Badge>
                )}
              </div>

              <dl className="mt-3 space-y-1 text-xs text-muted">
                {hotel.rating ? (
                  <div>
                    <dt className="inline font-medium">{t('hotels.rating')}: </dt>
                    <dd className="inline">{hotel.rating}</dd>
                  </div>
                ) : null}
                {hotel.distance_to_centre_km !== null &&
                hotel.distance_to_centre_km !== undefined ? (
                  <div>{t('hotels.distance', { km: hotel.distance_to_centre_km })}</div>
                ) : null}
                {hotel.family_friendly ? <div>{t('hotels.familyFriendly')}</div> : null}
              </dl>

              {hotel.amenities.length ? (
                <p className="mt-2 text-xs text-muted">
                  <span className="font-medium">{t('hotels.amenities')}: </span>
                  {hotel.amenities.join(', ')}
                </p>
              ) : null}

              {hotel.why_recommended ? (
                <p className="mt-2 text-xs text-muted">{hotel.why_recommended}</p>
              ) : null}

              {hotel.reference_url ? (
                <a
                  className="mt-2 inline-block text-xs text-accent underline-offset-2 hover:underline"
                  href={hotel.reference_url}
                  target="_blank"
                  rel="noreferrer noopener"
                >
                  {hotel.reference_url.replace(/^https?:\/\//, '').slice(0, 40)}
                </a>
              ) : null}
            </li>
          ))}
        </ul>
      )}

      {hotels.notes.length ? (
        <ul className="mt-3 space-y-1 text-xs text-muted">
          {hotels.notes.map((note) => (
            <li key={note}>• {note}</li>
          ))}
        </ul>
      ) : null}
    </Section>
  );
}
