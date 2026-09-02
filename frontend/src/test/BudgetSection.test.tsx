import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { BudgetSection } from '../components/trip/BudgetSection';
import type { BudgetAnalysis } from '../types';

const budget: BudgetAnalysis = {
  currency: 'USD',
  total_budget: 3000,
  estimated_total: 2650,
  breakdown: {
    flights: 900,
    hotels: 850,
    food: 400,
    transport: 200,
    activities: 200,
    miscellaneous: 100,
    total: 2650,
  },
  line_provenance: {
    flights: { amount: 900, source: 'ESTIMATE', basis: 'reference fare band' },
    hotels: { amount: 850, source: 'SEARCH_DERIVED', basis: '170/night x 5 nights' },
  },
  remaining_budget: 350,
  budget_status: 'within_budget',
  confirmed_cost_total: 850,
  estimated_cost_total: 1800,
  per_traveler_total: 883,
  recommendations: ['About 350 USD is unspent.'],
  notes: [],
};

describe('BudgetSection', () => {
  it('shows the verdict and the totals', () => {
    render(<BudgetSection budget={budget} />);
    expect(screen.getByText(/within budget/i)).toBeInTheDocument();
    expect(screen.getByText(/\$2,650/)).toBeInTheDocument();
    expect(screen.getByText(/\$350/)).toBeInTheDocument();
  });

  it('labels every cost line with where the number came from', () => {
    render(<BudgetSection budget={budget} />);
    expect(screen.getByText('Estimate')).toBeInTheDocument();
    expect(screen.getByText('From research')).toBeInTheDocument();
  });

  it('explains that nothing is available when no budget was produced', () => {
    render(
      <BudgetSection
        budget={{
          ...budget,
          estimated_total: 0,
          breakdown: {
            flights: 0,
            hotels: 0,
            food: 0,
            transport: 0,
            activities: 0,
            miscellaneous: 0,
            total: 0,
          },
        }}
      />,
    );
    expect(screen.getByText(/no budget analysis/i)).toBeInTheDocument();
  });
});
