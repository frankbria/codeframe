'use client';

import type { ReactNode } from 'react';
import { usePathname } from 'next/navigation';
import { AppSidebar } from './AppSidebar';
import { PipelineProgressBar } from './PipelineProgressBar';

interface AppLayoutProps {
  children: ReactNode;
}

// Routes that render bare (no sidebar / pipeline bar) — e.g. the login page,
// which is shown when the user is unauthenticated (issue #336).
const BARE_ROUTES = new Set(['/login']);

/**
 * Client-side layout shell that renders the persistent sidebar
 * alongside the main content area. The sidebar auto-hides when
 * no workspace is selected. The login page renders bare.
 */
export function AppLayout({ children }: AppLayoutProps) {
  const pathname = usePathname();

  if (pathname && BARE_ROUTES.has(pathname)) {
    return <>{children}</>;
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
