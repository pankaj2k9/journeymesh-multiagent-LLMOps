import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { PlannerForm } from '../components/planner/PlannerForm';

describe('PlannerForm', () => {
  it('renders translated labels rather than hard-coded English strings', () => {
    render(<PlannerForm onSubmit={() => {}} />);
    expect(screen.getByLabelText(/describe your ideal trip/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /plan my journey/i })).toBeInTheDocument();
  });

  it('refuses to submit an empty description', async () => {
    const onSubmit = vi.fn();
    render(<PlannerForm onSubmit={onSubmit} />);

    await userEvent.click(screen.getByRole('button', { name: /plan my journey/i }));

    expect(await screen.findByRole('alert')).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('builds a request body from the form fields', async () => {
    const onSubmit = vi.fn();
    render(<PlannerForm onSubmit={onSubmit} />);

    await userEvent.type(
      screen.getByLabelText(/describe your ideal trip/i),
      'Plan a 5-day family trip to Singapore',
    );
    await userEvent.type(screen.getByLabelText(/^origin/i), 'Dhaka');
    await userEvent.type(screen.getByLabelText(/^destination/i), 'Singapore');
    await userEvent.click(screen.getByRole('button', { name: /^food$/i }));
    await userEvent.click(screen.getByRole('button', { name: /^family$/i }));
    await userEvent.click(screen.getByRole('button', { name: /plan my journey/i }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    const body = onSubmit.mock.calls[0][0];
    expect(body.origin).toBe('Dhaka');
    expect(body.destination).toBe('Singapore');
    expect(body.interests).toContain('food');
    expect(body.travel_style).toBe('family');
    expect(body.response_language).toBe('en');
  });

  it('rejects a return date before the departure date', async () => {
    const onSubmit = vi.fn();
    render(<PlannerForm onSubmit={onSubmit} />);

    await userEvent.type(
      screen.getByLabelText(/describe your ideal trip/i),
      'Plan a trip to Rome for a week',
    );
    await userEvent.type(screen.getByLabelText(/departure date/i), '2027-05-10');
    await userEvent.type(screen.getByLabelText(/return date/i), '2027-05-02');
    await userEvent.click(screen.getByRole('button', { name: /plan my journey/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent(/cannot be before/i);
    expect(onSubmit).not.toHaveBeenCalled();
  });
});
