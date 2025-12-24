/**
 * CostDashboard - Main container for cost metrics visualization (T130)
 *
 * Displays total project cost, breakdown by agent, and breakdown by model.
 * Auto-refreshes every 30 seconds.
 *
 * Part of 015-review-polish Phase 5 (Sprint 10 - Metrics & Cost Tracking)
 */

import React, { useState, useEffect, useMemo } from 'react';
import { Download01Icon } from '@hugeicons/react';
import { format, subDays } from 'date-fns';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';
import type {
  CostBreakdown,
  TokenUsage,
  TokenUsageTimeSeries,
} from '../../types/metrics';
import {
  getProjectCosts,
  getProjectTokens,
  getTokenUsageTimeSeries,
} from '../../api/metrics';

interface CostDashboardProps {
  /** Project ID to display costs for */
  projectId: number;
  /** Auto-refresh interval in milliseconds (default 30000 = 30 seconds) */
  refreshInterval?: number;
}

/**
 * Format currency value with $ and 2 decimal places
 */
function formatCurrency(value: number): string {
  return `$${value.toFixed(2)}`;
}

/**
 * Format large numbers with comma separators
 */
function formatNumber(value: number): string {
  return value.toLocaleString('en-US');
}

/**
 * Model pricing (per million tokens)
 */
const MODEL_PRICING = {
  'claude-sonnet-4-5': { input: 3.0, output: 15.0 },
  'claude-opus-4': { input: 15.0, output: 75.0 },
  'claude-haiku-4': { input: 0.8, output: 4.0 },
};

/**
 * Date range options
 */
type DateRangeOption = 'last-7-days' | 'last-30-days' | 'all-time';

/**
 * Task cost aggregation
 */
interface TaskCost {
  task_id: number;
  cost_usd: number;
  total_tokens: number;
}

/**
 * Calculate cost breakdown by task
 */
function aggregateCostsByTask(tokens: TokenUsage[]): TaskCost[] {
  const taskMap = new Map<number, TaskCost>();

  tokens.forEach((record) => {
    if (record.task_id !== undefined && record.task_id !== null) {
      const existing = taskMap.get(record.task_id);
      if (existing) {
        existing.cost_usd += record.estimated_cost_usd;
        existing.total_tokens += record.input_tokens + record.output_tokens;
      } else {
        taskMap.set(record.task_id, {
          task_id: record.task_id,
          cost_usd: record.estimated_cost_usd,
          total_tokens: record.input_tokens + record.output_tokens,
        });
      }
    }
  });

  return Array.from(taskMap.values()).sort((a, b) => b.cost_usd - a.cost_usd);
}

/**
 * Export data to CSV
 */
function exportToCSV(
  breakdown: CostBreakdown,
  tokens: TokenUsage[],
  taskCosts: TaskCost[],
  projectId: number
): void {
  const rows: string[] = [];

  // Header
  rows.push('Category,Name,Cost (USD),Tokens,Calls');

  // Total summary
  const tokensArray = Array.isArray(tokens) ? tokens : [];
  const totalTokens = tokensArray.reduce(
    (sum, t) => sum + t.input_tokens + t.output_tokens,
    0
  );
  rows.push(
    `Total,Project ${projectId},${breakdown.total_cost_usd.toFixed(4)},${totalTokens},${tokens.length}`
  );

  // By agent
  breakdown.by_agent.forEach((agent) => {
    rows.push(
      `Agent,${agent.agent_id},${agent.cost_usd.toFixed(4)},${agent.total_tokens},${agent.call_count}`
    );
  });

  // By model
  breakdown.by_model.forEach((model) => {
    rows.push(
      `Model,${model.model_name},${model.cost_usd.toFixed(4)},${model.total_tokens},${model.call_count}`
    );
  });

  // By task
  taskCosts.forEach((task) => {
    rows.push(
      `Task,Task #${task.task_id},${task.cost_usd.toFixed(4)},${task.total_tokens},-`
    );
  });

  const csvContent = rows.join('\n');
  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `cost-report-${projectId}-${format(new Date(), 'yyyy-MM-dd')}.csv`;
  link.click();
  URL.revokeObjectURL(url);
}

/**
 * Main cost dashboard panel
 *
 * Shows:
 * - Token usage statistics (input/output/total)
 * - Date range filter
 * - CSV export button
 * - Cost trend chart
 * - Total project cost
 * - Cost breakdown by agent (table)
 * - Cost breakdown by model (table)
 * - Model pricing information
 * - Cost per task table
 * - Auto-refreshes periodically
 */
export function CostDashboard({
  projectId,
  refreshInterval = 30000,
}: CostDashboardProps): JSX.Element {
  const [breakdown, setBreakdown] = useState<CostBreakdown | null>(null);
  const [tokens, setTokens] = useState<TokenUsage[]>([]);
  const [timeSeries, setTimeSeries] = useState<TokenUsageTimeSeries[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [dateRange, setDateRange] = useState<DateRangeOption>('all-time');

  // Calculate date filter based on selected range
  const dateFilter = useMemo(() => {
    const now = new Date();
    switch (dateRange) {
      case 'last-7-days':
        return {
          start_date: format(subDays(now, 7), 'yyyy-MM-dd'),
          end_date: format(now, 'yyyy-MM-dd'),
        };
      case 'last-30-days':
        return {
          start_date: format(subDays(now, 30), 'yyyy-MM-dd'),
          end_date: format(now, 'yyyy-MM-dd'),
        };
      case 'all-time':
      default:
        return { start_date: undefined, end_date: undefined };
    }
  }, [dateRange]);

  // Calculate token statistics
  const tokenStats = useMemo(() => {
    // Defensive check: ensure tokens is an array
    const tokensArray = Array.isArray(tokens) ? tokens : [];
    const inputTokens = tokensArray.reduce((sum, t) => sum + t.input_tokens, 0);
    const outputTokens = tokensArray.reduce((sum, t) => sum + t.output_tokens, 0);
    return {
      inputTokens,
      outputTokens,
      totalTokens: inputTokens + outputTokens,
    };
  }, [tokens]);

  // Calculate task costs
  const taskCosts = useMemo(() => {
    // Defensive check: ensure tokens is an array
    const tokensArray = Array.isArray(tokens) ? tokens : [];
    return aggregateCostsByTask(tokensArray);
  }, [tokens]);

  // Fetch cost breakdown on mount and set up auto-refresh
  useEffect(() => {
    let mounted = true;

    const loadData = async () => {
      try {
        setLoading(true);

        // Fetch all data in parallel
        const [costsData, tokensData, timeSeriesData] = await Promise.all([
          getProjectCosts(projectId),
          getProjectTokens(
            projectId,
            dateFilter.start_date,
            dateFilter.end_date,
            1000
          ),
          dateFilter.start_date && dateFilter.end_date
            ? getTokenUsageTimeSeries(
                projectId,
                dateFilter.start_date,
                dateFilter.end_date,
                'day'
              )
            : Promise.resolve([]),
        ]);

        if (mounted) {
          setBreakdown(costsData);
          setTokens(tokensData);
          setTimeSeries(timeSeriesData);
          setError(null);
          setLoading(false);
        }
      } catch (err) {
        if (mounted) {
          setError(
            err instanceof Error ? err.message : 'Failed to load cost metrics'
          );
          setLoading(false);
        }
      }
    };

    // Initial load
    loadData();

    // Set up auto-refresh
    const intervalId = setInterval(loadData, refreshInterval);

    // Cleanup
    return () => {
      mounted = false;
      clearInterval(intervalId);
    };
  }, [projectId, refreshInterval, dateFilter]);

  // Handle CSV export
  const handleExportCSV = () => {
    if (breakdown) {
      exportToCSV(breakdown, tokens, taskCosts, projectId);
    }
  };

  if (loading) {
    return (
      <div className="p-6 bg-card rounded-lg border border-border">
        <h2 className="text-2xl font-bold text-foreground mb-4">Cost Metrics</h2>
        <p className="text-muted-foreground">Loading...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6 bg-card rounded-lg border border-border">
        <h2 className="text-2xl font-bold text-foreground mb-4">Cost Metrics</h2>
        <p className="text-red-600">Error: {error}</p>
      </div>
    );
  }

  if (!breakdown) {
    return (
      <div className="p-6 bg-card rounded-lg border border-border">
        <h2 className="text-2xl font-bold text-foreground mb-4">Cost Metrics</h2>
        <p className="text-muted-foreground">No cost data available</p>
      </div>
    );
  }

  return (
    <div
      className="p-6 bg-card rounded-lg border border-border space-y-6"
      data-testid="cost-dashboard"
    >
      {/* Header with filters and export */}
      <div className="flex justify-between items-center">
        <h2 className="text-2xl font-bold text-foreground">Cost Metrics</h2>
        <div className="flex gap-4 items-center">
          {/* Date range filter */}
          <select
            data-testid="date-range-filter"
            value={dateRange}
            onChange={(e) => setDateRange(e.target.value as DateRangeOption)}
            className="px-4 py-2 border border-border rounded-md bg-background text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
          >
            <option value="last-7-days">Last 7 days</option>
            <option value="last-30-days">Last 30 days</option>
            <option value="all-time">All time</option>
          </select>

          {/* Export CSV button */}
          <button
            data-testid="export-csv-button"
            onClick={handleExportCSV}
            className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-md hover:bg-primary/90 transition-colors"
          >
            <Download01Icon size={16} />
            Export CSV
          </button>
        </div>
      </div>

      {/* Token Usage Statistics */}
      <div className="token-stats-section" data-testid="token-stats">
        <h3 className="text-xl font-semibold text-foreground mb-3">Token Usage Statistics</h3>
        <div className="grid grid-cols-3 gap-4">
          <div className="bg-muted p-4 rounded-lg border border-border">
            <p className="text-sm text-muted-foreground mb-1">Input Tokens</p>
            <p
              className="text-2xl font-bold text-foreground"
              data-testid="input-tokens"
            >
              {formatNumber(tokenStats.inputTokens)}
            </p>
          </div>
          <div className="bg-muted p-4 rounded-lg border border-border">
            <p className="text-sm text-muted-foreground mb-1">Output Tokens</p>
            <p
              className="text-2xl font-bold text-foreground"
              data-testid="output-tokens"
            >
              {formatNumber(tokenStats.outputTokens)}
            </p>
          </div>
          <div className="bg-secondary p-4 rounded-lg border border-border">
            <p className="text-sm text-muted-foreground mb-1">Total Tokens</p>
            <p
              className="text-2xl font-bold text-foreground"
              data-testid="total-tokens"
            >
              {formatNumber(tokenStats.totalTokens)}
            </p>
          </div>
        </div>
      </div>

      {/* Cost Trend Chart */}
      {timeSeries.length > 0 ? (
        <div className="trend-chart-section" data-testid="cost-trend-chart">
          <h3 className="text-xl font-semibold text-foreground mb-3">Cost Trend</h3>
          <div data-testid="trend-chart-data">
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={timeSeries}>
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                <XAxis
                  dataKey="timestamp"
                  tickFormatter={(value) => format(new Date(value), 'MMM dd')}
                  data-testid="chart-x-axis"
                  stroke="hsl(var(--muted-foreground))"
                />
                <YAxis stroke="hsl(var(--muted-foreground))" />
                <Tooltip
                  formatter={(value: number) => formatCurrency(value)}
                  labelFormatter={(label) =>
                    format(new Date(label), 'MMM dd, yyyy')
                  }
                  contentStyle={{
                    backgroundColor: 'hsl(var(--card))',
                    border: '1px solid hsl(var(--border))',
                    borderRadius: '0.5rem',
                  }}
                />
                <Legend />
                <Line
                  type="monotone"
                  dataKey="cost_usd"
                  stroke="hsl(var(--foreground))"
                  strokeWidth={2}
                  name="Cost (USD)"
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      ) : (
        <div className="trend-chart-section" data-testid="cost-trend-chart">
          <h3 className="text-xl font-semibold text-foreground mb-3">Cost Trend</h3>
          <div className="bg-muted p-4 rounded-lg text-center text-muted-foreground border border-border">
            No time series data available for selected range
          </div>
        </div>
      )}

      {/* Total Cost */}
      <div className="total-cost-section">
        <h3 className="text-xl font-semibold text-foreground mb-2">Total Project Cost</h3>
        <p
          className="text-4xl font-bold text-foreground"
          data-testid="total-cost-display"
        >
          {formatCurrency(breakdown.total_cost_usd)}
        </p>
      </div>

      {/* Cost by Agent */}
      <div className="agent-cost-section" data-testid="cost-by-agent">
        <h3 className="text-xl font-semibold text-foreground mb-3">Cost by Agent</h3>
        {breakdown.by_agent.length === 0 ? (
          <p className="text-muted-foreground" data-testid="agent-cost-empty">
            No agent data available
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-border">
              <thead className="bg-muted">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                    Agent ID
                  </th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-muted-foreground uppercase tracking-wider">
                    Cost
                  </th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-muted-foreground uppercase tracking-wider">
                    Calls
                  </th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-muted-foreground uppercase tracking-wider">
                    Total Tokens
                  </th>
                </tr>
              </thead>
              <tbody className="bg-card divide-y divide-border">
                {breakdown.by_agent.map((agent) => (
                  <tr
                    key={agent.agent_id}
                    className="hover:bg-muted/50"
                    data-testid={`agent-cost-${agent.agent_id}`}
                  >
                    <td
                      className="px-6 py-4 whitespace-nowrap text-sm font-medium text-foreground"
                      data-testid="agent-name"
                    >
                      {agent.agent_id}
                    </td>
                    <td
                      className="px-6 py-4 whitespace-nowrap text-sm text-right text-foreground"
                      data-testid="agent-cost"
                    >
                      {formatCurrency(agent.cost_usd)}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-right text-muted-foreground">
                      {formatNumber(agent.call_count)}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-right text-muted-foreground">
                      {formatNumber(agent.total_tokens)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Cost by Model */}
      <div className="model-cost-section" data-testid="cost-by-model">
        <h3 className="text-xl font-semibold text-foreground mb-3">Cost by Model</h3>
        {breakdown.by_model.length === 0 ? (
          <p className="text-muted-foreground" data-testid="model-cost-empty">
            No model data available
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-border">
              <thead className="bg-muted">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                    Model Name
                  </th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-muted-foreground uppercase tracking-wider">
                    Cost
                  </th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-muted-foreground uppercase tracking-wider">
                    Calls
                  </th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-muted-foreground uppercase tracking-wider">
                    Total Tokens
                  </th>
                </tr>
              </thead>
              <tbody className="bg-card divide-y divide-border">
                {breakdown.by_model.map((model) => (
                  <tr
                    key={model.model_name}
                    className="hover:bg-muted/50"
                    data-testid={`model-cost-${model.model_name}`}
                  >
                    <td
                      className="px-6 py-4 whitespace-nowrap text-sm font-medium text-foreground"
                      data-testid="model-name"
                    >
                      {model.model_name}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-right text-foreground">
                      {formatCurrency(model.cost_usd)}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-right text-muted-foreground">
                      {formatNumber(model.call_count)}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-right text-muted-foreground">
                      {formatNumber(model.total_tokens)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Model Pricing Information */}
      <div className="pricing-info-section" data-testid="model-pricing-info">
        <h3 className="text-xl font-semibold text-foreground mb-3">Model Pricing</h3>
        <div className="bg-muted p-4 rounded-lg border border-border space-y-2">
          {Object.entries(MODEL_PRICING).map(([modelKey, pricing]) => (
            <div
              key={modelKey}
              className="text-sm text-foreground"
              data-testid={`pricing-${modelKey}`}
            >
              <span className="font-medium">{modelKey}:</span> $
              {pricing.input.toFixed(2)} / ${pricing.output.toFixed(2)} per
              MTok (input/output)
            </div>
          ))}
          <p className="text-xs text-muted-foreground mt-2">
            Pricing as of November 2025 from Anthropic
          </p>
        </div>
      </div>

      {/* Cost Per Task Table */}
      <div className="task-cost-section" data-testid="cost-per-task-table">
        <h3 className="text-xl font-semibold text-foreground mb-3">Cost by Task</h3>
        {taskCosts.length === 0 ? (
          <p className="text-muted-foreground" data-testid="task-cost-empty">
            No task data available
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-border">
              <thead className="bg-muted">
                <tr>
                  <th
                    className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider"
                    data-testid="task-column-header"
                  >
                    Task ID
                  </th>
                  <th
                    className="px-6 py-3 text-right text-xs font-medium text-muted-foreground uppercase tracking-wider"
                    data-testid="cost-column-header"
                  >
                    Cost
                  </th>
                  <th
                    className="px-6 py-3 text-right text-xs font-medium text-muted-foreground uppercase tracking-wider"
                    data-testid="tokens-column-header"
                  >
                    Total Tokens
                  </th>
                </tr>
              </thead>
              <tbody className="bg-card divide-y divide-border">
                {taskCosts.map((task) => (
                  <tr
                    key={task.task_id}
                    className="hover:bg-muted/50"
                    data-testid={`task-cost-row-${task.task_id}`}
                  >
                    <td
                      className="px-6 py-4 whitespace-nowrap text-sm font-medium text-foreground"
                      data-testid="task-description"
                    >
                      Task #{task.task_id}
                    </td>
                    <td
                      className="px-6 py-4 whitespace-nowrap text-sm text-right text-foreground"
                      data-testid="task-cost"
                    >
                      {formatCurrency(task.cost_usd)}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-right text-muted-foreground">
                      {formatNumber(task.total_tokens)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Last updated timestamp */}
      <div className="text-xs text-muted-foreground text-right">
        Auto-refreshes every {refreshInterval / 1000} seconds
      </div>
    </div>
  );
}

export default React.memo(CostDashboard);
