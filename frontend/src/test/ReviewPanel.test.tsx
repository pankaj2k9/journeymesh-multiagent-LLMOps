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

const APPROVE = /approve & generate final/i;
const REVISE = /revise using feedback/i;
const FEEDBACK = /revision feedback/i;

describe('ReviewPanel', () => {
  it('offers both review decisions and the feedback box without a toggle', () => {
    render(<ReviewPanel {...baseProps} status="awaiting_review" />);

    expect(screen.getByRole('button', { name: APPROVE })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: REVISE })).toBeInTheDocument();
    expect(screen.getByLabelText(FEEDBACK)).toBeInTheDocument();
  });

  it('sends the requested change text to the caller', async () => {
    const onRequestChanges = vi.fn();
    render(
      <ReviewPanel {...baseProps} status="awaiting_review" onRequestChanges={onRequestChanges} />,
    );

    await userEvent.type(
      screen.getByLabelText(FEEDBACK),
      'Find a cheaper hotel under $120 per night.',
    );
    await userEvent.click(screen.getByRole('button', { name: REVISE }));

    expect(onRequestChanges).toHaveBeenCalledWith('Find a cheaper hotel under $120 per night.');
  });

  it('approves without requiring feedback', async () => {
    const onApprove = vi.fn();
    render(<ReviewPanel {...baseProps} status="awaiting_review" onApprove={onApprove} />);

    await userEvent.click(screen.getByRole('button', { name: APPROVE }));

    expect(onApprove).toHaveBeenCalledTimes(1);
  });

  it('will not spend a revision on a change request that is too short', async () => {
    const onRequestChanges = vi.fn();
    render(
      <ReviewPanel {...baseProps} status="awaiting_review" onRequestChanges={onRequestChanges} />,
    );

    await userEvent.type(screen.getByLabelText(FEEDBACK), 'no');
    await userEvent.click(screen.getByRole('button', { name: REVISE }));

    expect(onRequestChanges).not.toHaveBeenCalled();
    expect(screen.getByRole('alert')).toBeInTheDocument();
  });

  it('shows a spinner on the approving button and locks the other one', () => {
    render(<ReviewPanel {...baseProps} status="awaiting_review" approving />);

    const approve = screen.getByRole('button', { name: /approving/i });
    expect(approve).toBeDisabled();
    expect(approve).toHaveAttribute('aria-busy', 'true');
    expect(screen.getByRole('button', { name: REVISE })).toBeDisabled();
  });

  it('shows a spinner on the revise button and locks approval', () => {
    render(<ReviewPanel {...baseProps} status="awaiting_review" requesting />);

    const revise = screen.getByRole('button', { name: /revising/i });
    expect(revise).toBeDisabled();
    expect(revise).toHaveAttribute('aria-busy', 'true');
    expect(screen.getByRole('button', { name: APPROVE })).toBeDisabled();
  });

  it('offers a retry when a review action failed', async () => {
    const onRetry = vi.fn();
    render(
      <ReviewPanel
        {...baseProps}
        status="awaiting_review"
        errorMessage="The planning service took too long to answer."
        onRetry={onRetry}
      />,
    );

    expect(screen.getByText(/took too long/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /try again/i }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it('stops offering changes once the revision limit is reached', () => {
    render(<ReviewPanel {...baseProps} status="revision_limit_reached" revision={3} />);

    expect(screen.queryByRole('button', { name: REVISE })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: APPROVE })).toBeInTheDocument();
  });

  it('confirms an approved journey', () => {
    render(<ReviewPanel {...baseProps} status="approved" />);
    expect(screen.getByText(/this journey is approved/i)).toBeInTheDocument();
  });
});
