import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import type { Attraction } from '../api/places';
import { PlannerForm } from '../components/planner/PlannerForm';

function place(name: string, city: string, country = 'India'): Attraction {
  return {
    slug: name.toLowerCase().replace(/\W+/g, '-'),
    name,
    city,
    country,
    description: '',
    summary: '',
    wikipedia_url: '',
    image: {
      url: '/media/x.webp',
      card_url: '/media/x-small.webp',
      width: 640,
      height: 480,
      author: 'A. Photographer',
      license: 'CC BY-SA 4.0',
      license_url: '',
      source_url: 'https://commons.wikimedia.org/wiki/File:X.jpg',
    },
  };
}

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
    await userEvent.click(
      within(screen.getByRole('group', { name: /travel style/i })).getByRole('button', {
        name: /^family$/i,
      }),
    );
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

  it('offers the cities of the chosen destination country abroad', async () => {
    const onSubmit = vi.fn();
    render(<PlannerForm onSubmit={onSubmit} />);

    expect(screen.queryByLabelText(/travelling to \(country\)/i)).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /^international$/i }));
    expect(screen.queryByRole('button', { name: /DXB Dubai/ })).not.toBeInTheDocument();

    await userEvent.selectOptions(
      screen.getByLabelText(/travelling to \(country\)/i),
      'United Arab Emirates',
    );
    await userEvent.click(screen.getByRole('button', { name: /DXB Dubai/ }));
    await userEvent.click(screen.getByRole('button', { name: /plan my journey/i }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    const body = onSubmit.mock.calls[0][0];
    expect(body.destination).toBe('Dubai');
    expect(body.query).toContain('to Dubai, United Arab Emirates');
    expect(body.additional_instructions).toContain('From country: India.');
    expect(body.additional_instructions).toContain('To country: United Arab Emirates.');
  });

  it('switches the domestic cities with the home country', async () => {
    render(<PlannerForm onSubmit={() => {}} />);

    expect(screen.getAllByRole('button', { name: /CCU Kolkata/ }).length).toBeGreaterThan(0);
    await userEvent.selectOptions(screen.getByLabelText(/travelling from/i), 'Bangladesh');
    expect(screen.queryByRole('button', { name: /CCU Kolkata/ })).not.toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: /DAC Dhaka/ }).length).toBe(2);
  });

  it('plans to a country when no city there is picked', async () => {
    const onSubmit = vi.fn();
    render(<PlannerForm onSubmit={onSubmit} />);

    await userEvent.click(screen.getByRole('button', { name: /^international$/i }));
    await userEvent.selectOptions(screen.getByLabelText(/travelling to \(country\)/i), 'Japan');
    await userEvent.click(screen.getByRole('button', { name: /plan my journey/i }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit.mock.calls[0][0].destination).toBe('Japan');
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

  it('counts a family as adults plus children', async () => {
    const onSubmit = vi.fn();
    render(<PlannerForm onSubmit={onSubmit} />);

    await userEvent.click(
      within(screen.getByRole('group', { name: /^who is travelling\?$/i })).getByRole('button', {
        name: /family/i,
      }),
    );
    await userEvent.click(screen.getByRole('button', { name: /increase children/i }));
    await userEvent.click(screen.getAllByRole('button', { name: /GOI Goa/ })[1]);
    await userEvent.click(screen.getByRole('button', { name: /plan my journey/i }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    const body = onSubmit.mock.calls[0][0];
    expect(body.travelers).toBe(4);
    expect(body.additional_instructions).toContain('family of 4 (2 adults, 2 children)');
  });

  it('asks how many are in a bachelors group', async () => {
    const onSubmit = vi.fn();
    render(<PlannerForm onSubmit={onSubmit} />);

    await userEvent.click(screen.getByRole('button', { name: /bachelors/i }));
    expect(screen.getByLabelText(/^how many in the group\?$/i)).toHaveValue(4);
    await userEvent.click(screen.getByRole('button', { name: /increase how many/i }));
    await userEvent.click(screen.getAllByRole('button', { name: /GOI Goa/ })[1]);
    await userEvent.click(screen.getByRole('button', { name: /plan my journey/i }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit.mock.calls[0][0].travelers).toBe(5);
  });

  it('suggests cities from the chosen countries in the placeholders', async () => {
    render(<PlannerForm onSubmit={() => {}} />);

    expect(screen.getByLabelText(/^origin/i)).toHaveAttribute('placeholder', 'e.g. Delhi');
    await userEvent.selectOptions(screen.getByLabelText(/travelling from/i), 'Bangladesh');
    expect(screen.getByLabelText(/^origin/i)).toHaveAttribute('placeholder', 'e.g. Dhaka');

    await userEvent.click(screen.getByRole('button', { name: /^international$/i }));
    expect(screen.getByLabelText(/^destination/i)).toHaveAttribute(
      'placeholder',
      'Choose a country first',
    );
    await userEvent.selectOptions(screen.getByLabelText(/travelling to \(country\)/i), 'Japan');
    expect(screen.getByLabelText(/^destination/i)).toHaveAttribute('placeholder', 'e.g. Tokyo');
  });

  it('turns a tapped attraction into the destination and a must-see', async () => {
    const onSubmit = vi.fn();
    render(
      <PlannerForm
        onSubmit={onSubmit}
        attractions={[place('Taj Mahal', 'Agra'), place('Red Fort', 'Delhi')]}
      />,
    );

    expect(screen.getAllByText('A. Photographer')).toHaveLength(2);
    await userEvent.click(screen.getByRole('button', { name: /taj mahal, agra/i }));
    expect(screen.getByLabelText(/^destination/i)).toHaveValue('Agra');
    await userEvent.click(screen.getByRole('button', { name: /plan my journey/i }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    const body = onSubmit.mock.calls[0][0];
    expect(body.destination).toBe('Agra');
    expect(body.additional_instructions).toContain('Must-see: Taj Mahal.');
  });

  it('sends the chosen way of getting there, and hides cabin class off a plane', async () => {
    const onSubmit = vi.fn();
    render(<PlannerForm onSubmit={onSubmit} />);

    expect(screen.getByRole('button', { name: /auto \(best\)/i })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    expect(screen.getByRole('group', { name: /cabin class/i })).toBeInTheDocument();

    await userEvent.click(
      within(screen.getByRole('group', { name: /how do you want to get there/i })).getByRole(
        'button',
        { name: /^bus$/i },
      ),
    );
    expect(screen.queryByRole('group', { name: /cabin class/i })).not.toBeInTheDocument();

    await userEvent.click(screen.getAllByRole('button', { name: /GOI Goa/ })[1]);
    await userEvent.click(screen.getByRole('button', { name: /plan my journey/i }));
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit.mock.calls[0][0].transport_mode).toBe('bus');
  });
});
