/**
 * Blog posts, shipped with the frontend.
 *
 * Static on purpose: there is no CMS yet, and posts in the bundle are fast,
 * indexable and need no database. Cover images come from the media library
 * (`/admin` -> upload with category "blog") and are referenced by URL; a post
 * without one gets a themed gradient instead.
 */

export type BlogBlock =
  | { type: 'p'; text: string }
  | { type: 'h2'; text: string }
  | { type: 'ul'; items: string[] }
  | { type: 'tip'; text: string };

export interface BlogPost {
  slug: string;
  title: string;
  excerpt: string;
  category: 'Guides' | 'Planning' | 'Product';
  /** ISO date. */
  published: string;
  readMinutes: number;
  cover?: string;
  emoji: string;
  body: BlogBlock[];
}

export const BLOG_POSTS: BlogPost[] = [
  {
    slug: 'plan-a-trip-with-an-ai-crew',
    title: 'How an AI crew plans your trip',
    excerpt:
      'A supervisor, five specialists and a reviewer: what happens between typing a trip and reading a finished plan.',
    category: 'Product',
    published: '2026-09-10',
    readMinutes: 4,
    emoji: '🧭',
    body: [
      {
        type: 'p',
        text: 'Travel Crew AI does not ask one model to do everything. A supervisor reads your request, decides which specialists are needed, and hands each of them one job.',
      },
      { type: 'h2', text: 'The specialists' },
      {
        type: 'ul',
        items: [
          'Flights - routes and fares between your origin and destination.',
          'Hotels - stays that match the type and budget you picked.',
          'Weather - what to expect on your dates, so the plan fits the season.',
          'Budget - a running total in your currency, split by category.',
          'Itinerary - a day-by-day plan built around your interests.',
        ],
      },
      { type: 'h2', text: 'Checked before you see it' },
      {
        type: 'p',
        text: 'Every draft is evaluated and then paused for your review. Ask for a change and only the specialists that change affects run again, so a cheaper hotel does not re-plan your flights.',
      },
      {
        type: 'tip',
        text: 'Prices and availability come from providers and can change. Always confirm before you book.',
      },
    ],
  },
  {
    slug: 'domestic-vs-international-checklist',
    title: 'Domestic or international: a pre-trip checklist',
    excerpt:
      'The documents, money and timing questions that differ between a trip at home and a trip abroad.',
    category: 'Guides',
    published: '2026-09-03',
    readMinutes: 5,
    emoji: '🛂',
    body: [
      {
        type: 'p',
        text: 'Picking "Domestic" or "International" in the planner changes more than the list of cities. It changes what you need to sort out before you leave.',
      },
      { type: 'h2', text: 'For every trip' },
      {
        type: 'ul',
        items: [
          'A government photo ID that matches the name on your ticket.',
          'Airline check-in times - larger airports need more margin.',
          'A copy of your bookings that works offline.',
        ],
      },
      { type: 'h2', text: 'Additionally, abroad' },
      {
        type: 'ul',
        items: [
          'A passport valid well beyond your return date - many countries ask for six months.',
          'The visa or entry permit your destination requires for your nationality.',
          'Travel insurance that covers medical care where you are going.',
          'A card that works overseas, and a little local currency for arrival.',
        ],
      },
      {
        type: 'tip',
        text: 'Entry rules change. Check the destination government or embassy website close to your travel date.',
      },
    ],
  },
  {
    slug: 'set-a-travel-budget-that-holds',
    title: 'Setting a travel budget that holds',
    excerpt:
      'Why a single number is not a budget, and how splitting it by category keeps a trip on track.',
    category: 'Planning',
    published: '2026-08-27',
    readMinutes: 4,
    emoji: '💰',
    body: [
      {
        type: 'p',
        text: 'A budget that is one number tends to be spent on the first two things you book. Splitting it up front makes the trade-offs visible while you can still make them.',
      },
      { type: 'h2', text: 'A simple split' },
      {
        type: 'ul',
        items: [
          'Getting there and back.',
          'Where you sleep.',
          'Food and local transport, per day.',
          'Activities and entry fees.',
          'A buffer for the unexpected.',
        ],
      },
      {
        type: 'p',
        text: 'Each journey in Travel Crew AI has a budget tab that tracks planned against spent in your currency, converted at published reference rates.',
      },
    ],
  },
  {
    slug: 'choosing-the-right-stay',
    title: 'Hostel, guesthouse or resort: choosing a stay',
    excerpt: 'What each hotel type in the planner is good for, and when to pick it.',
    category: 'Guides',
    published: '2026-08-20',
    readMinutes: 3,
    emoji: '🏨',
    body: [
      {
        type: 'p',
        text: 'The hotel type you pick steers which stays the hotel specialist looks for. None is better than the others - they suit different trips.',
      },
      {
        type: 'ul',
        items: [
          'Hostel - lowest cost, social, best for solo travellers.',
          'Guesthouse - local hosts and a quieter base.',
          '3 to 5 star - more predictable service as the stars go up.',
          'Apartment - a kitchen and space for families and longer stays.',
          'Resort - everything on site, for trips that are about resting.',
        ],
      },
    ],
  },
];

export function findPost(slug: string | undefined): BlogPost | undefined {
  return BLOG_POSTS.find((post) => post.slug === slug);
}
