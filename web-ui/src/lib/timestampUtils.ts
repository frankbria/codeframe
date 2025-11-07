/**
 * Timestamp Utility Functions
 *
 * Utilities for handling timestamp parsing and validation
 * for conflict resolution in the agent state management system.
 *
 * Phase: 5.2 - Dashboard Multi-Agent State Management
 * Date: 2025-11-06
 */

/**
 * Parse backend timestamp to Unix milliseconds
 *
 * Backend can send timestamps as either:
 * - Unix milliseconds (number)
 * - ISO 8601 string
 *
 * @param timestamp - Timestamp from backend
 * @returns Unix milliseconds
 */
export function parseTimestamp(timestamp: string | number): number {
  if (typeof timestamp === 'number') {
    return timestamp;
  }
  return new Date(timestamp).getTime();
}

/**
 * Get current timestamp in Unix milliseconds
 *
 * @returns Current time in Unix ms
 */
export function getCurrentTimestamp(): number {
  return Date.now();
}

/**
 * Check if timestamp1 is newer than timestamp2
 *
 * Used for conflict resolution - newer timestamps win
 *
 * @param timestamp1 - First timestamp (Unix ms)
 * @param timestamp2 - Second timestamp (Unix ms)
 * @returns true if timestamp1 is newer
 */
export function isNewerTimestamp(timestamp1: number, timestamp2: number): boolean {
  return timestamp1 > timestamp2;
}

/**
 * Format Unix milliseconds to ISO 8601 string for display
 *
 * @param timestamp - Unix milliseconds
 * @returns ISO 8601 formatted string
 */
export function formatTimestamp(timestamp: number): string {
  return new Date(timestamp).toISOString();
}

/**
 * Validate that a timestamp is reasonable (not too far in past or future)
 *
 * @param timestamp - Unix milliseconds
 * @param maxAgeMs - Maximum age in milliseconds (default: 24 hours)
 * @returns true if timestamp is within acceptable range
 */
export function isValidTimestamp(timestamp: number, maxAgeMs: number = 24 * 60 * 60 * 1000): boolean {
  const now = Date.now();
  const age = now - timestamp;
  const futureOffset = timestamp - now;

  // Not too old (> maxAgeMs in the past)
  if (age > maxAgeMs) {
    return false;
  }

  // Not too far in future (> 5 minutes ahead, allowing for some clock skew)
  if (futureOffset > 5 * 60 * 1000) {
    return false;
  }

  return true;
}
