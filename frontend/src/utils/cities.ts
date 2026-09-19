/**
 * Countries and cities for the planner's one-tap choices.
 *
 * The live list comes from `GET /places`, built from the backend's airport
 * reference table, so every button is a city the agents can resolve. The
 * list below is only the fallback shown while that request is in flight or if
 * it fails - planning never waits on it. Typing any other city still works.
 */

export type TripScope = 'domestic' | 'international';

export interface City {
  name: string;
  code: string;
}

export interface Country {
  name: string;
  cities: City[];
}

export const DEFAULT_HOME_COUNTRY = 'India';

export const FALLBACK_COUNTRIES: Country[] = [
  {
    name: 'Bangladesh',
    cities: [
      { name: 'Chittagong', code: 'CGP' },
      { name: "Cox's Bazar", code: 'CXB' },
      { name: 'Dhaka', code: 'DAC' },
      { name: 'Sylhet', code: 'ZYL' },
    ],
  },
  {
    name: 'India',
    cities: [
      { name: 'Bengaluru', code: 'BLR' },
      { name: 'Chennai', code: 'MAA' },
      { name: 'Delhi', code: 'DEL' },
      { name: 'Goa', code: 'GOI' },
      { name: 'Hyderabad', code: 'HYD' },
      { name: 'Jaipur', code: 'JAI' },
      { name: 'Kochi', code: 'COK' },
      { name: 'Kolkata', code: 'CCU' },
      { name: 'Leh', code: 'IXL' },
      { name: 'Mumbai', code: 'BOM' },
      { name: 'Port Blair', code: 'IXZ' },
      { name: 'Srinagar', code: 'SXR' },
      { name: 'Udaipur', code: 'UDR' },
      { name: 'Varanasi', code: 'VNS' },
    ],
  },
  { name: 'Indonesia', cities: [{ name: 'Bali', code: 'DPS' }] },
  {
    name: 'Japan',
    cities: [
      { name: 'Osaka', code: 'KIX' },
      { name: 'Tokyo', code: 'HND' },
    ],
  },
  { name: 'Maldives', cities: [{ name: 'Malé', code: 'MLE' }] },
  { name: 'Nepal', cities: [{ name: 'Kathmandu', code: 'KTM' }] },
  { name: 'Singapore', cities: [{ name: 'Singapore', code: 'SIN' }] },
  { name: 'Sri Lanka', cities: [{ name: 'Colombo', code: 'CMB' }] },
  {
    name: 'Thailand',
    cities: [
      { name: 'Bangkok', code: 'BKK' },
      { name: 'Phuket', code: 'HKT' },
    ],
  },
  { name: 'United Arab Emirates', cities: [{ name: 'Dubai', code: 'DXB' }] },
  { name: 'United Kingdom', cities: [{ name: 'London', code: 'LHR' }] },
];

export function citiesOf(countries: Country[], country: string): City[] {
  return countries.find((item) => item.name === country)?.cities ?? [];
}

export function isCityIn(cities: City[], name: string): boolean {
  const wanted = name.trim().toLowerCase();
  return cities.some((city) => city.name.toLowerCase() === wanted);
}

/** The IATA code for a known city, or the first three letters as a label. */
export function cityCode(name: string, countries: Country[] = FALLBACK_COUNTRIES): string {
  const trimmed = name.trim();
  if (!trimmed) return '···';
  const wanted = trimmed.toLowerCase();
  for (const country of countries) {
    const found = country.cities.find((city) => city.name.toLowerCase() === wanted);
    if (found) return found.code;
  }
  return trimmed.slice(0, 3).toUpperCase();
}

/** Routes the hero cycles through while the traveller has not picked one. */
export const SHOWCASE_ROUTES: Array<[string, string]> = [
  ['Kolkata', 'Goa'],
  ['Delhi', 'Dubai'],
  ['Mumbai', 'Bali'],
  ['Bengaluru', 'Singapore'],
  ['Chennai', 'Tokyo'],
];
