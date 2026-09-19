/**
 * Cities offered as one-tap choices in the planner.
 *
 * "Domestic" means India, the home market of the three interface languages.
 * These are shortcuts, not a whitelist: the fields still accept any city, and
 * the backend resolves airports from its own reference data.
 */

export type TripScope = 'domestic' | 'international';

export interface City {
  name: string;
  code: string;
}

export const DOMESTIC_CITIES: City[] = [
  { name: 'Delhi', code: 'DEL' },
  { name: 'Mumbai', code: 'BOM' },
  { name: 'Bengaluru', code: 'BLR' },
  { name: 'Kolkata', code: 'CCU' },
  { name: 'Chennai', code: 'MAA' },
  { name: 'Hyderabad', code: 'HYD' },
  { name: 'Goa', code: 'GOI' },
  { name: 'Jaipur', code: 'JAI' },
  { name: 'Kochi', code: 'COK' },
  { name: 'Varanasi', code: 'VNS' },
  { name: 'Srinagar', code: 'SXR' },
  { name: 'Leh', code: 'IXL' },
  { name: 'Udaipur', code: 'UDR' },
  { name: 'Port Blair', code: 'IXZ' },
];

export const INTERNATIONAL_CITIES: City[] = [
  { name: 'Dubai', code: 'DXB' },
  { name: 'Singapore', code: 'SIN' },
  { name: 'Bangkok', code: 'BKK' },
  { name: 'Bali', code: 'DPS' },
  { name: 'Kuala Lumpur', code: 'KUL' },
  { name: 'Kathmandu', code: 'KTM' },
  { name: 'Dhaka', code: 'DAC' },
  { name: 'Colombo', code: 'CMB' },
  { name: 'Malé', code: 'MLE' },
  { name: 'London', code: 'LHR' },
  { name: 'Paris', code: 'CDG' },
  { name: 'Tokyo', code: 'HND' },
  { name: 'New York', code: 'JFK' },
  { name: 'Sydney', code: 'SYD' },
];

export function citiesFor(scope: TripScope): City[] {
  return scope === 'domestic' ? DOMESTIC_CITIES : INTERNATIONAL_CITIES;
}

const BY_NAME = new Map(
  [...DOMESTIC_CITIES, ...INTERNATIONAL_CITIES].map((city) => [city.name.toLowerCase(), city]),
);

/** The IATA code for a known city, or the first three letters as a label. */
export function cityCode(name: string): string {
  const trimmed = name.trim();
  if (!trimmed) return '···';
  return BY_NAME.get(trimmed.toLowerCase())?.code ?? trimmed.slice(0, 3).toUpperCase();
}

/** Routes the hero cycles through while the traveller has not picked one. */
export const SHOWCASE_ROUTES: Array<[string, string]> = [
  ['Kolkata', 'Goa'],
  ['Delhi', 'Dubai'],
  ['Mumbai', 'Bali'],
  ['Bengaluru', 'Singapore'],
  ['Chennai', 'Tokyo'],
];
