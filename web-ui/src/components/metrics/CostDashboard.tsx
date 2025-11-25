/**
 * CostDashboard - Main container for cost metrics visualization (T130)
 *
 * Displays total project cost, breakdown by agent, and breakdown by model.
 * Auto-refreshes every 30 seconds.
 *
 * Part of 015-review-polish Phase 5 (Sprint 10 - Metrics & Cost Tracking)
 */

import React, { useState, useEffect } from 'react';
import type { CostBreakdown } from '../../types/metrics';
import { getProjectCosts } from '../../api/metrics';

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
 * Main cost dashboard panel
 *
 * Shows:
 * - Total project cost
 * - Cost breakdown by agent (table)
 * - Cost breakdown by model (table)
 * - Auto-refreshes periodically
 */
export function CostDashboard({
  projectId,
  refreshInterval = 30000,
}: CostDashboardProps): JSX.Element {
  const [breakdown, setBreakdown] = useState<CostBreakdown | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Fetch cost breakdown on mount and set up auto-refresh
  useEffect(() => {
    let mounted = true;

    const loadCosts = async () => {
      try {
        const data = await getProjectCosts(projectId);
        if (mounted) {
          setBreakdown(data);
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
    loadCosts();

    // Set up auto-refresh
    const intervalId = setInterval(loadCosts, refreshInterval);

    // Cleanup
    return () => {
      mounted = false;
      clearInterval(intervalId);
    };
  }, [projectId, refreshInterval]);

  if (loading) {
    return (
      <div className="cost-dashboard p-6 bg-white rounded-lg shadow">
        <h2 className="text-2xl font-bold mb-4">Cost Metrics</h2>
        <p className="text-gray-500">Loading...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="cost-dashboard p-6 bg-white rounded-lg shadow">
        <h2 className="text-2xl font-bold mb-4">Cost Metrics</h2>
        <p className="text-red-600">Error: {error}</p>
      </div>
    );
  }

  if (!breakdown) {
    return (
      <div className="cost-dashboard p-6 bg-white rounded-lg shadow">
        <h2 className="text-2xl font-bold mb-4">Cost Metrics</h2>
        <p className="text-gray-500">No cost data available</p>
      </div>
    );
  }

  return (
    <div className="cost-dashboard p-6 bg-white rounded-lg shadow space-y-6">
      <h2 className="text-2xl font-bold">Cost Metrics</h2>

      {/* Total Cost */}
      <div className="total-cost-section">
        <h3 className="text-xl font-semibold mb-2">Total Project Cost</h3>
        <p className="text-4xl font-bold text-green-600">
          {formatCurrency(breakdown.total_cost_usd)}
        </p>
      </div>

      {/* Cost by Agent */}
      <div className="agent-cost-section">
        <h3 className="text-xl font-semibold mb-3">Cost by Agent</h3>
        {breakdown.by_agent.length === 0 ? (
          <p className="text-gray-500">No agent data available</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Agent ID
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
                {breakdown.by_agent.map((agent) => (
                  <tr key={agent.agent_id} className="hover:bg-gray-50">
                    <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                      {agent.agent_id}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-right text-gray-900">
                      {formatCurrency(agent.cost_usd)}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-right text-gray-500">
                      {formatNumber(agent.call_count)}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-right text-gray-500">
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
      <div className="model-cost-section">
        <h3 className="text-xl font-semibold mb-3">Cost by Model</h3>
        {breakdown.by_model.length === 0 ? (
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
                {breakdown.by_model.map((model) => (
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
