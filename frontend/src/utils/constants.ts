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

/**
 * Example prompts shown as chips under the main input.
 *
 * Configuration, not JSX: the label and the prompt text live in the locale
 * catalogues under `planner.quickPrompts.<id>`, so a new destination is one
 * entry here plus three catalogue entries, and the examples are translated
 * rather than hard-coded in English.
 */
export interface QuickPrompt {
  id: string;
  flag: string;
}

export const QUICK_PROMPTS: QuickPrompt[] = [
  { id: 'india', flag: '\u{1F1EE}\u{1F1F3}' },
  { id: 'china', flag: '\u{1F1E8}\u{1F1F3}' },
  { id: 'maldives', flag: '\u{1F1F2}\u{1F1FB}' },
  { id: 'singapore', flag: '\u{1F1F8}\u{1F1EC}' },
  { id: 'japan', flag: '\u{1F1EF}\u{1F1F5}' },
  { id: 'dubai', flag: '\u{1F1E6}\u{1F1EA}' },
];

/**
 * How each agent is presented wherever a selected-agent list is rendered.
 *
 * One place decides the icon and the label key, so the execution plan, the
 * overview card and the revision summary cannot disagree with each other.
 */
export interface AgentDisplay {
  icon: string;
  labelKey: string;
}

export const AGENT_DISPLAY: Record<string, AgentDisplay> = {
  supervisor: { icon: '\u{1F9ED}', labelKey: 'agents.supervisor' },
  flight_agent: { icon: '\u{2708}\u{FE0F}', labelKey: 'agents.flight_agent' },
  hotel_agent: { icon: '\u{1F3E8}', labelKey: 'agents.hotel_agent' },
  weather_agent: { icon: '\u{1F326}\u{FE0F}', labelKey: 'agents.weather_agent' },
  budget_agent: { icon: '\u{1F4B0}', labelKey: 'agents.budget_agent' },
  itinerary_agent: { icon: '\u{1F4CB}', labelKey: 'agents.itinerary_agent' },
  final_response_agent: { icon: '\u{2728}', labelKey: 'agents.final_response_agent' },
};
