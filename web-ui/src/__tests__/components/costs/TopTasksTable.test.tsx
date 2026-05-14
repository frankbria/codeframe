import React from 'react';
import { render, screen } from '@testing-library/react';
import { TopTasksTable } from '@/components/costs/TopTasksTable';
import type { TaskCostEntry } from '@/types';

function makeEntry(overrides: Partial<TaskCostEntry> = {}): TaskCostEntry {
  return {
    task_id: 't-1',
    task_title: 'Build login flow',
    agent_id: 'react-agent',
    input_tokens: 1234,
    output_tokens: 567,
    total_cost_usd: 0.4321,
    ...overrides,
  };
}

describe('TopTasksTable', () => {
  it('renders an empty state when no tasks have cost data', () => {
    render(<TopTasksTable tasks={[]} />);
    expect(screen.getByTestId('top-tasks-empty')).toBeInTheDocument();
  });

  it('renders a loading skeleton when isLoading is true and no data', () => {
    render(<TopTasksTable tasks={[]} isLoading />);
    expect(screen.getByTestId('top-tasks-loading')).toBeInTheDocument();
    expect(screen.queryByTestId('top-tasks-empty')).not.toBeInTheDocument();
  });

  it('renders one row per task with title, agent, tokens, and cost', () => {
    render(
      <TopTasksTable
        tasks={[
          makeEntry({ task_id: 't-1', task_title: 'Foo', total_cost_usd: 0.50 }),
          makeEntry({ task_id: 't-2', task_title: 'Bar', total_cost_usd: 0.10 }),
        ]}
      />
    );
    const table = screen.getByTestId('top-tasks-table');
    expect(table).toBeInTheDocument();
    expect(screen.getByText('Foo')).toBeInTheDocument();
    expect(screen.getByText('Bar')).toBeInTheDocument();
    // Both agent IDs render
    expect(screen.getAllByText('react-agent').length).toBeGreaterThanOrEqual(2);
  });

  it('formats cost with at least four decimal places of precision', () => {
    render(<TopTasksTable tasks={[makeEntry({ total_cost_usd: 0.0123 })]} />);
    // Allow either $0.0123 or $0.012300 — anything but $0.01 (2dp) is fine
    const cells = screen.getAllByText(/\$0\.0123/);
    expect(cells.length).toBeGreaterThanOrEqual(1);
  });

  it('links the task title to the tasks page filtered by id', () => {
    render(<TopTasksTable tasks={[makeEntry({ task_id: 'abc-123' })]} />);
    const link = screen.getByRole('link', { name: /build login flow/i });
    expect(link).toHaveAttribute('href', '/tasks?selected=abc-123');
  });
});
