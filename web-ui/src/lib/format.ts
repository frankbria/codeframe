/**
 * Format an ISO date string as a human-readable relative time.
 * Returns strings like "just now", "5m ago", "2h ago", or "3d ago".
 */
export function formatRelativeTime(isoDate: string): string {
  const now = new Date();
  const date = new Date(isoDate);
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  if (diffMins < 1) return 'just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  const diffHours = Math.floor(diffMins / 60);
  if (diffHours < 24) return `${diffHours}h ago`;
  const diffDays = Math.floor(diffHours / 24);
  return `${diffDays}d ago`;
}

/**
 * Format a USD amount. The single currency formatter for the app — cost,
 * session and task surfaces must agree on the same figure.
 *
 * Defaults to exactly 4 fraction digits, the precision per-call LLM costs need.
 * Pass `maximumFractionDigits: 6` where sub-cent figures would otherwise round
 * to zero, or a fixed 2 where the amount is known to be dollars.
 */
export function formatUsd(
  value: number,
  {
    minimumFractionDigits = 4,
    maximumFractionDigits = minimumFractionDigits,
  }: { minimumFractionDigits?: number; maximumFractionDigits?: number } = {}
): string {
  return value.toLocaleString('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits,
    maximumFractionDigits,
  });
}

/** Format a plain count (tokens, rows) with thousands separators. */
export function formatCount(n: number): string {
  return n.toLocaleString('en-US');
}
