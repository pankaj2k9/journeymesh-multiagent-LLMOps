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
