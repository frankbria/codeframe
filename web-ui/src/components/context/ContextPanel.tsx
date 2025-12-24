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
      <div className="p-6 bg-card rounded-lg border border-border">
        <h3 className="text-xl font-semibold text-foreground mb-2">Context Overview</h3>
        <p className="text-muted-foreground">Loading...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6 bg-card rounded-lg border border-border">
        <h3 className="text-xl font-semibold text-foreground mb-2">Context Overview</h3>
        <p className="text-red-600">{error}</p>
      </div>
    );
  }

  if (!stats) {
    return (
      <div className="p-6 bg-card rounded-lg border border-border">
        <h3 className="text-xl font-semibold text-foreground mb-2">Context Overview</h3>
        <p className="text-muted-foreground">No data available</p>
      </div>
    );
  }

  const tokenLimit = 180000;
  const tokenPercentage = stats.token_usage_percentage;

  return (
    <div className="p-6 bg-card rounded-lg border border-border space-y-6">
      <h3 className="text-xl font-semibold text-foreground">Context Overview - {agentId}</h3>

      {/* Token Usage Section */}
      <div className="space-y-2">
        <h4 className="text-lg font-medium text-foreground">Token Usage</h4>
        <div className="w-full h-4 bg-muted rounded-full overflow-hidden">
          <div
            className="h-full bg-secondary transition-all duration-300"
            style={{ width: `${Math.min(tokenPercentage, 100)}%` }}
            aria-valuenow={tokenPercentage}
            aria-valuemin={0}
            aria-valuemax={100}
          />
        </div>
        <p className="text-sm text-muted-foreground">
          {stats.total_tokens.toLocaleString()} / {tokenLimit.toLocaleString()} tokens
          ({tokenPercentage.toFixed(1)}%)
        </p>
      </div>

      {/* Tier Breakdown Section */}
      <div className="space-y-3">
        <h4 className="text-lg font-medium text-foreground">Tier Breakdown</h4>
        <div className="grid grid-cols-3 gap-4">
          <div className="p-4 bg-muted rounded-lg border border-border">
            <span className="block text-xs font-medium text-muted-foreground uppercase mb-1">HOT</span>
            <span className="block text-2xl font-bold text-foreground">{stats.hot_count}</span>
            <span className="block text-xs text-muted-foreground mt-1">
              {stats.hot_tokens.toLocaleString()} tokens
            </span>
          </div>

          <div className="p-4 bg-muted rounded-lg border border-border">
            <span className="block text-xs font-medium text-muted-foreground uppercase mb-1">WARM</span>
            <span className="block text-2xl font-bold text-foreground">{stats.warm_count}</span>
            <span className="block text-xs text-muted-foreground mt-1">
              {stats.warm_tokens.toLocaleString()} tokens
            </span>
          </div>

          <div className="p-4 bg-muted rounded-lg border border-border">
            <span className="block text-xs font-medium text-muted-foreground uppercase mb-1">COLD</span>
            <span className="block text-2xl font-bold text-foreground">{stats.cold_count}</span>
            <span className="block text-xs text-muted-foreground mt-1">
              {stats.cold_tokens.toLocaleString()} tokens
            </span>
          </div>
        </div>

        <div className="pt-2 border-t border-border">
          <span className="text-sm font-medium text-foreground">Total Items: </span>
          <span className="text-sm text-muted-foreground">{stats.total_count}</span>
        </div>
      </div>

      {/* Last Updated */}
      <div className="text-xs text-muted-foreground text-right">
        Last updated: {new Date(stats.calculated_at).toLocaleTimeString()}
      </div>
    </div>
  );
}

export default ContextPanel;
