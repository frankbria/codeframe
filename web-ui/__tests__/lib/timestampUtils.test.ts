/**
 * Timestamp Utils Tests
 *
 * Comprehensive test coverage for timestamp utility functions
 * used in conflict resolution and state synchronization.
 *
 * Phase: 5.2 - Dashboard Multi-Agent State Management
 * Date: 2025-11-21
 */

import {
  parseTimestamp,
  getCurrentTimestamp,
  isNewerTimestamp,
  formatTimestamp,
  isValidTimestamp,
} from '@/lib/timestampUtils';

describe('Timestamp Utils', () => {
  // Fixed timestamps for deterministic testing
  const FIXED_NOW = 1700000000000; // 2023-11-14T22:13:20.000Z
  const ONE_HOUR_AGO = FIXED_NOW - (60 * 60 * 1000);
  const ONE_DAY_AGO = FIXED_NOW - (24 * 60 * 60 * 1000);
  const TWO_DAYS_AGO = FIXED_NOW - (48 * 60 * 60 * 1000);
  const FIVE_MINUTES_FUTURE = FIXED_NOW + (5 * 60 * 1000);
  const TEN_MINUTES_FUTURE = FIXED_NOW + (10 * 60 * 1000);

  let dateNowSpy: jest.SpyInstance;

  beforeEach(() => {
    // Mock Date.now() to return fixed timestamp
    dateNowSpy = jest.spyOn(Date, 'now').mockReturnValue(FIXED_NOW);
  });

  afterEach(() => {
    // Restore Date.now()
    dateNowSpy.mockRestore();
  });

  describe('parseTimestamp', () => {
    it('should return Unix milliseconds when given a number', () => {
      const timestamp = 1700000000000;
      expect(parseTimestamp(timestamp)).toBe(timestamp);
    });

    it('should parse ISO 8601 string to Unix milliseconds', () => {
      const isoString = '2023-11-14T22:13:20.000Z';
      const expected = 1700000000000;
      expect(parseTimestamp(isoString)).toBe(expected);
    });

    it('should handle ISO strings with timezone offsets', () => {
      const isoString = '2023-11-14T17:13:20.000-05:00'; // EST, same moment as above
      const expected = 1700000000000;
      expect(parseTimestamp(isoString)).toBe(expected);
    });

    it('should handle ISO strings with milliseconds', () => {
      const isoString = '2023-11-14T22:13:20.456Z';
      const expected = 1700000000456;
      expect(parseTimestamp(isoString)).toBe(expected);
    });

    it('should handle date-only ISO strings', () => {
      const isoString = '2023-11-14';
      const result = parseTimestamp(isoString);
      expect(result).toBeGreaterThan(0);
      expect(new Date(result).toISOString().startsWith('2023-11-14')).toBe(true);
    });

    it('should handle zero timestamp', () => {
      expect(parseTimestamp(0)).toBe(0);
    });

    it('should handle epoch start timestamp', () => {
      const epochStart = '1970-01-01T00:00:00.000Z';
      expect(parseTimestamp(epochStart)).toBe(0);
    });

    it('should handle very large timestamps (far future)', () => {
      const farFuture = '2099-12-31T23:59:59.999Z';
      const result = parseTimestamp(farFuture);
      expect(result).toBeGreaterThan(FIXED_NOW);
      expect(result).toBeLessThan(5000000000000); // Before year 2128
    });

    it('should return NaN for invalid date strings', () => {
      const result = parseTimestamp('invalid-date');
      expect(result).toBeNaN();
    });

    it('should handle empty string as invalid', () => {
      const result = parseTimestamp('');
      expect(result).toBeNaN();
    });
  });

  describe('getCurrentTimestamp', () => {
    it('should return current time in Unix milliseconds', () => {
      const result = getCurrentTimestamp();
      expect(result).toBe(FIXED_NOW);
    });

    it('should return a positive number', () => {
      const result = getCurrentTimestamp();
      expect(result).toBeGreaterThan(0);
    });

    it('should return a timestamp in milliseconds (not seconds)', () => {
      const result = getCurrentTimestamp();
      // Unix milliseconds are 13 digits for dates after 2001
      expect(result.toString().length).toBeGreaterThanOrEqual(13);
    });

    it('should return consistent value when Date.now is mocked', () => {
      const first = getCurrentTimestamp();
      const second = getCurrentTimestamp();
      expect(first).toBe(second);
    });
  });

  describe('isNewerTimestamp', () => {
    it('should return true when first timestamp is newer', () => {
      expect(isNewerTimestamp(FIXED_NOW, ONE_HOUR_AGO)).toBe(true);
    });

    it('should return false when first timestamp is older', () => {
      expect(isNewerTimestamp(ONE_HOUR_AGO, FIXED_NOW)).toBe(false);
    });

    it('should return false when timestamps are equal', () => {
      expect(isNewerTimestamp(FIXED_NOW, FIXED_NOW)).toBe(false);
    });

    it('should handle very small time differences (1ms)', () => {
      const timestamp1 = FIXED_NOW;
      const timestamp2 = FIXED_NOW - 1;
      expect(isNewerTimestamp(timestamp1, timestamp2)).toBe(true);
      expect(isNewerTimestamp(timestamp2, timestamp1)).toBe(false);
    });

    it('should handle large time differences', () => {
      const twoYearsAgo = FIXED_NOW - (2 * 365 * 24 * 60 * 60 * 1000);
      expect(isNewerTimestamp(FIXED_NOW, twoYearsAgo)).toBe(true);
    });

    it('should handle zero timestamps', () => {
      expect(isNewerTimestamp(FIXED_NOW, 0)).toBe(true);
      expect(isNewerTimestamp(0, FIXED_NOW)).toBe(false);
    });

    it('should handle negative timestamps (before epoch)', () => {
      const beforeEpoch = -1000;
      expect(isNewerTimestamp(0, beforeEpoch)).toBe(true);
      expect(isNewerTimestamp(beforeEpoch, 0)).toBe(false);
    });

    it('should correctly resolve conflicts (last-write-wins)', () => {
      const serverTimestamp = FIXED_NOW;
      const clientTimestamp = ONE_HOUR_AGO;

      // Server update is newer - should win
      expect(isNewerTimestamp(serverTimestamp, clientTimestamp)).toBe(true);

      // Client update is older - should lose
      expect(isNewerTimestamp(clientTimestamp, serverTimestamp)).toBe(false);
    });
  });

  describe('formatTimestamp', () => {
    it('should format Unix milliseconds to ISO 8601 string', () => {
      const timestamp = 1700000000000;
      const result = formatTimestamp(timestamp);
      expect(result).toBe('2023-11-14T22:13:20.000Z');
    });

    it('should include milliseconds in output', () => {
      const timestamp = 1700000000456;
      const result = formatTimestamp(timestamp);
      expect(result).toBe('2023-11-14T22:13:20.456Z');
    });

    it('should format zero timestamp as epoch start', () => {
      const result = formatTimestamp(0);
      expect(result).toBe('1970-01-01T00:00:00.000Z');
    });

    it('should format negative timestamp (before epoch)', () => {
      const timestamp = -1000;
      const result = formatTimestamp(timestamp);
      expect(result).toBe('1969-12-31T23:59:59.000Z');
    });

    it('should always use UTC timezone (Z suffix)', () => {
      const result = formatTimestamp(FIXED_NOW);
      expect(result).toMatch(/Z$/);
    });

    it('should produce valid ISO 8601 format', () => {
      const result = formatTimestamp(FIXED_NOW);
      // ISO 8601: YYYY-MM-DDTHH:mm:ss.sssZ
      expect(result).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/);
    });

    it('should be reversible with parseTimestamp', () => {
      const original = FIXED_NOW;
      const formatted = formatTimestamp(original);
      const parsed = parseTimestamp(formatted);
      expect(parsed).toBe(original);
    });

    it('should handle far future timestamps', () => {
      const farFuture = new Date('2099-12-31').getTime();
      const result = formatTimestamp(farFuture);
      expect(result.startsWith('2099-12-31')).toBe(true);
    });
  });

  describe('isValidTimestamp', () => {
    describe('Default max age (24 hours)', () => {
      it('should return true for current timestamp', () => {
        expect(isValidTimestamp(FIXED_NOW)).toBe(true);
      });

      it('should return true for timestamp 1 hour ago', () => {
        expect(isValidTimestamp(ONE_HOUR_AGO)).toBe(true);
      });

      it('should return true for timestamp exactly 24 hours ago', () => {
        expect(isValidTimestamp(ONE_DAY_AGO)).toBe(true);
      });

      it('should return false for timestamp more than 24 hours ago', () => {
        const justOver24Hours = FIXED_NOW - (24 * 60 * 60 * 1000 + 1);
        expect(isValidTimestamp(justOver24Hours)).toBe(false);
      });

      it('should return false for timestamp 2 days ago', () => {
        expect(isValidTimestamp(TWO_DAYS_AGO)).toBe(false);
      });

      it('should return true for timestamp 1 minute in future (clock skew)', () => {
        const oneMinuteFuture = FIXED_NOW + (60 * 1000);
        expect(isValidTimestamp(oneMinuteFuture)).toBe(true);
      });

      it('should return true for timestamp exactly 5 minutes in future', () => {
        expect(isValidTimestamp(FIVE_MINUTES_FUTURE)).toBe(true);
      });

      it('should return false for timestamp more than 5 minutes in future', () => {
        const justOver5Min = FIXED_NOW + (5 * 60 * 1000 + 1);
        expect(isValidTimestamp(justOver5Min)).toBe(false);
      });

      it('should return false for timestamp 10 minutes in future', () => {
        expect(isValidTimestamp(TEN_MINUTES_FUTURE)).toBe(false);
      });

      it('should handle boundary at 24 hours (inclusive)', () => {
        const exactly24h = FIXED_NOW - (24 * 60 * 60 * 1000);
        expect(isValidTimestamp(exactly24h)).toBe(true);
      });

      it('should handle boundary at 5 minutes future (inclusive)', () => {
        const exactly5min = FIXED_NOW + (5 * 60 * 1000);
        expect(isValidTimestamp(exactly5min)).toBe(true);
      });
    });

    describe('Custom max age', () => {
      it('should respect custom maxAgeMs parameter (1 hour)', () => {
        const oneHour = 60 * 60 * 1000;

        // Within 1 hour - valid
        expect(isValidTimestamp(ONE_HOUR_AGO, oneHour)).toBe(true);

        // More than 1 hour - invalid
        const twoHoursAgo = FIXED_NOW - (2 * 60 * 60 * 1000);
        expect(isValidTimestamp(twoHoursAgo, oneHour)).toBe(false);
      });

      it('should respect custom maxAgeMs parameter (1 week)', () => {
        const oneWeek = 7 * 24 * 60 * 60 * 1000;
        const sixDaysAgo = FIXED_NOW - (6 * 24 * 60 * 60 * 1000);

        expect(isValidTimestamp(sixDaysAgo, oneWeek)).toBe(true);
      });

      it('should handle very small maxAgeMs (1 minute)', () => {
        const oneMinute = 60 * 1000;
        const thirtySecondsAgo = FIXED_NOW - (30 * 1000);
        const twoMinutesAgo = FIXED_NOW - (2 * 60 * 1000);

        expect(isValidTimestamp(thirtySecondsAgo, oneMinute)).toBe(true);
        expect(isValidTimestamp(twoMinutesAgo, oneMinute)).toBe(false);
      });

      it('should handle very large maxAgeMs (1 year)', () => {
        const oneYear = 365 * 24 * 60 * 60 * 1000;
        const sixMonthsAgo = FIXED_NOW - (180 * 24 * 60 * 60 * 1000);

        expect(isValidTimestamp(sixMonthsAgo, oneYear)).toBe(true);
      });

      it('should still check future limit with custom maxAgeMs', () => {
        const oneWeek = 7 * 24 * 60 * 60 * 1000;

        // Even with 1 week past allowance, future is still limited to 5 min
        expect(isValidTimestamp(TEN_MINUTES_FUTURE, oneWeek)).toBe(false);
      });
    });

    describe('Edge cases', () => {
      it('should return true for timestamp exactly at current time', () => {
        expect(isValidTimestamp(FIXED_NOW)).toBe(true);
      });

      it('should return false for zero timestamp (epoch)', () => {
        expect(isValidTimestamp(0)).toBe(false);
      });

      it('should return false for negative timestamp', () => {
        expect(isValidTimestamp(-1000)).toBe(false);
      });

      it('should handle timestamp at exact boundary (24h ago)', () => {
        const exactly24h = FIXED_NOW - (24 * 60 * 60 * 1000);
        expect(isValidTimestamp(exactly24h)).toBe(true);

        const justOver24h = exactly24h - 1;
        expect(isValidTimestamp(justOver24h)).toBe(false);
      });

      it('should handle timestamp at exact future boundary (5 min)', () => {
        const exactly5min = FIXED_NOW + (5 * 60 * 1000);
        expect(isValidTimestamp(exactly5min)).toBe(true);

        const justOver5min = exactly5min + 1;
        expect(isValidTimestamp(justOver5min)).toBe(false);
      });

      it('should handle maxAgeMs of zero (only current allowed)', () => {
        expect(isValidTimestamp(FIXED_NOW, 0)).toBe(true);
        expect(isValidTimestamp(FIXED_NOW - 1, 0)).toBe(false);
      });

      it('should handle very far future timestamp', () => {
        const farFuture = new Date('2099-12-31').getTime();
        expect(isValidTimestamp(farFuture)).toBe(false);
      });

      it('should handle very old timestamp', () => {
        const veryOld = new Date('1990-01-01').getTime();
        expect(isValidTimestamp(veryOld)).toBe(false);
      });
    });
  });

  describe('Integration: Conflict Resolution Workflow', () => {
    it('should correctly resolve timestamp conflicts using last-write-wins', () => {
      // Scenario: Client has old data, server sends update
      const clientTimestamp = parseTimestamp('2023-11-14T20:00:00.000Z');
      const serverTimestamp = parseTimestamp('2023-11-14T22:00:00.000Z');

      // Server update is newer
      expect(isNewerTimestamp(serverTimestamp, clientTimestamp)).toBe(true);

      // Both timestamps are valid (within 24 hours of FIXED_NOW)
      expect(isValidTimestamp(clientTimestamp)).toBe(true);
      expect(isValidTimestamp(serverTimestamp)).toBe(true);
    });

    it('should reject stale updates from old timestamps', () => {
      const currentTimestamp = FIXED_NOW;
      const staleTimestamp = TWO_DAYS_AGO;

      // Stale update is older
      expect(isNewerTimestamp(staleTimestamp, currentTimestamp)).toBe(false);

      // Stale timestamp is invalid
      expect(isValidTimestamp(staleTimestamp)).toBe(false);
    });

    it('should handle WebSocket message with timestamp', () => {
      // Simulate WebSocket message with ISO timestamp
      const wsMessage = {
        type: 'agent_status_update',
        timestamp: '2023-11-14T22:13:20.000Z',
        data: { status: 'active' }
      };

      const parsedTimestamp = parseTimestamp(wsMessage.timestamp);
      expect(parsedTimestamp).toBe(FIXED_NOW);
      expect(isValidTimestamp(parsedTimestamp)).toBe(true);
    });

    it('should handle backend response with numeric timestamp', () => {
      // Simulate backend API response with Unix milliseconds
      const apiResponse = {
        agent_id: 'backend-001',
        status: 'active',
        updated_at: 1700000000000
      };

      const parsedTimestamp = parseTimestamp(apiResponse.updated_at);
      expect(parsedTimestamp).toBe(FIXED_NOW);
      expect(isValidTimestamp(parsedTimestamp)).toBe(true);
    });

    it('should format timestamps for display in UI', () => {
      const timestamp = FIXED_NOW;
      const formatted = formatTimestamp(timestamp);

      // Should be readable ISO format
      expect(formatted).toBe('2023-11-14T22:13:20.000Z');

      // Should be parseable back
      expect(parseTimestamp(formatted)).toBe(timestamp);
    });

    it('should validate timestamps before using in conflict resolution', () => {
      const validTimestamp = FIXED_NOW;
      const invalidTimestamp = TWO_DAYS_AGO;

      if (isValidTimestamp(validTimestamp) && isValidTimestamp(invalidTimestamp)) {
        // This path won't execute due to invalid timestamp
        expect(isNewerTimestamp(validTimestamp, invalidTimestamp)).toBe(true);
      } else {
        // Should reject comparison due to invalid timestamp
        expect(isValidTimestamp(invalidTimestamp)).toBe(false);
      }
    });
  });

  describe('Type Safety & Error Handling', () => {
    it('should handle NaN from invalid date parsing', () => {
      const result = parseTimestamp('not-a-date');
      expect(result).toBeNaN();

      // NaN should be considered invalid
      expect(isValidTimestamp(result)).toBe(false);
    });

    it('should handle Infinity', () => {
      expect(isValidTimestamp(Infinity)).toBe(false);
      expect(isValidTimestamp(-Infinity)).toBe(false);
    });

    it('should handle very large numbers', () => {
      const veryLarge = Number.MAX_SAFE_INTEGER;
      // This is far in the future, should be invalid
      expect(isValidTimestamp(veryLarge)).toBe(false);
    });

    it('should consistently handle numeric zero', () => {
      expect(parseTimestamp(0)).toBe(0);
      expect(formatTimestamp(0)).toBe('1970-01-01T00:00:00.000Z');
      expect(isValidTimestamp(0)).toBe(false); // Too old
    });

    it('should handle all timestamp formats consistently', () => {
      const formats = [
        1700000000000,                          // Unix milliseconds
        '2023-11-14T22:13:20.000Z',            // ISO with milliseconds
        '2023-11-14T22:13:20Z',                // ISO without milliseconds
        '2023-11-14T17:13:20-05:00',           // ISO with timezone
      ];

      const parsed = formats.map(parseTimestamp);

      // All should parse to the same timestamp (within 1s for those without ms)
      parsed.forEach((timestamp, i) => {
        if (i === 0) {
          expect(timestamp).toBe(1700000000000);
        } else {
          // Allow for formatting differences, but should be very close
          expect(Math.abs(timestamp - 1700000000000)).toBeLessThan(1000);
        }
      });
    });
  });
});
