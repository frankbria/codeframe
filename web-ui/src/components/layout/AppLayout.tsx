'use client';

import { useEffect, useState, type ReactNode } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { Loading03Icon } from '@hugeicons/react';
import { isAuthenticated } from '@/lib/auth';
import { AppSidebar } from './AppSidebar';
import { PipelineProgressBar } from './PipelineProgressBar';

interface AppLayoutProps {
  children: ReactNode;
}

// Routes that render bare (no sidebar / pipeline bar) and are reachable while
// unauthenticated — e.g. the login page (issue #336).
const BARE_ROUTES = new Set(['/login']);

/** Neutral full-screen placeholder shown while auth is resolving / redirecting. */
function FullPageLoader() {
  return (
    <div
      className="flex min-h-screen items-center justify-center bg-background"
      role="status"
      aria-label="Loading"
    >
      <Loading03Icon className="h-6 w-6 animate-spin text-muted-foreground" aria-hidden="true" />
    </div>
  );
}

/**
 * Client-side layout shell with a proactive auth guard (issue #651).
 *
 * The JWT lives in localStorage, so a server/edge `middleware.ts` can't see it —
 * the guard must run on the client. Unauthenticated visitors to a protected
 * route are redirected to `/login` and only ever see a neutral loader: the
 * sidebar/shell never renders for them, so there's no "shell → flicker → login"
 * jump. The login page renders bare and owns its own already-authenticated
 * redirect.
 */
export function AppLayout({ children }: AppLayoutProps) {
  const pathname = usePathname();
  const router = useRouter();
  const isBare = !!pathname && BARE_ROUTES.has(pathname);

  // Defer auth-dependent rendering to the client. The first client render must
  // match the server's (both `mounted === false`) to avoid a hydration mismatch.
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  useEffect(() => {
    if (!mounted || isBare) return;
    if (!isAuthenticated()) {
      router.replace('/login');
    }
  }, [mounted, isBare, pathname, router]);

  // Bare routes (login) always render their own content, no guard, no shell.
  if (isBare) {
    return <>{children}</>;
  }

  // Pre-hydration and while redirecting an unauthenticated user: show a neutral
  // loader instead of the shell.
  if (!mounted || !isAuthenticated()) {
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
