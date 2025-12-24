/**
 * AgentMetrics - Display metrics for a specific agent (T132)
 *
 * Shows agent-specific cost, token usage, and breakdowns by call type and model.
 *
 * Part of 015-review-polish Phase 5 (Sprint 10 - Metrics & Cost Tracking)
 */

import React, { useState, useEffect } from 'react';
import type { AgentMetrics as AgentMetricsType } from '../../types/metrics';
import { getAgentMetrics } from '../../api/metrics';

interface AgentMetricsProps {
  /** Agent ID to display metrics for */
  agentId: string;
  /** Optional project ID to filter by */
  projectId?: number;
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
 * Format datetime for display
 */
function formatDateTime(dateStr: string): string {
  const date = new Date(dateStr);
  return date.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

/**
 * Agent metrics component
 *
 * Shows:
 * - Total cost and token usage for the agent
 * - Breakdown by call type (task_execution, code_review, etc.)
 * - Breakdown by model
 * - First and last call timestamps
 */
export function AgentMetrics({
  agentId,
  projectId,
  refreshInterval = 30000,
}: AgentMetricsProps): JSX.Element {
  const [metrics, setMetrics] = useState<AgentMetricsType | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Fetch agent metrics on mount and set up auto-refresh
  useEffect(() => {
    let mounted = true;

    const loadMetrics = async () => {
      try {
        const data = await getAgentMetrics(agentId, projectId);
        if (mounted) {
          setMetrics(data);
          setError(null);
          setLoading(false);
        }
      } catch (err) {
        if (mounted) {
          setError(
            err instanceof Error
              ? err.message
              : 'Failed to load agent metrics'
          );
          setLoading(false);
        }
      }
    };

    // Initial load
    loadMetrics();

    // Set up auto-refresh
    const intervalId = setInterval(loadMetrics, refreshInterval);

    // Cleanup
    return () => {
      mounted = false;
      clearInterval(intervalId);
    };
  }, [agentId, projectId, refreshInterval]);

  if (loading) {
    return (
      <div className="p-6 bg-card rounded-lg border border-border">
        <h2 className="text-2xl font-bold text-foreground mb-4">Agent Metrics</h2>
        <p className="text-muted-foreground">Loading...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6 bg-card rounded-lg border border-border">
        <h2 className="text-2xl font-bold text-foreground mb-4">Agent Metrics</h2>
        <p className="text-red-600">Error: {error}</p>
      </div>
    );
  }

  if (!metrics) {
    return (
      <div className="p-6 bg-card rounded-lg border border-border">
        <h2 className="text-2xl font-bold text-foreground mb-4">Agent Metrics</h2>
        <p className="text-muted-foreground">No metrics available</p>
      </div>
    );
  }

  return (
    <div className="p-6 bg-card rounded-lg border border-border space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-foreground">Agent Metrics</h2>
        <p className="text-muted-foreground mt-1">Agent ID: {metrics.agent_id}</p>
        {metrics.project_id && (
          <p className="text-muted-foreground">Project ID: {metrics.project_id}</p>
        )}
      </div>

      {/* Summary Stats */}
      <div className="summary-stats grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="stat-card p-4 bg-muted rounded-lg border border-border">
          <p className="text-sm text-muted-foreground">Total Cost</p>
          <p className="text-2xl font-bold text-foreground">
            {formatCurrency(metrics.total_cost_usd)}
          </p>
        </div>
        <div className="stat-card p-4 bg-muted rounded-lg border border-border">
          <p className="text-sm text-muted-foreground">Input Tokens</p>
          <p className="text-2xl font-bold text-foreground">
            {formatNumber(metrics.total_input_tokens)}
          </p>
        </div>
        <div className="stat-card p-4 bg-muted rounded-lg border border-border">
          <p className="text-sm text-muted-foreground">Output Tokens</p>
          <p className="text-2xl font-bold text-foreground">
            {formatNumber(metrics.total_output_tokens)}
          </p>
        </div>
        <div className="stat-card p-4 bg-secondary rounded-lg border border-border">
          <p className="text-sm text-muted-foreground">Total Calls</p>
          <p className="text-2xl font-bold text-foreground">
            {formatNumber(metrics.total_calls)}
          </p>
        </div>
      </div>

      {/* Activity Period */}
      <div className="activity-period p-4 bg-muted rounded-lg border border-border">
        <p className="text-sm text-muted-foreground">
          <strong className="text-foreground">First Call:</strong> {formatDateTime(metrics.first_call_at)}
        </p>
        <p className="text-sm text-muted-foreground">
          <strong className="text-foreground">Last Call:</strong> {formatDateTime(metrics.last_call_at)}
        </p>
      </div>

      {/* Breakdown by Call Type */}
      <div className="call-type-breakdown">
        <h3 className="text-xl font-semibold text-foreground mb-3">Breakdown by Call Type</h3>
        {metrics.by_call_type.length === 0 ? (
          <p className="text-muted-foreground">No call type data available</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-border">
              <thead className="bg-muted">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                    Call Type
                  </th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-muted-foreground uppercase tracking-wider">
                    Cost
                  </th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-muted-foreground uppercase tracking-wider">
                    Calls
                  </th>
                </tr>
              </thead>
              <tbody className="bg-card divide-y divide-border">
                {metrics.by_call_type.map((item) => (
                  <tr key={item.call_type} className="hover:bg-muted/50">
                    <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-foreground">
                      {item.call_type.replace(/_/g, ' ').toUpperCase()}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-right text-foreground">
                      {formatCurrency(item.cost_usd)}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-right text-muted-foreground">
                      {formatNumber(item.call_count)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Breakdown by Model */}
      <div className="model-breakdown">
        <h3 className="text-xl font-semibold text-foreground mb-3">Breakdown by Model</h3>
        {metrics.by_model.length === 0 ? (
          <p className="text-muted-foreground">No model data available</p>
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
                {metrics.by_model.map((model) => (
                  <tr key={model.model_name} className="hover:bg-muted/50">
                    <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-foreground">
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

      {/* Last updated timestamp */}
      <div className="text-xs text-muted-foreground text-right">
        Auto-refreshes every {refreshInterval / 1000} seconds
      </div>
    </div>
  );
}
