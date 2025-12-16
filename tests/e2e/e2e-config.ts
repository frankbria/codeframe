/**
 * Shared configuration for E2E tests.
 * Centralizes constants used by both playwright.config.ts and global-setup.ts.
 */
import * as path from 'path';

// Test database path - used by both Playwright config and global setup
export const TEST_DB_PATH = path.join(__dirname, '.codeframe', 'state.db');

// Backend URL for API calls
export const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8080';

// Frontend URL for browser tests
export const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:3000';
