import React from 'react';
import { render, screen } from '@testing-library/react';
import { AgentCostBars } from '@/components/costs/AgentCostBars';
import type { AgentCostsResponse } from '@/types';

function makeData(overrides: Partial<AgentCostsResponse> = {}): AgentCostsResponse {
  return {
    by_agent: [
      {
        agent_id: 'react-agent',
        input_tokens: 800,
        output_tokens: 400,
        total_cost_usd: 0.50,
        call_count: 5,
      },
      {
        agent_id: 'codex',
        input_tokens: 200,
        output_tokens: 100,
        total_cost_usd: 0.10,
        call_count: 1,
      },
    ],
    total_input_tokens: 1000,
    total_output_tokens: 500,
    ...overrides,
  };
}

describe('AgentCostBars', () => {
  it('renders an empty state when no agents have cost data', () => {
    render(
      <AgentCostBars
        data={{ by_agent: [], total_input_tokens: 0, total_output_tokens: 0 }}
      />
    );
    expect(screen.getByTestId('agent-bars-empty')).toBeInTheDocument();
  });

  it('renders a loading skeleton when isLoading and no data', () => {
    render(
      <AgentCostBars
        data={{ by_agent: [], total_input_tokens: 0, total_output_tokens: 0 }}
        isLoading
      />
    );
    expect(screen.getByTestId('agent-bars-loading')).toBeInTheDocument();
  });

  it('renders one row per agent with a progressbar bar', () => {
    render(<AgentCostBars data={makeData()} />);
    expect(screen.getByTestId('agent-bars')).toBeInTheDocument();
    expect(screen.getByTestId('agent-row-react-agent')).toBeInTheDocument();
    expect(screen.getByTestId('agent-row-codex')).toBeInTheDocument();

    // Each bar exposes role="progressbar"
    const bars = screen.getAllByRole('progressbar');
    expect(bars).toHaveLength(2);
  });

  it('shows the input/output token split with computed percentage', () => {
    render(<AgentCostBars data={makeData()} />);
    const split = screen.getByTestId('token-split');
    // 1000 / (1000+500) = 66.7% -> rounds to 67%
    expect(split.textContent).toContain('1,000');
    expect(split.textContent).toContain('500');
    expect(split.textContent).toMatch(/67%/);
  });

  it('handles zero totals without dividing by zero', () => {
    render(
      <AgentCostBars
        data={{
          by_agent: [
            {
              agent_id: 'a',
              input_tokens: 0,
              output_tokens: 0,
              total_cost_usd: 0,
              call_count: 0,
            },
          ],
          total_input_tokens: 0,
          total_output_tokens: 0,
        }}
      />
    );
    const split = screen.getByTestId('token-split');
    expect(split.textContent).toMatch(/0%/);
  });
});
