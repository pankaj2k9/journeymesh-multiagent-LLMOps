import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';

import { TripCardView } from '../components/dashboard/TripCardView';
import type { TripCard } from '../types';

function card(overrides: Partial<TripCard> = {}): TripCard {
  return {
    trip_id: 'trip-1',
    bucket: 'upcoming',
    origin: 'Dhaka',
    destination: 'Barcelona',
    departure_date: '2027-06-10',
    return_date: '2027-06-17',
    nights: 7,
    travelers: 3,
    status: 'approved',
    review_status: 'approved',
    preferred_language: 'en',
    days_until_departure: 30,
    budget: {
      currency: 'USD',
      total_budget: '4000.00',
      committed_cost: '0.00',
      planned_cost: '1836.00',
      allocated_cost: '1836.00',
      remaining_budget: '2164.00',
      percentage_used: 45.9,
      verdict: 'within_budget',
    },
    booking: {
      flight_selected: true,
      hotel_selected: false,
      activity_count: 0,
      selected_count: 1,
      booked_count: 0,
      percent: 50,
    },
    next_item: null,
    created_at: '2026-09-18T10:00:00Z',
    updated_at: '2026-09-18T10:00:00Z',
    ...overrides,
  };
}

function renderCard(trip: TripCard) {
  return render(
    <MemoryRouter>
      <TripCardView trip={trip} />
    </MemoryRouter>,
  );
}

describe('TripCardView', () => {
  it('shows the route, the dates and the party size', () => {
    renderCard(card());
    expect(screen.getByText('Dhaka → Barcelona')).toBeInTheDocument();
    expect(screen.getByText(/3 travellers/i)).toBeInTheDocument();
  });

  it('shows what is left of the budget, not what was spent', () => {
    renderCard(card());
    expect(screen.getByText(/\$2,164/)).toBeInTheDocument();
    expect(screen.getByText(/\$4,000/)).toBeInTheDocument();
  });

  it('exposes the budget bar as a meter a screen reader can read', () => {
    renderCard(card());
    const bars = screen.getAllByRole('progressbar');
    expect(bars[0]).toHaveAttribute('aria-valuenow', '46');
  });

  it('counts down to departure', () => {
    renderCard(card({ days_until_departure: 30 }));
    expect(screen.getByText(/in 30 days/i)).toBeInTheDocument();
  });

  it('says "departs today" rather than "in 0 days"', () => {
    renderCard(card({ days_until_departure: 0 }));
    expect(screen.getByText(/departs today/i)).toBeInTheDocument();
  });

  it('marks a finished journey as completed', () => {
    renderCard(card({ bucket: 'past', days_until_departure: -12 }));
    expect(screen.getByText(/completed/i)).toBeInTheDocument();
  });

  it('invents no numbers for a journey with no budget', () => {
    renderCard(
      card({
        budget: {
          currency: 'USD',
          total_budget: null,
          committed_cost: null,
          planned_cost: null,
          allocated_cost: null,
          remaining_budget: null,
          percentage_used: null,
          verdict: 'no_budget_set',
        },
      }),
    );
    expect(screen.getByText(/no budget set/i)).toBeInTheDocument();
    expect(screen.queryByText(/\$0/)).not.toBeInTheDocument();
  });

  it('handles a journey with no dates', () => {
    renderCard(card({ departure_date: null, return_date: null, days_until_departure: null }));
    expect(screen.getByText(/no dates yet/i)).toBeInTheDocument();
  });

  it('links to the journey and straight to its budget', () => {
    renderCard(card());
    const links = screen.getAllByRole('link');
    const hrefs = links.map((link) => link.getAttribute('href'));
    expect(hrefs).toContain('/trip/trip-1');
    expect(hrefs).toContain('/trip/trip-1?tab=budget');
  });
});
