/**
 * Shared configuration for E2E tests.
 * Centralizes constants used by both playwright.config.ts and global-setup.ts.
 */
import * as path from 'path';

// Test database path - used by both Playwright config and global setup
export const TEST_DB_PATH = path.join(__dirname, '.codeframe', 'state.db');

// Backend URL for API calls
export const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8080';

// Frontend URL for browser tests (using 3001 to avoid conflicts with other services)
export const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:3001';

/**
 * Test Project IDs for State Reconciliation Tests
 *
 * These projects are seeded in seed-test-data.py with different lifecycle states:
 * - DISCOVERY: Project 1 - In discovery phase with active questions
 * - PLANNING: Project 2 - In planning phase with PRD complete and tasks generated
 * - ACTIVE: Project 3 - In active phase with running agents and in-progress tasks
 * - REVIEW: Project 4 - In review phase with completed tasks awaiting review
 * - COMPLETED: Project 5 - In completed phase with all work done
 *
 * @example
 * // Use in tests:
 * const projectId = TEST_PROJECT_IDS.PLANNING;
 * await page.goto(`${FRONTEND_URL}/projects/${projectId}`);
 */
export const TEST_PROJECT_IDS = {
  /** Project in discovery phase - active discovery questions */
  DISCOVERY: process.env.E2E_TEST_PROJECT_DISCOVERY_ID || '1',
  /** Project in planning phase - PRD complete, tasks generated */
  PLANNING: process.env.E2E_TEST_PROJECT_PLANNING_ID || '2',
  /** Project in active phase - agents working, tasks in progress */
  ACTIVE: process.env.E2E_TEST_PROJECT_ACTIVE_ID || '3',
  /** Project in review phase - tasks complete, quality gates run */
  REVIEW: process.env.E2E_TEST_PROJECT_REVIEW_ID || '4',
  /** Project in completed phase - all work done */
  COMPLETED: process.env.E2E_TEST_PROJECT_COMPLETED_ID || '5',
} as const;

/** Type for valid project IDs */
export type TestProjectId = typeof TEST_PROJECT_IDS[keyof typeof TEST_PROJECT_IDS];
