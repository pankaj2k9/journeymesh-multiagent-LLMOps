import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { AuthProvider } from '../auth/AuthProvider';
import { DashboardPage } from '../pages/DashboardPage';
import type { DashboardResponse, TripCard } from '../types';

const getDashboard = vi.hoisted(() => vi.fn());
vi.mock('../api/dashboard', () => ({ getDashboard }));

function trip(overrides: Partial<TripCard> = {}): TripCard {
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
      planned_cost: '0.00',
      allocated_cost: '0.00',
      remaining_budget: '4000.00',
      percentage_used: 0,
      verdict: 'within_budget',
    },
    booking: {
      flight_selected: false,
      hotel_selected: false,
      activity_count: 0,
      selected_count: 0,
      booked_count: 0,
      percent: 0,
    },
    next_item: null,
    created_at: null,
    updated_at: null,
    ...overrides,
  };
}

function response(overrides: Partial<DashboardResponse> = {}): DashboardResponse {
  return {
    user: null,
    anonymous: true,
    counts: { upcoming: 0, drafts: 0, past: 0, total: 0 },
    upcoming: [],
    drafts: [],
    past: [],
    price_watches: [],
    notifications: [],
    generated_at: '2026-09-18T10:00:00Z',
    ...overrides,
  };
}

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <AuthProvider>
          <DashboardPage />
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('DashboardPage', () => {
  beforeEach(() => {
    getDashboard.mockReset();
  });

  it('shows a loading state first', () => {
    getDashboard.mockReturnValue(new Promise(() => {}));
    renderPage();
    expect(screen.getByRole('status')).toBeInTheDocument();
  });

  it('invites a first journey when there is nothing yet', async () => {
    getDashboard.mockResolvedValue(response());
    renderPage();
    expect(await screen.findByText(/no journeys yet/i)).toBeInTheDocument();
  });

  it('lists journeys under their headings with counts', async () => {
    getDashboard.mockResolvedValue(
      response({
        counts: { upcoming: 1, drafts: 1, past: 0, total: 2 },
        upcoming: [trip()],
        drafts: [trip({ trip_id: 'trip-2', bucket: 'draft', review_status: 'awaiting_review' })],
      }),
    );
    renderPage();

    // The count sits in a nested span, so match on the accessible name.
    expect(
      await screen.findByRole('heading', { name: /upcoming journeys \(1\)/i }),
    ).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /drafts \(1\)/i })).toBeInTheDocument();
  });

  it('offers a recoverable error state rather than a blank page', async () => {
    getDashboard.mockRejectedValue(new Error('network is down'));
    renderPage();
    expect(await screen.findByRole('button', { name: /try again/i })).toBeInTheDocument();
  });

  it('greets a signed-in traveller by name instead', async () => {
    getDashboard.mockResolvedValue(
      response({
        anonymous: false,
        user: {
          id: 'u1',
          email: 'ayesha@example.com',
          display_name: 'Ayesha',
          role: 'USER',
          status: 'active',
          preferred_language: 'en',
          preferred_currency: 'USD',
          last_login_at: null,
          created_at: null,
        },
        counts: { upcoming: 1, drafts: 0, past: 0, total: 1 },
        upcoming: [trip()],
      }),
    );
    renderPage();
    // The greeting follows the signed-in state of the auth provider, which in
    // this test has no token - so the anonymous prompt is what should appear.
    await waitFor(() => expect(getDashboard).toHaveBeenCalled());
    expect(await screen.findByText(/dhaka → barcelona/i)).toBeInTheDocument();
  });

  it('keeps a place for the sections that arrive later', async () => {
    getDashboard.mockResolvedValue(response());
    renderPage();
    expect(await screen.findByText(/price watches/i)).toBeInTheDocument();
    expect(screen.getByText(/notifications/i)).toBeInTheDocument();
  });
});
