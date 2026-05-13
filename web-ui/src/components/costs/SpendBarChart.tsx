'use client';

import { format, parseISO } from 'date-fns';
import type { DailyCostPoint } from '@/types';

interface SpendBarChartProps {
  daily: DailyCostPoint[];
  days: number;
}

const CHART_HEIGHT = 220;
const CHART_PADDING_TOP = 12;
const Y_AXIS_WIDTH = 56;
const X_AXIS_HEIGHT = 28;

function formatCurrency(value: number): string {
  return value.toLocaleString('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 4,
    maximumFractionDigits: 4,
  });
}

export function SpendBarChart({ daily, days }: SpendBarChartProps) {
  const hasData = daily.length > 0 && daily.some((d) => d.cost_usd > 0);

  if (!hasData) {
    return (
      <div
        data-testid="spend-chart-empty"
        className="flex h-56 items-center justify-center rounded-md border border-dashed border-border bg-muted/30 text-sm text-muted-foreground"
      >
        No spend data for this period.
      </div>
    );
  }

  const maxCost = Math.max(...daily.map((d) => d.cost_usd), 0.0001);
  const tickValues = [maxCost, maxCost * 0.5, 0];

  // Label every Nth bar so the x-axis stays legible at 30/90 days.
  const labelStride = days >= 60 ? 14 : days >= 14 ? 5 : 1;

  return (
    <div
      data-testid="spend-chart"
      className="w-full overflow-x-auto rounded-md border bg-card p-4"
    >
      <div className="flex">
        {/* Y axis */}
        <div
          aria-hidden="true"
          className="flex flex-col justify-between pr-2 text-right text-[10px] text-muted-foreground"
          style={{ width: Y_AXIS_WIDTH, height: CHART_HEIGHT }}
        >
          {tickValues.map((v) => (
            <span key={v}>{formatCurrency(v)}</span>
          ))}
        </div>

        {/* Bars */}
        <div className="flex flex-1 flex-col">
          <div
            className="relative flex items-end gap-px"
            style={{ height: CHART_HEIGHT }}
            role="img"
            aria-label={`Daily spend bar chart for the last ${days} days`}
          >
            {daily.map((point) => {
              const ratio = maxCost > 0 ? point.cost_usd / maxCost : 0;
              const barHeight = Math.max(
                ratio * (CHART_HEIGHT - CHART_PADDING_TOP),
                point.cost_usd > 0 ? 2 : 0
              );
              return (
                <div
                  key={point.date}
                  data-testid={`bar-${point.date}`}
                  title={`${point.date}: ${formatCurrency(point.cost_usd)}`}
                  className="flex-1 rounded-t bg-primary/80 transition-colors hover:bg-primary"
                  style={{ height: `${barHeight}px`, minWidth: 4 }}
                />
              );
            })}
          </div>

          {/* X axis labels */}
          <div
            aria-hidden="true"
            className="flex gap-px pt-1 text-[10px] text-muted-foreground"
            style={{ height: X_AXIS_HEIGHT }}
          >
            {daily.map((point, idx) => {
              const showLabel = idx % labelStride === 0 || idx === daily.length - 1;
              return (
                <span
                  key={point.date}
                  className="flex-1 truncate text-center"
                  style={{ minWidth: 4 }}
                >
                  {showLabel ? format(parseISO(point.date), 'MMM d') : ''}
                </span>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
