import { betterAuth } from "better-auth";
import { resolve } from "path";

/**
 * Better Auth server configuration
 *
 * This configures Better Auth with SQLite database backend pointing to the
 * CodeFRAME state database. Authentication tables (users, sessions) are
 * created automatically by Better Auth.
 *
 * Features:
 * - Email/password authentication
 * - Session management with 7-day expiry
 * - SQLite database URL for persistence
 *
 * @see https://better-auth.com/docs/installation
 */
// Validate TEST_DB_PATH environment variable (used for E2E tests)
const testDbPath = process.env.TEST_DB_PATH?.trim();
const hasValidTestDbPath = testDbPath && testDbPath.length > 0;

export const auth = betterAuth({
  database: {
    // SQLite database URL pointing to CodeFRAME state database
    // Use TEST_DB_PATH for E2E tests, otherwise use production database
    url: hasValidTestDbPath
      ? `file:${resolve(testDbPath)}`
      : `file:${resolve(process.cwd(), "../.codeframe/state.db")}`,
    type: "sqlite",
  },

  // Use plural table names to match CodeFRAME's existing schema
  // This aligns BetterAuth with the `users` and `sessions` tables
  usePlural: true,

  // Email and password authentication
  emailAndPassword: {
    enabled: true,
    // Require email verification (can be disabled for development)
    requireEmailVerification: false,
    // Minimum password length
    minPasswordLength: 8,
  },

  // Session configuration
  session: {
    // Sessions expire after 7 days
    expiresIn: 60 * 60 * 24 * 7, // 7 days in seconds

    // Update session expiry on each request
    updateAge: 60 * 60 * 24, // Update if session is older than 1 day

    // Cookie configuration
    cookieCache: {
      enabled: true,
      maxAge: 60 * 5, // 5 minutes
    },
  },

  // Base URL for redirects and emails
  baseURL: process.env.NEXT_PUBLIC_APP_URL || "http://localhost:3000",

  // Trust proxy headers (for deployment behind reverse proxy)
  trustedOrigins: [
    process.env.NEXT_PUBLIC_APP_URL || "http://localhost:3000",
    "http://localhost:3000",
  ],
});

/**
 * Type exports for Better Auth
 */
export type Session = typeof auth.$Infer.Session;
