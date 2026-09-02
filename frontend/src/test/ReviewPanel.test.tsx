import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { ReviewPanel } from '../components/review/ReviewPanel';

const baseProps = {
  revision: 1,
  maxRevisions: 3,
  reviews: [],
  approving: false,
  requesting: false,
  onApprove: () => {},
  onRequestChanges: () => {},
};

describe('ReviewPanel', () => {
  it('offers both review decisions while a draft is awaiting review', () => {
    render(<ReviewPanel {...baseProps} status="awaiting_review" />);
    expect(screen.getByRole('button', { name: /approve/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /request changes/i })).toBeInTheDocument();
  });

  it('sends the requested change text to the caller', async () => {
    const onRequestChanges = vi.fn();
    render(
      <ReviewPanel
        {...baseProps}
        status="awaiting_review"
        onRequestChanges={onRequestChanges}
      />,
    );

    await userEvent.click(screen.getByRole('button', { name: /request changes/i }));
    await userEvent.type(
      screen.getByLabelText(/what would you like to change/i),
      'Find a cheaper hotel under $120 per night.',
    );
    await userEvent.click(screen.getByRole('button', { name: /send my changes/i }));

    expect(onRequestChanges).toHaveBeenCalledWith('Find a cheaper hotel under $120 per night.');
  });

  it('will not send a change request that is too short', async () => {
    const onRequestChanges = vi.fn();
    render(
      <ReviewPanel
        {...baseProps}
        status="awaiting_review"
        onRequestChanges={onRequestChanges}
      />,
    );

    await userEvent.click(screen.getByRole('button', { name: /request changes/i }));
    await userEvent.type(screen.getByLabelText(/what would you like to change/i), 'no');
    await userEvent.click(screen.getByRole('button', { name: /send my changes/i }));

    expect(onRequestChanges).not.toHaveBeenCalled();
    expect(screen.getByRole('alert')).toBeInTheDocument();
  });

  it('stops offering changes once the revision limit is reached', () => {
    render(<ReviewPanel {...baseProps} status="revision_limit_reached" revision={3} />);
    expect(screen.queryByRole('button', { name: /request changes/i })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /approve/i })).toBeInTheDocument();
  });

  it('confirms an approved journey', () => {
    render(<ReviewPanel {...baseProps} status="approved" />);
    expect(screen.getByText(/this journey is approved/i)).toBeInTheDocument();
  });
});
