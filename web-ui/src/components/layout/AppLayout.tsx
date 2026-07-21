'use client';

import { useEffect, useState, type ReactNode } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { HugeiconsIcon } from '@hugeicons/react';
import { Loading03Icon } from '@hugeicons/core-free-icons';
import { isAuthenticated } from '@/lib/auth';
import { checkAuthAccess } from '@/lib/api';
import { AppSidebar } from './AppSidebar';
import { PipelineProgressBar } from './PipelineProgressBar';

interface AppLayoutProps {
  children: ReactNode;
}

// Routes that render bare (no sidebar / pipeline bar) and are reachable while
// unauthenticated — e.g. the login page (issue #336).
const BARE_ROUTES = new Set(['/login']);

/** Neutral full-screen placeholder shown while access is resolving / redirecting. */
function FullPageLoader() {
  return (
    <div
      className="flex min-h-screen items-center justify-center bg-background"
      role="status"
      aria-label="Loading"
    >
      <HugeiconsIcon icon={Loading03Icon} className="h-6 w-6 animate-spin text-muted-foreground" aria-hidden="true" />
    </div>
  );
}

/**
 * Client-side layout shell with a proactive auth guard (issue #651).
 *
 * The JWT lives in localStorage, so a server/edge `middleware.ts` can't see it —
 * the guard must run on the client. A visitor without a token isn't necessarily
 * unauthenticated: the backend supports an auth-disabled mode
 * (`CODEFRAME_AUTH_REQUIRED=false`) where token-less access is allowed. So when
 * there's no token we ask the backend (`checkAuthAccess`) whether access is
 * permitted before deciding:
 *   - allowed (valid token, or auth disabled) → render the shell;
 *   - denied (auth required, no token)        → redirect to /login;
 *   - error (backend unreachable)             → fail open, render the shell.
 *
 * Throughout, an unauthenticated visitor only ever sees a neutral loader — the
 * sidebar/shell never renders for them, so there's no "shell → flicker → login"
 * jump. The login page renders bare and owns its own already-authenticated
 * redirect.
 */
export function AppLayout({ children }: AppLayoutProps) {
  const pathname = usePathname();
  const router = useRouter();
  const isBare = !!pathname && BARE_ROUTES.has(pathname);

  // Defer auth-dependent rendering to the client. The first client render must
  // match the server's (both `access === 'pending'`) to avoid a hydration
  // mismatch. Once 'allowed', it stays allowed for the session.
  const [mounted, setMounted] = useState(false);
  const [access, setAccess] = useState<'pending' | 'allowed'>('pending');
  useEffect(() => setMounted(true), []);

  useEffect(() => {
    if (!mounted || isBare || access === 'allowed') return;

    // A stored token → optimistically allow; the axios 401 interceptor handles
    // expiry reactively. No token → ask the backend whether auth is required.
    if (isAuthenticated()) {
      setAccess('allowed');
      return;
    }

    let cancelled = false;
    checkAuthAccess().then((result) => {
      if (cancelled) return;
      if (result === 'denied') {
        router.replace('/login');
      } else {
        // 'allowed' (auth disabled) or 'error' (fail open) → render the app.
        setAccess('allowed');
      }
    });
    return () => {
      cancelled = true;
    };
  }, [mounted, isBare, access, pathname, router]);

  // Bare routes (login) always render their own content, no guard, no shell.
  if (isBare) {
    return <>{children}</>;
  }

  // Pre-hydration, while resolving access, or while redirecting a denied
  // visitor: show a neutral loader instead of the shell.
  if (!mounted || access !== 'allowed') {
    return <FullPageLoader />;
  }

  return (
    <div className="flex min-h-screen">
      <AppSidebar />
      <div className="flex flex-1 flex-col">
        <PipelineProgressBar />
        {children}
      </div>
    </div>
  );
}
