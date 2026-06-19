/**
 * Thin navigation seam around `window.location`.
 *
 * jsdom 30 (Jest 30) makes `window.location` non-configurable, so it can no
 * longer be replaced in tests. Routing reads/writes through these helpers so
 * redirect behavior stays mockable via `jest.mock('@/lib/navigation')`.
 */

/** Current path, or '' on the server. */
export function currentPathname(): string {
  return typeof window !== 'undefined' ? window.location.pathname : '';
}

/** Hard-navigate the browser to `path` (no-op on the server). */
export function redirectTo(path: string): void {
  if (typeof window !== 'undefined') {
    window.location.href = path;
  }
}
