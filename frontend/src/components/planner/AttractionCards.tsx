import { useTranslation } from 'react-i18next';

import type { Attraction } from '../../api/places';

interface AttractionCardsProps {
  attractions: Attraction[];
  /** Names of the attractions marked as must-see. */
  selected: string[];
  onToggle: (attraction: Attraction) => void;
  title: string;
}

/**
 * Photographs of places worth seeing, shown under the destination. Tapping
 * one marks it must-see, and picks its city when none is chosen yet.
 *
 * Every photo keeps its credit visible: the free licences they are published
 * under require it.
 */
export function AttractionCards({ attractions, selected, onToggle, title }: AttractionCardsProps) {
  const { t } = useTranslation();
  if (attractions.length === 0) return null;

  return (
    <section aria-label={title} className="space-y-2">
      <h3 className="text-sm font-medium text-ink">{title}</h3>
      <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {attractions.map((place, index) => {
          const picked = selected.includes(place.name);
          return (
            <li key={place.slug} className="jm-rise" style={{ animationDelay: `${index * 60}ms` }}>
              <div
                className={`group flex h-full flex-col overflow-hidden rounded-2xl border bg-surface shadow-card transition hover:-translate-y-0.5 hover:shadow-raised ${
                  picked ? 'border-accent ring-2 ring-accent/40' : 'border-line'
                }`}
              >
                <button
                  type="button"
                  aria-pressed={picked}
                  onClick={() => onToggle(place)}
                  className="relative block text-left"
                  aria-label={`${place.name}, ${place.city}`}
                >
                  {place.image ? (
                    <img
                      src={place.image.card_url}
                      alt=""
                      loading="lazy"
                      className="aspect-[16/10] w-full bg-elevated object-cover transition duration-500 group-hover:scale-[1.03]"
                    />
                  ) : (
                    <div className="jm-hero aspect-[16/10] w-full rounded-none border-0 shadow-none" />
                  )}
                  <span
                    className={`absolute right-2 top-2 rounded-full px-2.5 py-1 text-xs font-medium shadow-card ${
                      picked ? 'bg-accent text-accent-contrast' : 'bg-surface/90 text-ink'
                    }`}
                  >
                    {picked ? `✓ ${t('planner.mustSeeAdded')}` : `+ ${t('planner.mustSeeAdd')}`}
                  </span>
                </button>
                <div className="flex flex-1 flex-col p-3">
                  <p className="text-sm font-semibold text-ink">{place.name}</p>
                  <p className="text-xs text-muted">
                    {place.city} · {place.description || place.country}
                  </p>
                  {place.image ? (
                    <p className="mt-auto pt-2 text-[11px] leading-tight text-faint">
                      {t('planner.photoCredit')}{' '}
                      <a
                        href={place.image.source_url}
                        target="_blank"
                        rel="noreferrer noopener"
                        className="underline-offset-2 hover:underline"
                      >
                        {place.image.author}
                      </a>
                      {place.image.license ? ` · ${place.image.license}` : ''}
                    </p>
                  ) : null}
                </div>
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
