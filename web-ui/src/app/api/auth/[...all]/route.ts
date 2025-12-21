import { auth } from "@/lib/auth";
import { toNextJsHandler } from "better-auth/next-js";

/**
 * Better Auth API route handler
 *
 * This catch-all route handles all Better Auth endpoints:
 * - POST /api/auth/sign-in
 * - POST /api/auth/sign-up
 * - POST /api/auth/sign-out
 * - GET /api/auth/session
 * - And more...
 *
 * Better Auth automatically creates these endpoints based on the
 * configuration in @/lib/auth.ts
 *
 * @see https://better-auth.com/docs/installation#add-api-route
 */
export const { GET, POST } = toNextJsHandler(auth);
