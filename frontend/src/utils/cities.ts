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
      { name: 'Bandarban', code: 'CGP' },
      { name: 'Chittagong', code: 'CGP' },
      { name: "Cox's Bazar", code: 'CXB' },
      { name: 'Dhaka', code: 'DAC' },
      { name: "Saint Martin's Island", code: 'CXB' },
      { name: 'Sreemangal', code: 'ZYL' },
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
  { name: 'Bahrain', cities: [{ name: 'Manama', code: 'BAH' }] },
  {
    name: 'Egypt',
    cities: [
      { name: 'Cairo', code: 'CAI' },
      { name: 'Luxor', code: 'LXR' },
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
  {
    name: 'Philippines',
    cities: [
      { name: 'Boracay', code: 'MPH' },
      { name: 'Cebu', code: 'CEB' },
      { name: 'Manila', code: 'MNL' },
    ],
  },
  { name: 'Singapore', cities: [{ name: 'Singapore', code: 'SIN' }] },
  {
    name: 'Sri Lanka',
    cities: [
      { name: 'Colombo', code: 'CMB' },
      { name: 'Kandy', code: 'CMB' },
    ],
  },
  {
    name: 'Thailand',
    cities: [
      { name: 'Bangkok', code: 'BKK' },
      { name: 'Phuket', code: 'HKT' },
    ],
  },
  {
    name: 'Turkiye',
    cities: [
      { name: 'Cappadocia', code: 'NAV' },
      { name: 'Istanbul', code: 'IST' },
    ],
  },
  { name: 'United Arab Emirates', cities: [{ name: 'Dubai', code: 'DXB' }] },
  { name: 'United Kingdom', cities: [{ name: 'London', code: 'LHR' }] },
];

// The city a placeholder suggests: the one most travellers would think of
// first, which is not always the first alphabetically (India would say "Agra").
const EXAMPLE_CITY: Record<string, string> = {
  Bangladesh: 'Dhaka',
  China: 'Beijing',
  India: 'Delhi',
  Japan: 'Tokyo',
  'United Arab Emirates': 'Dubai',
  'United Kingdom': 'London',
  'United States': 'New York',
  Australia: 'Sydney',
  Thailand: 'Bangkok',
  Vietnam: 'Hanoi',
  Egypt: 'Cairo',
  Turkiye: 'Istanbul',
  Bahrain: 'Manama',
  Philippines: 'Manila',
  'Sri Lanka': 'Colombo',
  Malaysia: 'Kuala Lumpur',
  Indonesia: 'Bali',
  Nepal: 'Kathmandu',
};

/** A city to suggest in a placeholder for `country`, or '' when it has none. */
export function exampleCity(countries: Country[], country: string): string {
  const cities = citiesOf(countries, country);
  const preferred = EXAMPLE_CITY[country];
  if (preferred && isCityIn(cities, preferred)) return preferred;
  return cities[0]?.name ?? '';
}

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
