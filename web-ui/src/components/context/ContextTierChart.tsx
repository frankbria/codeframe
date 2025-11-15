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
    <div className="context-tier-chart">
      <h4>Tier Distribution</h4>

      {totalItems === 0 ? (
        <p className="no-data">No context items</p>
      ) : (
        <>
          {/* Stacked horizontal bar */}
          <div className="chart-bar-container">
            {stats.hot_count > 0 && (
              <div
                className="chart-bar hot"
                style={{ width: `${hotPercentage}%` }}
                title={`HOT: ${stats.hot_count} items (${hotPercentage.toFixed(1)}%)`}
              />
            )}
            {stats.warm_count > 0 && (
              <div
                className="chart-bar warm"
                style={{ width: `${warmPercentage}%` }}
                title={`WARM: ${stats.warm_count} items (${warmPercentage.toFixed(1)}%)`}
              />
            )}
            {stats.cold_count > 0 && (
              <div
                className="chart-bar cold"
                style={{ width: `${coldPercentage}%` }}
                title={`COLD: ${stats.cold_count} items (${coldPercentage.toFixed(1)}%)`}
              />
            )}
          </div>

          {/* Legend */}
          <div className="chart-legend">
            <div className="legend-item hot">
              <span className="legend-color"></span>
              <span className="legend-label">
                HOT: {stats.hot_count} ({hotPercentage.toFixed(1)}%)
              </span>
            </div>

            <div className="legend-item warm">
              <span className="legend-color"></span>
              <span className="legend-label">
                WARM: {stats.warm_count} ({warmPercentage.toFixed(1)}%)
              </span>
            </div>

            <div className="legend-item cold">
              <span className="legend-color"></span>
              <span className="legend-label">
                COLD: {stats.cold_count} ({coldPercentage.toFixed(1)}%)
              </span>
            </div>
          </div>

          {/* Token breakdown */}
          <div className="token-breakdown">
            <p>
              <strong>Token Distribution:</strong>
            </p>
            <ul>
              <li className="hot">
                HOT: {stats.hot_tokens.toLocaleString()} tokens (
                {stats.total_tokens > 0
                  ? ((stats.hot_tokens / stats.total_tokens) * 100).toFixed(1)
                  : 0}
                %)
              </li>
              <li className="warm">
                WARM: {stats.warm_tokens.toLocaleString()} tokens (
                {stats.total_tokens > 0
                  ? ((stats.warm_tokens / stats.total_tokens) * 100).toFixed(1)
                  : 0}
                %)
              </li>
              <li className="cold">
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
