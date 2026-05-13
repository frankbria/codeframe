import React from 'react';
import { render, screen } from '@testing-library/react';
import { SpendBarChart } from '@/components/costs/SpendBarChart';

describe('SpendBarChart', () => {
  it('shows empty state when no data', () => {
    render(<SpendBarChart daily={[]} days={30} />);
    expect(screen.getByTestId('spend-chart-empty')).toHaveTextContent(
      'No spend data for this period.'
    );
  });

  it('shows empty state when all daily values are zero', () => {
    const daily = [
      { date: '2026-05-01', cost_usd: 0 },
      { date: '2026-05-02', cost_usd: 0 },
    ];
    render(<SpendBarChart daily={daily} days={7} />);
    expect(screen.getByTestId('spend-chart-empty')).toBeInTheDocument();
  });

  it('renders a bar for each daily point when data exists', () => {
    const daily = [
      { date: '2026-05-01', cost_usd: 0.5 },
      { date: '2026-05-02', cost_usd: 1.0 },
      { date: '2026-05-03', cost_usd: 0 },
    ];
    render(<SpendBarChart daily={daily} days={7} />);
    expect(screen.queryByTestId('spend-chart-empty')).not.toBeInTheDocument();
    expect(screen.getByTestId('spend-chart')).toBeInTheDocument();
    expect(screen.getByTestId('bar-2026-05-01')).toBeInTheDocument();
    expect(screen.getByTestId('bar-2026-05-02')).toBeInTheDocument();
    expect(screen.getByTestId('bar-2026-05-03')).toBeInTheDocument();
  });

  it('puts an accessible label on the chart', () => {
    const daily = [{ date: '2026-05-01', cost_usd: 0.5 }];
    render(<SpendBarChart daily={daily} days={7} />);
    expect(
      screen.getByRole('img', { name: /daily spend bar chart for the last 7 days/i })
    ).toBeInTheDocument();
  });

  it('formats currency in hover titles', () => {
    const daily = [{ date: '2026-05-01', cost_usd: 1.2345 }];
    render(<SpendBarChart daily={daily} days={7} />);
    const bar = screen.getByTestId('bar-2026-05-01');
    expect(bar.getAttribute('title')).toContain('$1.2345');
  });
});
