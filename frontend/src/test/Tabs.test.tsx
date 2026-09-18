import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { TabPanel, Tabs } from '../components/common/Tabs';

const TABS = [
  { id: 'overview', label: 'Overview' },
  { id: 'flights', label: 'Flights' },
  { id: 'budget', label: 'Budget' },
];

function Harness() {
  const [active, setActive] = useState('overview');
  return (
    <>
      <Tabs tabs={TABS} active={active} onChange={setActive} ariaLabel="Journey sections" />
      <TabPanel id="overview" active={active}>
        <p>Overview body</p>
      </TabPanel>
      <TabPanel id="flights" active={active}>
        <p>Flights body</p>
      </TabPanel>
      <TabPanel id="budget" active={active}>
        <p>Budget body</p>
      </TabPanel>
    </>
  );
}

describe('Tabs', () => {
  it('renders a real tablist with one selected tab', () => {
    render(<Harness />);
    expect(screen.getByRole('tablist', { name: 'Journey sections' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Overview' })).toHaveAttribute(
      'aria-selected',
      'true',
    );
    expect(screen.getByRole('tab', { name: 'Flights' })).toHaveAttribute(
      'aria-selected',
      'false',
    );
  });

  it('shows only the active panel', () => {
    render(<Harness />);
    expect(screen.getByText('Overview body')).toBeInTheDocument();
    expect(screen.queryByText('Flights body')).not.toBeInTheDocument();
  });

  it('switches panel on click', async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByRole('tab', { name: 'Budget' }));
    expect(screen.getByText('Budget body')).toBeInTheDocument();
    expect(screen.queryByText('Overview body')).not.toBeInTheDocument();
  });

  it('moves with the arrow keys, which a div-based tab strip usually loses', async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByRole('tab', { name: 'Overview' }));

    await user.keyboard('{ArrowRight}');
    expect(screen.getByText('Flights body')).toBeInTheDocument();

    await user.keyboard('{ArrowLeft}');
    expect(screen.getByText('Overview body')).toBeInTheDocument();
  });

  it('wraps around at the ends', async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByRole('tab', { name: 'Overview' }));
    await user.keyboard('{ArrowLeft}');
    expect(screen.getByText('Budget body')).toBeInTheDocument();
  });

  it('keeps only the selected tab in the tab order', () => {
    render(<Harness />);
    expect(screen.getByRole('tab', { name: 'Overview' })).toHaveAttribute('tabindex', '0');
    expect(screen.getByRole('tab', { name: 'Flights' })).toHaveAttribute('tabindex', '-1');
  });

  it('reports the change to its owner', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <Tabs tabs={TABS} active="overview" onChange={onChange} ariaLabel="Journey sections" />,
    );
    await user.click(screen.getByRole('tab', { name: 'Flights' }));
    expect(onChange).toHaveBeenCalledWith('flights');
  });
});
