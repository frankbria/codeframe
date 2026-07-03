/**
 * Frontend authentication library (issue #336).
 *
 * Owns the JWT lifecycle for the web UI:
 * - Token storage under the `auth_token` localStorage key (the convention
 *   already used by the WebSocket hooks — see `useAgentChat.ts`).
 * - `login()` against fastapi-users' form-encoded `/auth/jwt/login`.
 * - `register()` for the bootstrap-first-user flow (`/auth/register`).
 * - `logout()` clears the token and redirects to `/login`.
 * - `withStreamTicket()` appends `?ticket=<ticket>` to SSE/WebSocket URLs,
 *   which cannot send an Authorization header. The ticket is a short-lived,
 *   single-use credential fetched via an injected callback (issue #745) —
 *   this replaces the long-lived JWT previously exposed as `?token=`.
 *
 * Error messages are normalized to friendly, user-facing strings.
 */
import axios from 'axios';

import { redirectTo } from './navigation';

const TOKEN_KEY = 'auth_token';

// Login/register hit the API origin directly. Mirror the axios client base URL.
const API_BASE = process.env.NEXT_PUBLIC_API_URL || '';

// ── Token storage (SSR-safe) ────────────────────────────────────────────

export function getToken(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  if (typeof window === 'undefined') return;
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  if (typeof window === 'undefined') return;
  localStorage.removeItem(TOKEN_KEY);
}

/**
 * Whether a JWT is currently stored. Used by the proactive route guard
 * (`AppLayout`) and the `/login` already-authenticated redirect (#651).
 * Returns `false` during SSR (no `window`).
 */
export function isAuthenticated(): boolean {
  return getToken() !== null;
}

// ── Auth flows ──────────────────────────────────────────────────────────

interface LoginResponse {
  access_token: string;
  token_type: string;
}

/**
 * Authenticate with email + password against fastapi-users' JWT login.
 * The endpoint expects a form-encoded body (`username` / `password`), not JSON.
 * On success the token is stored and returned.
 */
export async function login(email: string, password: string): Promise<string> {
  const body = new URLSearchParams();
  body.set('username', email);
  body.set('password', password);

  try {
    const response = await axios.post<LoginResponse>(
      `${API_BASE}/auth/jwt/login`,
      body,
      {
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      }
    );
    const token = response.data.access_token;
    setToken(token);
    return token;
  } catch (error) {
    throw normalizeAuthError(error, 'login');
  }
}

/**
 * Register the first account (bootstrap-first-user). The backend returns 403
 * once any user exists, so this is only reachable on a fresh install.
 */
export async function register(email: string, password: string): Promise<void> {
  try {
    await axios.post(`${API_BASE}/auth/register`, { email, password });
  } catch (error) {
    throw normalizeAuthError(error, 'register');
  }
}

/**
 * Clear the stored token and send the user back to the login page.
 * Safe to call from anywhere (guards `window`).
 */
export function logout(): void {
  clearToken();
  redirectTo('/login');
}

// ── Stream ticket helper ────────────────────────────────────────────────

/**
 * Append a single-use stream ticket as `?ticket=` so EventSource/WebSocket
 * (neither can set an Authorization header) can authenticate (issue #745).
 *
 * `fetchTicket` is injected rather than imported directly from `./api`:
 * `api.ts` already imports `getToken`/`clearToken` from this module (for the
 * Bearer interceptor), so importing it back here would create a circular
 * dependency. Callers pass `fetchStreamTicket` from `@/lib/api`.
 *
 * Tickets are single-use and expire in ~60s, so this — and thus the injected
 * fetcher — must be called fresh for every (re)connect attempt; never reuse
 * a previously built URL. Handles URLs that already carry a query string.
 * Returns the URL unchanged (no ticket param) when no ticket is available
 * (fetch failed, or auth is disabled).
 */
export async function withStreamTicket(
  url: string,
  fetchTicket: () => Promise<string | null>
): Promise<string> {
  const ticket = await fetchTicket();
  if (!ticket) return url;
  const separator = url.includes('?') ? '&' : '?';
  return `${url}${separator}ticket=${encodeURIComponent(ticket)}`;
}

// ── Error normalization ─────────────────────────────────────────────────

function normalizeAuthError(error: unknown, flow: 'login' | 'register'): Error {
  if (axios.isAxiosError(error)) {
    const status = error.response?.status;
    if (flow === 'login' && status === 400) {
      return new Error('Invalid email or password.');
    }
    if (flow === 'register' && status === 403) {
      return new Error(
        'Registration is closed — an account already exists. Please sign in.'
      );
    }
    if (flow === 'register' && status === 400) {
      return new Error('An account with that email already exists.');
    }
    const detail = error.response?.data?.detail;
    if (typeof detail === 'string') return new Error(detail);
  }
  return new Error(
    flow === 'login'
      ? 'Sign-in failed. Please try again.'
      : 'Registration failed. Please try again.'
  );
}
