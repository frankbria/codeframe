/**
 * Drizzle ORM schema for BetterAuth integration with CodeFRAME database
 *
 * This schema defines the BetterAuth-compatible tables that exist in
 * CodeFRAME's SQLite database. BetterAuth will use these tables via
 * the Drizzle adapter with usePlural: true.
 *
 * BetterAuth Schema Architecture:
 * - users: Core user information (no password stored here)
 * - accounts: Authentication credentials (passwords, OAuth tokens)
 * - sessions: Active user sessions
 *
 * IMPORTANT: This schema matches the tables created by
 * codeframe.persistence.schema_manager.SchemaManager. Any changes here
 * must be coordinated with the backend schema.
 */

import { sqliteTable, text, integer } from "drizzle-orm/sqlite-core";
import { sql } from "drizzle-orm";

/**
 * Users table - stores core user information (BetterAuth compatible)
 *
 * Note: Passwords are NOT stored here. They are in the accounts table.
 * This separation allows OAuth and email/password auth to coexist.
 *
 * Schema matches backend table in:
 * codeframe/persistence/schema_manager.py (_create_auth_tables)
 */
export const users = sqliteTable("users", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  email: text("email").notNull().unique(),
  name: text("name"),
  emailVerified: integer("email_verified", { mode: "boolean" }).default(false),
  image: text("image"),
  createdAt: text("created_at").default(sql`CURRENT_TIMESTAMP`),
  updatedAt: text("updated_at").default(sql`CURRENT_TIMESTAMP`),
});

/**
 * Accounts table - stores authentication credentials (BetterAuth compatible)
 *
 * This table stores:
 * - Email/password credentials (provider_id='credential')
 * - OAuth tokens (provider_id='google', 'github', etc.)
 *
 * Schema matches backend table in:
 * codeframe/persistence/schema_manager.py (_create_auth_tables)
 */
export const accounts = sqliteTable("accounts", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  userId: integer("user_id")
    .notNull()
    .references(() => users.id, { onDelete: "cascade" }),
  accountId: text("account_id").notNull(),
  providerId: text("provider_id").notNull(),
  password: text("password"),
  accessToken: text("access_token"),
  refreshToken: text("refresh_token"),
  expiresAt: text("expires_at"),
  createdAt: text("created_at").default(sql`CURRENT_TIMESTAMP`),
  updatedAt: text("updated_at").default(sql`CURRENT_TIMESTAMP`),
});

/**
 * Sessions table - stores active user sessions (BetterAuth compatible)
 *
 * Schema matches backend table in:
 * codeframe/persistence/schema_manager.py (_create_auth_tables)
 */
export const sessions = sqliteTable("sessions", {
  id: text("id").primaryKey(),
  token: text("token").notNull().unique(),
  userId: integer("user_id")
    .notNull()
    .references(() => users.id, { onDelete: "cascade" }),
  expiresAt: text("expires_at").notNull(),
  ipAddress: text("ip_address"),
  userAgent: text("user_agent"),
  createdAt: text("created_at").default(sql`CURRENT_TIMESTAMP`),
  updatedAt: text("updated_at").default(sql`CURRENT_TIMESTAMP`),
});

/**
 * Drizzle database schema export
 * Used by BetterAuth drizzleAdapter
 */
export const schema = {
  users,
  accounts,
  sessions,
};
