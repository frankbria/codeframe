'use client';

import type { AgentCostsResponse } from '@/types';

interface AgentCostBarsProps {
  data: AgentCostsResponse;
  isLoading?: boolean;
}

function formatNumber(n: number): string {
  return n.toLocaleString('en-US');
}

function formatCost(value: number): string {
  return value.toLocaleString('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 4,
    maximumFractionDigits: 6,
  });
}

export function AgentCostBars({ data, isLoading }: AgentCostBarsProps) {
  if (isLoading) {
    return (
      <div data-testid="agent-bars-loading" className="h-40 animate-pulse rounded-xl bg-muted" />
    );
  }

  const agents = data.by_agent;
  if (agents.length === 0) {
    return (
      <div
        data-testid="agent-bars-empty"
        className="rounded-lg border border-dashed bg-muted/20 p-6 text-center text-sm text-muted-foreground"
      >
        No per-agent cost data yet.
      </div>
    );
  }

  // Find the max cost to scale bar widths. Guard against zero so the first
  // bar still shows a visible track.
  const maxCost = Math.max(...agents.map((a) => a.total_cost_usd), 0);
  const totalTokens = data.total_input_tokens + data.total_output_tokens;
  const inputPct = totalTokens > 0
    ? Math.round((data.total_input_tokens / totalTokens) * 100)
    : 0;

  return (
    <div data-testid="agent-bars" className="space-y-4">
      <ul className="space-y-2">
        {agents.map((agent) => {
          const widthPct = maxCost > 0
            ? Math.max(2, Math.round((agent.total_cost_usd / maxCost) * 100))
            : 2;
          return (
            <li
              key={agent.agent_id}
              data-testid={`agent-row-${agent.agent_id}`}
              className="grid grid-cols-[140px_1fr_auto] items-center gap-3 text-sm"
            >
              <span className="truncate font-mono text-xs" title={agent.agent_id}>
                {agent.agent_id}
              </span>
              <div className="h-3 overflow-hidden rounded-full bg-muted">
                <div
                  className="h-full rounded-full bg-primary/70 transition-all"
                  style={{ width: `${widthPct}%` }}
                  aria-label={`${agent.agent_id} cost bar`}
                  role="progressbar"
                  aria-valuenow={Math.round(agent.total_cost_usd * 10000) / 10000}
                  aria-valuemin={0}
                  aria-valuemax={Math.round(maxCost * 10000) / 10000}
                />
              </div>
              <span className="whitespace-nowrap text-right font-medium tabular-nums">
                {formatCost(agent.total_cost_usd)}
              </span>
            </li>
          );
        })}
      </ul>

      <div
        data-testid="token-split"
        className="flex flex-wrap items-center justify-between gap-3 rounded-lg border bg-muted/20 px-4 py-3 text-sm"
      >
        <div>
          <span className="text-muted-foreground">Input tokens:</span>{' '}
          <span className="font-medium tabular-nums">
            {formatNumber(data.total_input_tokens)}
          </span>
        </div>
        <div>
          <span className="text-muted-foreground">Output tokens:</span>{' '}
          <span className="font-medium tabular-nums">
            {formatNumber(data.total_output_tokens)}
          </span>
        </div>
        <div>
          <span className="text-muted-foreground">Input share:</span>{' '}
          <span className="font-medium tabular-nums">{inputPct}%</span>
        </div>
      </div>
    </div>
  );
}
