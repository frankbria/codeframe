import { formatDistanceToNow, formatDistanceToNowStrict } from 'date-fns';

/**
 * The single set of display formatters for the app. Two surfaces showing the
 * same value must agree on it (#971, #1195), so every displayed timestamp,
 * count and USD amount goes through here — the guard test in
 * `__tests__/lib/sharedConstants.guard.test.ts` enforces it.
 */

const LOCALE = 'en-US';

function parse(iso: string): Date | null {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? null : d;
}

/** "Apr 10, 2026" — or "" when `iso` does not parse. */
export function formatDate(iso: string): string {
  return (
    parse(iso)?.toLocaleDateString(LOCALE, { month: 'short', day: 'numeric', year: 'numeric' }) ?? ''
  );
}

/** "Apr 10, 2026, 12:00 PM" — or "" when `iso` does not parse. */
export function formatDateTime(iso: string): string {
  return (
    parse(iso)?.toLocaleString(LOCALE, {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
    }) ?? ''
  );
}

/** "12:00:05 PM" — time of day with seconds, for event streams. "" when unparseable. */
export function formatTime(iso: string): string {
  return (
    parse(iso)?.toLocaleTimeString(LOCALE, { hour: '2-digit', minute: '2-digit', second: '2-digit' }) ??
    ''
  );
}

/** "30 minutes ago", "about 2 hours ago", "3 days ago". "" when unparseable. */
export function formatRelativeTime(iso: string): string {
  const d = parse(iso);
  return d ? formatDistanceToNow(d, { addSuffix: true }) : '';
}

const AGE_UNIT_ABBR: Record<string, string> = {
  second: 's',
  minute: 'm',
  hour: 'h',
  day: 'd',
  week: 'w',
  month: 'mo',
  year: 'y',
};

/**
 * "3d", "1m", "2mo" — compact age for dense list columns. The strict variant
 * never emits "about"/"almost" qualifiers, so the output is always
 * "<n> <unit>" which is then abbreviated. "" when unparseable.
 */
export function formatCompactAge(iso: string): string {
  const d = parse(iso);
  if (!d) return '';
  const strict = formatDistanceToNowStrict(d); // e.g. "3 days", "1 minute"
  const match = strict.match(/^(\d+)\s+(\w+?)s?$/);
  if (!match) return strict;
  const [, count, unit] = match;
  return `${count}${AGE_UNIT_ABBR[unit] ?? unit}`;
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
  return value.toLocaleString(LOCALE, {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits,
    maximumFractionDigits,
  });
}

/** Format a plain count (tokens, rows) with thousands separators. */
export function formatCount(n: number): string {
  return n.toLocaleString(LOCALE);
}
