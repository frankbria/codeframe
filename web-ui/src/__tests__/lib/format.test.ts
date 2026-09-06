import { formatUsd, formatCount, formatRelativeTime } from '@/lib/format';

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

describe('formatRelativeTime', () => {
  it('still works after the module gained currency helpers', () => {
    expect(formatRelativeTime(new Date().toISOString())).toBe('just now');
  });
});
