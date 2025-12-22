import { createAuthClient } from "better-auth/react";
import type { Session } from "./auth";

/**
 * Better Auth client for React components
 *
 * Provides hooks and utilities for authentication in client-side code.
 * All authentication operations are handled through the Better Auth API.
 *
 * Usage:
 *   import { authClient } from '@/lib/auth-client';
 *
 *   // In a component:
 *   const { data: session, isPending } = authClient.useSession();
 *   const { signIn } = authClient;
 *
 * @see https://better-auth.com/docs/react
 */
export const authClient = createAuthClient({
  baseURL: process.env.NEXT_PUBLIC_APP_URL || "http://localhost:3000",
});

/**
 * Sign in with email and password
 *
 * @param email - User email address
 * @param password - User password
 * @returns Promise resolving to session data or error
 *
 * @example
 *   const result = await signIn({
 *     email: 'user@example.com',
 *     password: 'securepassword123'
 *   });
 *
 *   if (result.error) {
 *     console.error('Login failed:', result.error.message);
 *   } else {
 *     console.log('Logged in as:', result.data.user.email);
 *   }
 */
export const signIn = authClient.signIn.email;

/**
 * Sign up with email and password
 *
 * @param name - User's full name
 * @param email - User email address
 * @param password - User password
 * @returns Promise resolving to session data or error
 *
 * @example
 *   const result = await signUp({
 *     name: 'John Doe',
 *     email: 'john@example.com',
 *     password: 'securepassword123'
 *   });
 *
 *   if (result.error) {
 *     console.error('Signup failed:', result.error.message);
 *   } else {
 *     console.log('Account created for:', result.data.user.email);
 *   }
 */
export const signUp = authClient.signUp.email;

/**
 * Sign out the current user
 *
 * Invalidates the current session and redirects to login page.
 *
 * @example
 *   await signOut();
 *   router.push('/login');
 */
export const signOut = authClient.signOut;

/**
 * Get current session
 *
 * React hook that returns the current session state.
 * Automatically re-renders when session changes.
 *
 * @returns Object with session data and loading state
 *
 * @example
 *   function MyComponent() {
 *     const { data: session, isPending } = useSession();
 *
 *     if (isPending) {
 *       return <div>Loading...</div>;
 *     }
 *
 *     if (!session) {
 *       return <div>Not logged in</div>;
 *     }
 *
 *     return <div>Welcome, {session.user.name}!</div>;
 *   }
 */
export const useSession = authClient.useSession;

/**
 * Type exports
 */
export type { Session };
