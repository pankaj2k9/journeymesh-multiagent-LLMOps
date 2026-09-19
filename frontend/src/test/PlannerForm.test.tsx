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
    await userEvent.click(screen.getByRole('button', { name: /add trip details/i }));
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

  it('shows the route builder up front and keeps the extras collapsed', async () => {
    render(<PlannerForm onSubmit={() => {}} />);

    expect(screen.getByLabelText(/^origin/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^domestic$/i })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    expect(screen.queryByLabelText(/special requirements/i)).not.toBeInTheDocument();

    const toggle = screen.getByRole('button', { name: /add trip details/i });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    await userEvent.click(toggle);
    expect(screen.getByLabelText(/special requirements/i)).toBeInTheDocument();
  });

  it('plans from picked buttons alone, writing the description itself', async () => {
    const onSubmit = vi.fn();
    render(<PlannerForm onSubmit={onSubmit} />);

    // The same city chips sit under both fields: origin first, destination second.
    await userEvent.click(screen.getAllByRole('button', { name: /CCU Kolkata/ })[0]);
    await userEvent.click(screen.getAllByRole('button', { name: /GOI Goa/ })[1]);
    await userEvent.click(screen.getByRole('button', { name: /^one way$/i }));
    await userEvent.click(screen.getByRole('button', { name: /^business class$/i }));
    await userEvent.click(screen.getByRole('button', { name: /resort/i }));
    await userEvent.click(screen.getByRole('button', { name: /one more traveller/i }));
    await userEvent.click(screen.getByRole('button', { name: /plan my journey/i }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    const body = onSubmit.mock.calls[0][0];
    expect(body.origin).toBe('Kolkata');
    expect(body.destination).toBe('Goa');
    expect(body.travelers).toBe(2);
    expect(body.hotel_preference).toBe('resort');
    expect(body.query).toBe('Plan a one-way domestic trip from Kolkata to Goa for 2 travellers.');
    expect(body.additional_instructions).toContain('Cabin: business class.');
    expect(body.return_date).toBeUndefined();
  });

  it('offers international destinations once international is picked', async () => {
    render(<PlannerForm onSubmit={() => {}} />);

    expect(screen.queryByRole('button', { name: /DXB Dubai/ })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /^international$/i }));
    expect(screen.getByRole('button', { name: /DXB Dubai/ })).toBeInTheDocument();
  });

  it('hides the return date for a one-way flight', async () => {
    render(<PlannerForm onSubmit={() => {}} />);

    expect(screen.getByLabelText(/return date/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /^one way$/i }));
    expect(screen.queryByLabelText(/return date/i)).not.toBeInTheDocument();
  });

  it('fills the prompt from a quick example without submitting', async () => {
    const onSubmit = vi.fn();
    render(<PlannerForm onSubmit={onSubmit} />);

    await userEvent.click(screen.getByRole('button', { name: /japan trip/i }));

    const textarea = screen.getByLabelText(/describe your ideal trip/i);
    expect(textarea).toHaveValue(
      'Plan a complete 7-day Japan trip from Bangladesh including flights, hotels, ' +
        'sightseeing and a budget under 2 lakhs.',
    );
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('lets the traveller edit a quick example before planning', async () => {
    const onSubmit = vi.fn();
    render(<PlannerForm onSubmit={onSubmit} />);

    await userEvent.click(screen.getByRole('button', { name: /dubai trip/i }));
    const textarea = screen.getByLabelText(/describe your ideal trip/i);
    await userEvent.clear(textarea);
    await userEvent.type(textarea, 'Plan a 3-day Dubai trip for two people.');
    await userEvent.click(screen.getByRole('button', { name: /plan my journey/i }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit.mock.calls[0][0].query).toBe('Plan a 3-day Dubai trip for two people.');
  });

  it('shows a spinner and blocks a second submission while planning', () => {
    render(<PlannerForm onSubmit={() => {}} submitting />);

    const submit = screen.getByRole('button', { name: /planning/i });
    expect(submit).toBeDisabled();
    expect(submit).toHaveAttribute('aria-busy', 'true');
  });
});
