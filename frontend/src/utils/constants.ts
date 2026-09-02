import type { HotelPreference, Interest, LanguageCode, TravelStyle } from '../types';

export const LANGUAGES: LanguageCode[] = ['en', 'bn', 'hi'];
export const DEFAULT_LANGUAGE: LanguageCode = 'en';

// Theme and language persist under separate keys and never affect each other.
// See src/theme/theme.ts for THEME_STORAGE_KEY.
export const LANGUAGE_STORAGE_KEY = 'journeymesh_language';
export const LEGACY_LANGUAGE_STORAGE_KEY = 'journeymesh.language';
export const SESSION_STORAGE_KEY = 'journeymesh.session';

export const TRAVEL_STYLES: TravelStyle[] = [
  'budget',
  'comfort',
  'luxury',
  'adventure',
  'family',
  'business',
  'relaxed',
];

export const HOTEL_PREFERENCES: HotelPreference[] = [
  'any',
  'hostel',
  'guesthouse',
  'three_star',
  'four_star',
  'five_star',
  'apartment',
  'resort',
];

export const INTERESTS: Interest[] = [
  'food',
  'nature',
  'history',
  'culture',
  'shopping',
  'beaches',
  'nightlife',
  'photography',
  'technology',
  'family_activities',
];

export const CURRENCIES = ['USD', 'EUR', 'GBP', 'INR', 'BDT', 'AED', 'SGD', 'JPY', 'AUD'];

export const AGENT_LABELS: Record<string, string> = {
  supervisor: 'Supervisor',
  flight_agent: 'Flight',
  hotel_agent: 'Hotel',
  weather_agent: 'Weather',
  budget_agent: 'Budget',
  itinerary_agent: 'Itinerary',
  final_response_agent: 'Final response',
};
