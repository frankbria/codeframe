/**
 * ContextTierChart - Visual chart showing tier distribution (T065)
 *
 * Displays a simple bar chart showing tier distribution with color coding:
 * - HOT (red)
 * - WARM (yellow)
 * - COLD (blue)
 *
 * Part of 007-context-management Phase 7 (US5 - Context Visualization)
 */

import React from 'react';
import type { ContextStats } from '../../types/context';

interface ContextTierChartProps {
  /** Context statistics to visualize */
  stats: ContextStats;
}

/**
 * Simple bar chart showing tier distribution
 *
 * Shows percentages and color-coded bars for each tier.
 */
export function ContextTierChart({ stats }: ContextTierChartProps): JSX.Element {
  const totalItems = stats.total_count;

  // Calculate percentages
  const hotPercentage =
    totalItems > 0 ? (stats.hot_count / totalItems) * 100 : 0;
  const warmPercentage =
    totalItems > 0 ? (stats.warm_count / totalItems) * 100 : 0;
  const coldPercentage =
    totalItems > 0 ? (stats.cold_count / totalItems) * 100 : 0;

  return (
    <div className="p-6 bg-card rounded-lg border border-border space-y-4">
      <h4 className="text-lg font-semibold text-foreground">Tier Distribution</h4>

      {totalItems === 0 ? (
        <p className="text-muted-foreground text-center py-8">No context items</p>
      ) : (
        <>
          {/* Stacked horizontal bar */}
          <div className="w-full h-8 rounded-lg overflow-hidden flex">
            {stats.hot_count > 0 && (
              <div
                className="chart-bar hot bg-foreground hover:opacity-90 transition-opacity"
                style={{ width: `${hotPercentage}%` }}
                title={`HOT: ${stats.hot_count} items (${hotPercentage.toFixed(1)}%)`}
              />
            )}
            {stats.warm_count > 0 && (
              <div
                className="chart-bar warm bg-muted-foreground hover:opacity-90 transition-opacity"
                style={{ width: `${warmPercentage}%` }}
                title={`WARM: ${stats.warm_count} items (${warmPercentage.toFixed(1)}%)`}
              />
            )}
            {stats.cold_count > 0 && (
              <div
                className="chart-bar cold bg-muted hover:opacity-90 transition-opacity"
                style={{ width: `${coldPercentage}%` }}
                title={`COLD: ${stats.cold_count} items (${coldPercentage.toFixed(1)}%)`}
              />
            )}
          </div>

          {/* Legend */}
          <div className="grid grid-cols-3 gap-4 py-2">
            <div className="legend-item hot flex items-center gap-2">
              <span className="legend-color legend-indicator hot w-4 h-4 bg-foreground rounded"></span>
              <span className="legend-label text-sm text-foreground">
                HOT: {stats.hot_count} ({hotPercentage.toFixed(1)}%)
              </span>
            </div>

            <div className="legend-item warm flex items-center gap-2">
              <span className="legend-color legend-indicator warm w-4 h-4 bg-muted-foreground rounded"></span>
              <span className="legend-label text-sm text-foreground">
                WARM: {stats.warm_count} ({warmPercentage.toFixed(1)}%)
              </span>
            </div>

            <div className="legend-item cold flex items-center gap-2">
              <span className="legend-color legend-indicator cold w-4 h-4 bg-muted rounded"></span>
              <span className="legend-label text-sm text-foreground">
                COLD: {stats.cold_count} ({coldPercentage.toFixed(1)}%)
              </span>
            </div>
          </div>

          {/* Token breakdown */}
          <div className="token-breakdown pt-4 border-t border-border space-y-2">
            <p className="text-sm font-medium text-foreground">
              Token Distribution:
            </p>
            <ul className="space-y-1">
              <li className="tier-hot flex items-center gap-2 text-sm text-muted-foreground">
                <span className="w-3 h-3 bg-foreground rounded-sm"></span>
                HOT: {stats.hot_tokens.toLocaleString()} tokens (
                {stats.total_tokens > 0
                  ? ((stats.hot_tokens / stats.total_tokens) * 100).toFixed(1)
                  : 0}
                %)
              </li>
              <li className="tier-warm flex items-center gap-2 text-sm text-muted-foreground">
                <span className="w-3 h-3 bg-muted-foreground rounded-sm"></span>
                WARM: {stats.warm_tokens.toLocaleString()} tokens (
                {stats.total_tokens > 0
                  ? ((stats.warm_tokens / stats.total_tokens) * 100).toFixed(1)
                  : 0}
                %)
              </li>
              <li className="tier-cold flex items-center gap-2 text-sm text-muted-foreground">
                <span className="w-3 h-3 bg-muted rounded-sm"></span>
                COLD: {stats.cold_tokens.toLocaleString()} tokens (
                {stats.total_tokens > 0
                  ? ((stats.cold_tokens / stats.total_tokens) * 100).toFixed(1)
                  : 0}
                %)
              </li>
            </ul>
          </div>
        </>
      )}
    </div>
  );
}

export default ContextTierChart;
