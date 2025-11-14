/**
 * ContextPanel - Main container component for context visualization (T064)
 *
 * Displays tier breakdown (HOT/WARM/COLD counts) and token usage for an agent.
 * Auto-refreshes every 5 seconds.
 *
 * Part of 007-context-management Phase 7 (US5 - Context Visualization)
 */

import React, { useState, useEffect } from 'react';
import type { ContextStats } from '../../types/context';
import { fetchContextStats } from '../../api/context';

interface ContextPanelProps {
  /** Agent ID to display context for */
  agentId: string;
  /** Project ID the agent is working on */
  projectId: number;
  /** Auto-refresh interval in milliseconds (default 5000 = 5 seconds) */
  refreshInterval?: number;
}

/**
 * Main context visualization panel
 *
 * Shows:
 * - Tier breakdown (HOT/WARM/COLD counts)
 * - Total token usage with percentage (X / 180k tokens)
 * - Auto-refreshes periodically
 */
export function ContextPanel({
  agentId,
  projectId,
  refreshInterval = 5000,
}: ContextPanelProps): JSX.Element {
  const [stats, setStats] = useState<ContextStats | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Fetch stats on mount and set up auto-refresh
  useEffect(() => {
    let mounted = true;

    const loadStats = async () => {
      try {
        const data = await fetchContextStats(agentId, projectId);
        if (mounted) {
          setStats(data);
          setError(null);
          setLoading(false);
        }
      } catch (err) {
        if (mounted) {
          setError(err instanceof Error ? err.message : 'Failed to load context stats');
          setLoading(false);
        }
      }
    };

    // Initial load
    loadStats();

    // Set up auto-refresh
    const intervalId = setInterval(loadStats, refreshInterval);

    // Cleanup
    return () => {
      mounted = false;
      clearInterval(intervalId);
    };
  }, [agentId, projectId, refreshInterval]);

  if (loading) {
    return (
      <div className="context-panel">
        <h3>Context Overview</h3>
        <p>Loading...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="context-panel error">
        <h3>Context Overview</h3>
        <p className="error-message">{error}</p>
      </div>
    );
  }

  if (!stats) {
    return (
      <div className="context-panel">
        <h3>Context Overview</h3>
        <p>No data available</p>
      </div>
    );
  }

  const tokenLimit = 180000;
  const tokenPercentage = stats.token_usage_percentage;

  return (
    <div className="context-panel">
      <h3>Context Overview - {agentId}</h3>

      {/* Token Usage Section */}
      <div className="token-usage-section">
        <h4>Token Usage</h4>
        <div className="token-bar-container">
          <div
            className="token-bar"
            style={{ width: `${Math.min(tokenPercentage, 100)}%` }}
            aria-valuenow={tokenPercentage}
            aria-valuemin={0}
            aria-valuemax={100}
          />
        </div>
        <p className="token-usage-text">
          {stats.total_tokens.toLocaleString()} / {tokenLimit.toLocaleString()} tokens
          ({tokenPercentage.toFixed(1)}%)
        </p>
      </div>

      {/* Tier Breakdown Section */}
      <div className="tier-breakdown-section">
        <h4>Tier Breakdown</h4>
        <div className="tier-stats">
          <div className="tier-stat hot">
            <span className="tier-label">HOT</span>
            <span className="tier-count">{stats.hot_count}</span>
            <span className="tier-tokens">
              {stats.hot_tokens.toLocaleString()} tokens
            </span>
          </div>

          <div className="tier-stat warm">
            <span className="tier-label">WARM</span>
            <span className="tier-count">{stats.warm_count}</span>
            <span className="tier-tokens">
              {stats.warm_tokens.toLocaleString()} tokens
            </span>
          </div>

          <div className="tier-stat cold">
            <span className="tier-label">COLD</span>
            <span className="tier-count">{stats.cold_count}</span>
            <span className="tier-tokens">
              {stats.cold_tokens.toLocaleString()} tokens
            </span>
          </div>
        </div>

        <div className="total-items">
          <strong>Total Items:</strong> {stats.total_count}
        </div>
      </div>

      {/* Last Updated */}
      <div className="last-updated">
        <small>
          Last updated: {new Date(stats.calculated_at).toLocaleTimeString()}
        </small>
      </div>
    </div>
  );
}

export default ContextPanel;
