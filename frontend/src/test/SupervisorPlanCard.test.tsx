import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { GuardrailBlockedCard } from '../components/planner/GuardrailBlockedCard';
import { SupervisorPlanCard } from '../components/trip/SupervisorPlanCard';
import type { TripDetailResponse } from '../types';

/**
 * A trip response reduced to the fields the execution plan reads. Everything
 * else is defaulted, because the card must not depend on the rest of the
 * payload being present.
 */
function makeTrip(overrides: Partial<TripDetailResponse> = {}): TripDetailResponse {
  return {
    trip_id: 'trip-123',
    status: 'awaiting_review',
    review_status: 'awaiting_review',
    revision: 1,
    selected_agents: ['flight_agent', 'hotel_agent', 'itinerary_agent'],
    execution_reason: 'Chosen because the request involves getting there and where to stay.',
    constraints: {
      travelers: 2,
      currency: 'USD',
      interests: [],
      response_language: 'en',
    },
    flights: { origin_airports: [], destination_airports: [], options: [], source: 'ESTIMATE', notes: [] },
    hotels: { options: [], recommended_index: 0, source: 'ESTIMATE', notes: [] },
    weather: { forecast: [], packing_recommendations: [], travel_suggestions: [], source: 'ESTIMATE', notes: [] },
    budget: {
      currency: 'USD',
      estimated_total: 0,
      breakdown: { flights: 0, hotels: 0, food: 0, transport: 0, activities: 0, miscellaneous: 0, total: 0 },
      line_provenance: {},
      budget_status: 'insufficient_data',
      confirmed_cost_total: 0,
      estimated_cost_total: 0,
      recommendations: [],
      notes: [],
    },
    itinerary: { days: [], total_days: 0, pacing: 'balanced', estimated_activity_cost: 0, travel_tips: [], notes: [] },
    provider_status: [],
    guardrails: [{ stage: 'input', allowed: true }],
    messages: [],
    reviews: [],
    ...overrides,
  } as TripDetailResponse;
}

describe('SupervisorPlanCard', () => {
  it('reports a passing guardrail and the reasoning', () => {
    render(<SupervisorPlanCard trip={makeTrip()} />);

    expect(screen.getByText(/guardrail passed/i)).toBeInTheDocument();
    expect(screen.getByText(/execution plan/i)).toBeInTheDocument();
    expect(screen.getByText(/involves getting there/i)).toBeInTheDocument();
  });

  it('shows only the agents the supervisor selected', () => {
    render(<SupervisorPlanCard trip={makeTrip()} />);

    expect(screen.getByText('Flight Agent')).toBeInTheDocument();
    expect(screen.getByText('Hotel Agent')).toBeInTheDocument();
    expect(screen.getByText('Itinerary Agent')).toBeInTheDocument();
    expect(screen.queryByText('Weather Agent')).not.toBeInTheDocument();
    expect(screen.queryByText('Budget Agent')).not.toBeInTheDocument();
  });

  it('includes the weather agent once a revision asks for it', () => {
    render(
      <SupervisorPlanCard
        trip={makeTrip({
          selected_agents: ['weather_agent', 'itinerary_agent'],
          revision: 2,
        })}
      />,
    );

    expect(screen.getByText('Weather Agent')).toBeInTheDocument();
  });

  it('keeps preserved agents on the plan after a revision re-runs only some', () => {
    // The revision re-ran weather and the itinerary; the flights and hotels on
    // the page came from the first pass and were preserved, so they must still
    // appear rather than vanishing from the plan.
    render(
      <SupervisorPlanCard
        trip={makeTrip({
          revision: 2,
          selected_agents: ['weather_agent', 'itinerary_agent'],
          flights: {
            origin_airports: [],
            destination_airports: [],
            options: [{ stops: 0, segments: [], price_source: 'ESTIMATE', provenance: { source: 'ESTIMATE' } }],
            source: 'ESTIMATE',
            notes: [],
          },
          hotels: {
            options: [{ name: 'Hotel One', price_source: 'ESTIMATE', amenities: [], family_friendly: true, provenance: { source: 'ESTIMATE' } }],
            recommended_index: 0,
            source: 'ESTIMATE',
            notes: [],
          },
        } as Partial<TripDetailResponse>)}
      />,
    );

    expect(screen.getByText('Flight Agent')).toBeInTheDocument();
    expect(screen.getByText('Hotel Agent')).toBeInTheDocument();
    expect(screen.getByText('Weather Agent')).toBeInTheDocument();
    expect(screen.getByText(/highlighted agents re-ran/i)).toBeInTheDocument();
  });

  it('keeps the guardrail trail collapsed until it is asked for', async () => {
    render(
      <SupervisorPlanCard
        trip={makeTrip({
          guardrails: [
            { stage: 'input', allowed: true },
            { stage: 'tool', tool: 'search_flights', allowed: true },
          ],
        })}
      />,
    );

    expect(screen.queryByText(/search_flights/)).not.toBeInTheDocument();

    const toggle = screen.getByRole('button', { name: /show details/i });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    await userEvent.click(toggle);

    expect(screen.getByText(/search_flights/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /hide details/i })).toBeInTheDocument();
  });

  it('marks a refused check as blocked', async () => {
    render(
      <SupervisorPlanCard
        trip={makeTrip({
          guardrails: [{ stage: 'input', allowed: false, reason: 'prompt injection detected' }],
        })}
      />,
    );

    expect(screen.getByText(/guardrail blocked/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /show details/i }));
    expect(screen.getByText(/prompt injection detected/i)).toBeInTheDocument();
  });
});

describe('GuardrailBlockedCard', () => {
  it('explains a refusal and states that no agent ran', async () => {
    render(
      <GuardrailBlockedCard
        blocked={{
          status: 'blocked',
          reason_code: 'prompt_injection',
          message: 'Request involves hacking, which is illegal and harmful.',
          guidance: 'Ask for a travel plan without instructions to attack a system.',
        }}
      />,
    );

    expect(screen.getByText(/guardrail blocked/i)).toBeInTheDocument();
    expect(screen.getByText(/illegal and harmful/i)).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: /show details/i }));
    expect(screen.getByText('prompt_injection')).toBeInTheDocument();
    expect(screen.getByText(/refused before the workflow started/i)).toBeInTheDocument();
  });
});
