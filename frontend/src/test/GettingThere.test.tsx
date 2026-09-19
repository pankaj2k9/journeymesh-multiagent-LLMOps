import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { GettingThere } from '../components/trip/GettingThere';
import type { RoutePlan } from '../types';

const plan: RoutePlan = {
  origin: 'Dhaka',
  destination: 'Bandarban',
  preference: 'auto',
  round_trip: true,
  travelers: 2,
  straight_line_km: 256,
  currency: 'USD',
  source: 'ESTIMATE',
  recommended_index: 0,
  notes: ['Travel times and fares are estimates.'],
  options: [
    {
      main_mode: 'train',
      label: 'Train to Chittagong, then bus to Bandarban',
      distance_km: 380,
      duration_hours: 8.4,
      one_way_per_traveler: 7.3,
      one_way_for_group: 14.6,
      trip_total_for_group: 29.2,
      recommended: true,
      reason: 'Best balance of cost and travel time for 2 traveller(s).',
      legs: [
        {
          mode: 'train',
          from_place: 'Dhaka',
          to_place: 'Chittagong',
          distance_km: 282,
          duration_hours: 6.4,
          cost_per_traveler: 5.64,
          cost_for_group: 11.28,
        },
        {
          mode: 'bus',
          from_place: 'Chittagong',
          to_place: 'Bandarban',
          distance_km: 98,
          duration_hours: 2,
          cost_per_traveler: 2.94,
          cost_for_group: 5.88,
        },
      ],
    },
    {
      main_mode: 'flight',
      label: 'Flight to Chittagong, then bus to Bandarban',
      distance_km: 315,
      duration_hours: 5.3,
      one_way_per_traveler: 47.5,
      one_way_for_group: 95,
      trip_total_for_group: 190,
      recommended: false,
      legs: [],
    },
  ],
};

describe('GettingThere', () => {
  it('shows every option, the recommended one first, leg by leg', () => {
    render(<GettingThere plan={plan} />);

    expect(screen.getByRole('heading', { name: /getting there/i })).toBeInTheDocument();
    expect(screen.getByText('Best choice')).toBeInTheDocument();
    expect(screen.getByText(/Train: Dhaka → Chittagong/)).toBeInTheDocument();
    expect(screen.getByText(/Bus: Chittagong → Bandarban/)).toBeInTheDocument();
    expect(screen.getAllByText(/Return for 2/)).toHaveLength(2);
    expect(screen.getByText('Travel times and fares are estimates.')).toBeInTheDocument();
  });

  it('renders nothing without a plan', () => {
    const { container } = render(<GettingThere plan={null} />);
    expect(container).toBeEmptyDOMElement();
  });
});
