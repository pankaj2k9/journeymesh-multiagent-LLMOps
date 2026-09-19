import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';

import { AboutPage } from '../pages/AboutPage';
import { FAQ_IDS, FEATURES, STEPS } from '../utils/about';

function renderPage() {
  return render(
    <MemoryRouter>
      <AboutPage />
    </MemoryRouter>,
  );
}

describe('AboutPage', () => {
  it('speaks to travellers, with a way to start planning', () => {
    renderPage();

    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(/your own travel crew/i);
    expect(screen.getByRole('link', { name: /plan a trip/i })).toHaveAttribute('href', '/#planner');
  });

  it('lists what a traveller can do, and how planning goes', () => {
    renderPage();

    const features = screen
      .getByRole('heading', { name: /what you can do here/i })
      .closest('section') as HTMLElement;
    expect(within(features).getAllByRole('listitem')).toHaveLength(FEATURES.length);
    expect(within(features).getByText('Every way to get there')).toBeInTheDocument();

    const steps = screen
      .getByRole('heading', { name: /how it works/i })
      .closest('section') as HTMLElement;
    const items = within(steps).getAllByRole('listitem');
    expect(items).toHaveLength(STEPS.length);
    expect(items[0]).toHaveTextContent('Tell us your trip');
  });

  it('answers the common questions honestly', () => {
    renderPage();

    const faq = screen
      .getByRole('heading', { name: /common questions/i })
      .closest('section') as HTMLElement;
    expect(within(faq).getAllByRole('group')).toHaveLength(FAQ_IDS.length);
    expect(within(faq).getByText(/not yet/i)).toBeInTheDocument();
    expect(within(faq).getByText(/labelled as one/i)).toBeInTheDocument();
  });

  it('leaves the technical detail out', () => {
    renderPage();

    for (const jargon of [
      'LangGraph',
      'FastAPI',
      'Model Context Protocol',
      'Supervisor agent',
      'Guardrails',
    ]) {
      expect(screen.queryByText(new RegExp(jargon, 'i'))).not.toBeInTheDocument();
    }
  });

  it('offers a way to get in touch', () => {
    renderPage();
    expect(screen.getByRole('link', { name: /email us/i })).toHaveAttribute(
      'href',
      'mailto:pkp2.me2k9@gmail.com',
    );
  });
});
