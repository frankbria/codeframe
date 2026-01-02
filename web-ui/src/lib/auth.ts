import { betterAuth } from "better-auth";
import { drizzleAdapter } from "better-auth/adapters/drizzle";
import { resolve } from "path";
import Database from "better-sqlite3";
import { drizzle } from "drizzle-orm/better-sqlite3";
import { schema } from "./db-schema";

/**
 * Better Auth server configuration with Drizzle adapter
 *
 * This configures Better Auth to use CodeFRAME's existing SQLite database
 * with the Drizzle ORM adapter. The adapter enables proper support for
 * plural table names (users, sessions) via usePlural: true.
 *
 * Features:
 * - Email/password authentication
 * - Session management with 7-day expiry
 * - Drizzle adapter for schema control
 * - Plural table names matching CodeFRAME backend
 *
 * @see https://better-auth.com/docs/adapters/drizzle
 */

// Determine database path (test vs production)
const testDbPath = process.env.TEST_DB_PATH?.trim();
const hasValidTestDbPath = testDbPath && testDbPath.length > 0;

const dbPath = hasValidTestDbPath
  ? resolve(testDbPath)
  : resolve(process.cwd(), "../.codeframe/state.db");

// Create better-sqlite3 connection
const sqlite = new Database(dbPath);

// Create Drizzle database instance with CodeFRAME schema
const db = drizzle(sqlite, { schema });

export const auth = betterAuth({
  database: drizzleAdapter(db, {
    provider: "sqlite",
    // Use plural table names to match CodeFRAME's existing schema
    // This tells Drizzle to use "users" and "sessions" instead of "user" and "session"
    usePlural: true,
  }),

  // Enable debug logging to diagnose authentication issues
  logger: {
    level: "debug",
    disabled: false,
  },

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
