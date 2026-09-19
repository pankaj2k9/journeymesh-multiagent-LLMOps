/**
 * Content structure for the About page, written for travellers.
 *
 * Each entry describes something the product does today - no roadmap items.
 * The words live in the locale files; this file only fixes the order and icons.
 */

export interface AboutItem {
  id: string;
  icon: string;
}

/** What a traveller can do here. */
export const FEATURES: AboutItem[] = [
  { id: 'minutes', icon: '⏱️' },
  { id: 'transport', icon: '🚆' },
  { id: 'places', icon: '📸' },
  { id: 'budget', icon: '💰' },
  { id: 'groups', icon: '👨‍👩‍👧' },
  { id: 'control', icon: '✍️' },
  { id: 'language', icon: '🗣️' },
  { id: 'save', icon: '📄' },
];

/** How planning goes, from the traveller's side. */
export const STEPS: AboutItem[] = [
  { id: 'tell', icon: '🧭' },
  { id: 'crew', icon: '🤝' },
  { id: 'review', icon: '👀' },
  { id: 'go', icon: '🧳' },
];

/** Questions people ask before they trust a planner with a trip. */
export const FAQ_IDS = ['free', 'booking', 'prices', 'account', 'languages', 'regions'] as const;
