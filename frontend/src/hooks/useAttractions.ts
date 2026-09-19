import { useQuery } from '@tanstack/react-query';

import { getAttractions, type Attraction } from '../api/places';

/**
 * Attractions for a city, or the top ones in a country when no city is
 * picked. Empty while loading or if the request fails: attractions decorate
 * the planner, they never block it.
 */
export function useAttractions(city: string, country: string, limit = 6): Attraction[] {
  const wanted = city.trim() ? { city: city.trim(), limit } : { country, limit };
  const { data } = useQuery({
    queryKey: ['attractions', wanted],
    queryFn: () => getAttractions(wanted),
    enabled: Boolean(wanted.city || wanted.country),
    staleTime: 5 * 60_000,
    retry: 1,
  });
  return data ?? [];
}

/** Specific attractions by slug, in the order asked for. */
export function useFeaturedAttractions(slugs: string[]): Attraction[] {
  const { data } = useQuery({
    queryKey: ['attractions', 'featured', slugs],
    queryFn: () => getAttractions({ slugs, limit: slugs.length }),
    staleTime: 30 * 60_000,
    retry: 1,
  });
  if (!data) return [];
  return slugs
    .map((slug) => data.find((item) => item.slug === slug))
    .filter((item): item is Attraction => Boolean(item));
}
