import type { Country } from '../utils/cities';
import { request } from './client';

interface PlacesResponse {
  countries: Array<{ name: string; cities: Array<{ name: string; iata: string }> }>;
}

/** Countries and the cities the agents can resolve, from the airport table. */
export async function getPlaces(): Promise<Country[]> {
  const response = await request<PlacesResponse>('/places', { anonymous: true });
  return response.countries.map((country) => ({
    name: country.name,
    cities: country.cities.map((city) => ({ name: city.name, code: city.iata })),
  }));
}

export interface Attraction {
  slug: string;
  name: string;
  city: string;
  country: string;
  description: string;
  summary: string;
  wikipedia_url: string;
  image: {
    url: string;
    card_url: string;
    width: number | null;
    height: number | null;
    author: string;
    license: string;
    license_url: string;
    source_url: string;
  } | null;
}

export async function getAttractions(params: {
  city?: string;
  country?: string;
  slugs?: string[];
  limit?: number;
}): Promise<Attraction[]> {
  const query = new URLSearchParams();
  for (const slug of params.slugs ?? []) query.append('slug', slug);
  if (params.city) query.set('city', params.city);
  if (params.country) query.set('country', params.country);
  if (params.limit) query.set('limit', String(params.limit));
  const response = await request<{ items: Attraction[] }>(`/places/attractions?${query}`, {
    anonymous: true,
  });
  return response.items;
}
