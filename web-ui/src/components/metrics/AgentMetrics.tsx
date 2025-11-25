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
      <div className="agent-metrics p-6 bg-white rounded-lg shadow">
        <h2 className="text-2xl font-bold mb-4">Agent Metrics</h2>
        <p className="text-gray-500">Loading...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="agent-metrics p-6 bg-white rounded-lg shadow">
        <h2 className="text-2xl font-bold mb-4">Agent Metrics</h2>
        <p className="text-red-600">Error: {error}</p>
      </div>
    );
  }

  if (!metrics) {
    return (
      <div className="agent-metrics p-6 bg-white rounded-lg shadow">
        <h2 className="text-2xl font-bold mb-4">Agent Metrics</h2>
        <p className="text-gray-500">No metrics available</p>
      </div>
    );
  }

  return (
    <div className="agent-metrics p-6 bg-white rounded-lg shadow space-y-6">
      <div>
        <h2 className="text-2xl font-bold">Agent Metrics</h2>
        <p className="text-gray-600 mt-1">Agent ID: {metrics.agent_id}</p>
        {metrics.project_id && (
          <p className="text-gray-600">Project ID: {metrics.project_id}</p>
        )}
      </div>

      {/* Summary Stats */}
      <div className="summary-stats grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="stat-card p-4 bg-green-50 rounded">
          <p className="text-sm text-gray-600">Total Cost</p>
          <p className="text-2xl font-bold text-green-600">
            {formatCurrency(metrics.total_cost_usd)}
          </p>
        </div>
        <div className="stat-card p-4 bg-blue-50 rounded">
          <p className="text-sm text-gray-600">Input Tokens</p>
          <p className="text-2xl font-bold text-blue-600">
            {formatNumber(metrics.total_input_tokens)}
          </p>
        </div>
        <div className="stat-card p-4 bg-purple-50 rounded">
          <p className="text-sm text-gray-600">Output Tokens</p>
          <p className="text-2xl font-bold text-purple-600">
            {formatNumber(metrics.total_output_tokens)}
          </p>
        </div>
        <div className="stat-card p-4 bg-orange-50 rounded">
          <p className="text-sm text-gray-600">Total Calls</p>
          <p className="text-2xl font-bold text-orange-600">
            {formatNumber(metrics.total_calls)}
          </p>
        </div>
      </div>

      {/* Activity Period */}
      <div className="activity-period p-4 bg-gray-50 rounded">
        <p className="text-sm text-gray-600">
          <strong>First Call:</strong> {formatDateTime(metrics.first_call_at)}
        </p>
        <p className="text-sm text-gray-600">
          <strong>Last Call:</strong> {formatDateTime(metrics.last_call_at)}
        </p>
      </div>

      {/* Breakdown by Call Type */}
      <div className="call-type-breakdown">
        <h3 className="text-xl font-semibold mb-3">Breakdown by Call Type</h3>
        {metrics.by_call_type.length === 0 ? (
          <p className="text-gray-500">No call type data available</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Call Type
                  </th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Cost
                  </th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Calls
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {metrics.by_call_type.map((item) => (
                  <tr key={item.call_type} className="hover:bg-gray-50">
                    <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                      {item.call_type.replace(/_/g, ' ').toUpperCase()}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-right text-gray-900">
                      {formatCurrency(item.cost_usd)}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-right text-gray-500">
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
        <h3 className="text-xl font-semibold mb-3">Breakdown by Model</h3>
        {metrics.by_model.length === 0 ? (
          <p className="text-gray-500">No model data available</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Model Name
                  </th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Cost
                  </th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Calls
                  </th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Total Tokens
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {metrics.by_model.map((model) => (
                  <tr key={model.model_name} className="hover:bg-gray-50">
                    <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                      {model.model_name}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-right text-gray-900">
                      {formatCurrency(model.cost_usd)}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-right text-gray-500">
                      {formatNumber(model.call_count)}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-right text-gray-500">
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
      <div className="text-xs text-gray-400 text-right">
        Auto-refreshes every {refreshInterval / 1000} seconds
      </div>
    </div>
  );
}
