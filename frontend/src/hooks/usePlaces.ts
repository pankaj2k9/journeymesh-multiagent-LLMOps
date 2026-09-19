import { useQuery } from '@tanstack/react-query';

import { getPlaces } from '../api/places';
import { FALLBACK_COUNTRIES, type Country } from '../utils/cities';

/**
 * The planner's country and city list. The bundled fallback is used until the
 * server answers, and for good if it cannot - the form never waits on this.
 */
export function usePlaces(): Country[] {
  const { data } = useQuery({
    queryKey: ['places'],
    queryFn: getPlaces,
    staleTime: Infinity,
    retry: 1,
  });
  return data && data.length > 0 ? data : FALLBACK_COUNTRIES;
}
