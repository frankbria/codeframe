/**
 * TokenUsageChart - Line chart for token usage over time (T131)
 *
 * Displays token usage trends with separate lines for input vs output tokens.
 * Includes date range selector and simple CSS-based visualization.
 *
 * Part of 015-review-polish Phase 5 (Sprint 10 - Metrics & Cost Tracking)
 */

import React, { useState, useEffect } from 'react';
import type { TokenUsageTimeSeries } from '../../types/metrics';
import { getTokenUsageTimeSeries } from '../../api/metrics';

interface TokenUsageChartProps {
  /** Project ID to display token usage for */
  projectId: number;
  /** Initial number of days to show (default 7) */
  defaultDays?: number;
}

/**
 * Format large numbers with comma separators
 */
function formatNumber(value: number): string {
  return value.toLocaleString('en-US');
}

/**
 * Format date for display
 */
function formatDate(dateStr: string): string {
  const date = new Date(dateStr);
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

/**
 * Calculate percentage of max value for bar height
 */
function getBarHeight(value: number, maxValue: number): number {
  if (maxValue === 0) return 0;
  return (value / maxValue) * 100;
}

/**
 * Token usage chart component with CSS-based visualization
 *
 * Shows:
 * - Bar chart of input vs output tokens over time
 * - Date range selector (7, 14, 30 days)
 * - Total tokens and cost summary
 */
export function TokenUsageChart({
  projectId,
  defaultDays = 7,
}: TokenUsageChartProps): JSX.Element {
  const [data, setData] = useState<TokenUsageTimeSeries[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [days, setDays] = useState<number>(defaultDays);

  // Calculate date range
  const endDate = new Date();
  const startDate = new Date();
  startDate.setDate(startDate.getDate() - days);

  // Fetch token usage time series
  useEffect(() => {
    let mounted = true;

    const loadData = async () => {
      setLoading(true);
      try {
        const result = await getTokenUsageTimeSeries(
          projectId,
          startDate.toISOString(),
          endDate.toISOString(),
          'day'
        );
        if (mounted) {
          setData(result);
          setError(null);
          setLoading(false);
        }
      } catch (err) {
        if (mounted) {
          setError(
            err instanceof Error
              ? err.message
              : 'Failed to load token usage data'
          );
          setLoading(false);
        }
      }
    };

    loadData();

    return () => {
      mounted = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, days]);

  // Calculate max value for scaling
  const maxTokens = Math.max(
    ...data.map((d) => Math.max(d.input_tokens, d.output_tokens)),
    1
  );

  // Calculate totals
  const totalInputTokens = data.reduce((sum, d) => sum + d.input_tokens, 0);
  const totalOutputTokens = data.reduce((sum, d) => sum + d.output_tokens, 0);
  const totalCost = data.reduce((sum, d) => sum + d.cost_usd, 0);

  if (loading) {
    return (
      <div className="p-6 bg-card rounded-lg border border-border">
        <h2 className="text-2xl font-bold text-foreground mb-4">Token Usage Over Time</h2>
        <p className="text-muted-foreground">Loading...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6 bg-card rounded-lg border border-border">
        <h2 className="text-2xl font-bold text-foreground mb-4">Token Usage Over Time</h2>
        <p className="text-destructive">Error: {error}</p>
      </div>
    );
  }

  if (data.length === 0) {
    return (
      <div className="p-6 bg-card rounded-lg border border-border">
        <h2 className="text-2xl font-bold text-foreground mb-4">Token Usage Over Time</h2>
        <p className="text-muted-foreground">No token usage data available</p>
      </div>
    );
  }

  return (
    <div className="p-6 bg-card rounded-lg border border-border space-y-6">
      <div className="flex justify-between items-center">
        <h2 className="text-2xl font-bold text-foreground">Token Usage Over Time</h2>

        {/* Date Range Selector */}
        <div className="date-range-selector flex gap-2">
          <button
            onClick={() => setDays(7)}
            className={`px-4 py-2 rounded ${
              days === 7
                ? 'bg-primary text-primary-foreground'
                : 'bg-muted text-foreground hover:bg-muted/80'
            }`}
          >
            7 Days
          </button>
          <button
            onClick={() => setDays(14)}
            className={`px-4 py-2 rounded ${
              days === 14
                ? 'bg-primary text-primary-foreground'
                : 'bg-muted text-foreground hover:bg-muted/80'
            }`}
          >
            14 Days
          </button>
          <button
            onClick={() => setDays(30)}
            className={`px-4 py-2 rounded ${
              days === 30
                ? 'bg-primary text-primary-foreground'
                : 'bg-muted text-foreground hover:bg-muted/80'
            }`}
          >
            30 Days
          </button>
        </div>
      </div>

      {/* Summary Stats */}
      <div className="summary-stats grid grid-cols-3 gap-4">
        <div className="stat-card p-4 bg-muted rounded-lg border border-border">
          <p className="text-sm text-muted-foreground">Total Input Tokens</p>
          <p className="text-2xl font-bold text-foreground">
            {formatNumber(totalInputTokens)}
          </p>
        </div>
        <div className="stat-card p-4 bg-muted rounded-lg border border-border">
          <p className="text-sm text-muted-foreground">Total Output Tokens</p>
          <p className="text-2xl font-bold text-foreground">
            {formatNumber(totalOutputTokens)}
          </p>
        </div>
        <div className="stat-card p-4 bg-secondary rounded-lg border border-border">
          <p className="text-sm text-muted-foreground">Total Cost</p>
          <p className="text-2xl font-bold text-foreground">
            ${totalCost.toFixed(2)}
          </p>
        </div>
      </div>

      {/* Chart */}
      <div className="chart-container">
        <div className="chart-legend flex justify-center gap-6 mb-4">
          <div className="flex items-center gap-2">
            <div className="w-4 h-4 bg-muted-foreground rounded"></div>
            <span className="text-sm text-muted-foreground">Input Tokens</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-4 h-4 bg-foreground rounded"></div>
            <span className="text-sm text-muted-foreground">Output Tokens</span>
          </div>
        </div>

        <div className="chart-area h-64 flex items-end gap-2 border-l border-b border-border p-4">
          {data.map((point, index) => (
            <div
              key={index}
              className="chart-bar-group flex-1 flex flex-col items-center gap-1"
            >
              {/* Output tokens bar (foreground) */}
              <div className="w-full flex flex-col items-center">
                <div
                  className="w-full bg-foreground hover:opacity-90 rounded-t transition-opacity"
                  style={{
                    height: `${getBarHeight(point.output_tokens, maxTokens)}%`,
                    minHeight: point.output_tokens > 0 ? '2px' : '0',
                  }}
                  title={`Output: ${formatNumber(point.output_tokens)}`}
                ></div>
              </div>

              {/* Input tokens bar (muted-foreground) */}
              <div className="w-full flex flex-col items-center">
                <div
                  className="w-full bg-muted-foreground hover:opacity-90 transition-opacity"
                  style={{
                    height: `${getBarHeight(point.input_tokens, maxTokens)}%`,
                    minHeight: point.input_tokens > 0 ? '2px' : '0',
                  }}
                  title={`Input: ${formatNumber(point.input_tokens)}`}
                ></div>
              </div>

              {/* Date label */}
              <div className="text-xs text-muted-foreground mt-2 whitespace-nowrap transform -rotate-45 origin-top-left">
                {formatDate(point.timestamp)}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
