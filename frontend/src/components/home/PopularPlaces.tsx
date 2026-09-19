import { useTranslation } from 'react-i18next';

import type { Attraction } from '../../api/places';

interface PopularPlacesProps {
  places: Attraction[];
  onPlan: (place: Attraction) => void;
}

/** A row of large photographs; each one starts a plan for that place. */
export function PopularPlaces({ places, onPlan }: PopularPlacesProps) {
  const { t } = useTranslation();
  if (places.length === 0) return null;

  return (
    <section aria-labelledby="popular-places" className="space-y-3">
      <h2 id="popular-places" className="text-lg font-semibold text-ink">
        {t('home.popularTitle')}
      </h2>
      <ul className="grid gap-4 sm:grid-cols-3">
        {places.map((place, index) => (
          <li key={place.slug} className="jm-rise" style={{ animationDelay: `${index * 90}ms` }}>
            <figure className="group relative overflow-hidden rounded-2xl border border-line shadow-card">
              {place.image ? (
                <img
                  src={place.image.card_url}
                  alt={place.name}
                  loading="lazy"
                  className="aspect-[4/3] w-full bg-elevated object-cover transition duration-700 group-hover:scale-105"
                />
              ) : (
                <div className="jm-hero aspect-[4/3] w-full rounded-none border-0 shadow-none" />
              )}
              {/* A scrim keeps white text legible on any photograph, in either theme. */}
              <div
                className="pointer-events-none absolute inset-0 bg-gradient-to-t from-canvas/95 via-canvas/20 to-transparent"
                aria-hidden="true"
              />
              <figcaption className="absolute inset-x-0 bottom-0 space-y-2 p-4">
                <div>
                  <p className="text-base font-semibold text-ink">{place.name}</p>
                  <p className="text-xs text-muted">
                    {place.city}, {place.country}
                  </p>
                </div>
                <div className="flex items-end justify-between gap-2">
                  <button
                    type="button"
                    onClick={() => onPlan(place)}
                    className="rounded-lg bg-accent px-3 py-1.5 text-xs font-semibold text-accent-contrast shadow-card transition hover:bg-accent-strong"
                  >
                    {t('home.planHere')}
                  </button>
                  {place.image ? (
                    <a
                      href={place.image.source_url}
                      target="_blank"
                      rel="noreferrer noopener"
                      className="max-w-[55%] truncate text-[10px] text-faint hover:underline"
                      title={`${place.image.author} · ${place.image.license}`}
                    >
                      {t('planner.photoCredit')} {place.image.author} · {place.image.license}
                    </a>
                  ) : null}
                </div>
              </figcaption>
            </figure>
          </li>
        ))}
      </ul>
    </section>
  );
}
