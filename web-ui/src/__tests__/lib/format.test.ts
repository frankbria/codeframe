import {
  formatUsd,
  formatCount,
  formatRelativeTime,
  formatCompactAge,
  formatDate,
  formatDateTime,
  formatTime,
} from '@/lib/format';

describe('formatUsd', () => {
  it('defaults to 4 fraction digits', () => {
    expect(formatUsd(1.5)).toBe('$1.5000');
    expect(formatUsd(0)).toBe('$0.0000');
  });

  it('honours a wider maximum for small-magnitude costs', () => {
    expect(formatUsd(0.0000125, { maximumFractionDigits: 6 })).toBe('$0.000013');
    expect(formatUsd(1.5, { maximumFractionDigits: 6 })).toBe('$1.5000');
  });

  it('honours an explicit fixed precision', () => {
    expect(formatUsd(1.5, { minimumFractionDigits: 2, maximumFractionDigits: 2 })).toBe('$1.50');
  });

  it('groups thousands', () => {
    expect(formatUsd(1234.5)).toBe('$1,234.5000');
  });
});

describe('formatCount', () => {
  it('groups thousands', () => {
    expect(formatCount(1234567)).toBe('1,234,567');
    expect(formatCount(0)).toBe('0');
  });
});

describe('formatRelativeTime (#1195)', () => {
  const minutesAgo = (n: number) => new Date(Date.now() - n * 60_000).toISOString();

  it('uses the date-fns wording with a suffix', () => {
    expect(formatRelativeTime(minutesAgo(30))).toBe('30 minutes ago');
    expect(formatRelativeTime(minutesAgo(2 * 60))).toBe('about 2 hours ago');
    expect(formatRelativeTime(minutesAgo(0))).toBe('less than a minute ago');
  });

  it('returns an empty string for unparseable input', () => {
    expect(formatRelativeTime('not a date')).toBe('');
    expect(formatRelativeTime('')).toBe('');
  });
});

describe('formatCompactAge (#1195)', () => {
  const ago = (ms: number) => new Date(Date.now() - ms).toISOString();

  it('abbreviates the unit and drops the suffix', () => {
    expect(formatCompactAge(ago(3 * 86_400_000))).toBe('3d');
    expect(formatCompactAge(ago(60_000))).toBe('1m');
    expect(formatCompactAge(ago(400 * 86_400_000))).toBe('1y');
  });

  it('returns an empty string for unparseable input', () => {
    expect(formatCompactAge('')).toBe('');
    expect(formatCompactAge('garbage')).toBe('');
  });
});

describe('absolute timestamp formatters (#1195)', () => {
  // Noon UTC keeps the calendar day stable in every timezone within ±11h.
  const ISO = '2026-04-10T12:00:05Z';
  const local = new Date(ISO);
  const hour12 = ((local.getHours() + 11) % 12) + 1;
  const ampm = local.getHours() < 12 ? 'AM' : 'PM';
  const mm = String(local.getMinutes()).padStart(2, '0');

  it('formatDate renders a short month, day and year', () => {
    expect(formatDate(ISO)).toBe('Apr 10, 2026');
  });

  it('formatDateTime appends the time to the date', () => {
    expect(formatDateTime(ISO)).toBe(`Apr 10, 2026, ${hour12}:${mm} ${ampm}`);
  });

  it('formatTime renders the time of day with seconds', () => {
    expect(formatTime(ISO)).toBe(`${String(hour12).padStart(2, '0')}:${mm}:05 ${ampm}`);
  });

  it('all three return an empty string for unparseable input', () => {
    expect(formatDate('garbage')).toBe('');
    expect(formatDateTime('garbage')).toBe('');
    expect(formatTime('garbage')).toBe('');
  });
});
