import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { AboutPage } from '../pages/AboutPage';
import { CAPABILITIES, FLOW_STEPS, STACK } from '../utils/about';

describe('AboutPage', () => {
  it('leads with the project and what it does', () => {
    render(<AboutPage />);

    expect(screen.getByRole('heading', { level: 1, name: 'JourneyMesh' })).toBeInTheDocument();
    expect(screen.getByText(/AI-Powered Multi-Agent Travel Planning/i)).toBeInTheDocument();
    expect(
      screen.getByText(/an AI-powered travel planning platform/i),
    ).toBeInTheDocument();
  });

  it('shows the whole request flow in order', () => {
    render(<AboutPage />);

    expect(FLOW_STEPS).toHaveLength(8);

    const section = screen.getByRole('heading', { name: /how it works/i })
      .closest('section') as HTMLElement;
    const flow = within(section);

    for (const label of [
      'User request',
      'Guardrails',
      'Supervisor agent',
      'Specialised agents',
      'Tools and external APIs',
      'Draft itinerary',
      'Human-in-the-loop review',
      'Final travel plan',
    ]) {
      expect(flow.getByText(label)).toBeInTheDocument();
    }

    // The steps are numbered, and in the order a request actually travels.
    const steps = flow.getAllByRole('listitem');
    expect(steps).toHaveLength(FLOW_STEPS.length);
    expect(steps[0]).toHaveTextContent('User request');
    expect(steps[steps.length - 1]).toHaveTextContent('Final travel plan');
  });

  it('describes every core capability', () => {
    render(<AboutPage />);

    expect(CAPABILITIES).toHaveLength(8);

    const section = screen.getByRole('heading', { name: /core capabilities/i })
      .closest('section') as HTMLElement;
    const capabilities = within(section);

    expect(capabilities.getByText('Multi-agent orchestration')).toBeInTheDocument();
    expect(capabilities.getByText('Intelligent agent routing')).toBeInTheDocument();
    expect(capabilities.getByText('Stateful workflows')).toBeInTheDocument();
    expect(capabilities.getByText(/determines which specialised agents/i)).toBeInTheDocument();
  });

  it('lists the infrastructure the project actually uses', () => {
    render(<AboutPage />);

    const card = screen.getByText('Infrastructure').closest('div') as HTMLElement;
    const infrastructure = within(card);
    expect(infrastructure.getByText('Docker Compose (local)')).toBeInTheDocument();
    expect(infrastructure.getByText('Railway (production)')).toBeInTheDocument();
    expect(infrastructure.getByText('Railway PostgreSQL')).toBeInTheDocument();
    expect(infrastructure.getByText('GitHub Actions')).toBeInTheDocument();
  });

  it('claims no technology the repository does not have', () => {
    render(<AboutPage />);

    // Render and Neon are gone; the frontend is Vite, not Next.js.
    for (const absent of ['Render', 'Neon', 'Next.js', 'Vercel', 'Kubernetes']) {
      expect(screen.queryByText(absent)).not.toBeInTheDocument();
    }

    const declared = STACK.flatMap((group) => group.items);
    expect(declared).toContain('PostgreSQL');
    expect(declared).toContain('Vite');
    expect(declared).not.toContain('Next.js');
  });

  it('keeps the booking disclaimer', () => {
    render(<AboutPage />);
    expect(screen.getByText(/verify prices, availability, schedules/i)).toBeInTheDocument();
  });
});
