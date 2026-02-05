'use client';

import { AppSidebar } from './AppSidebar';

interface AppLayoutProps {
  children: React.ReactNode;
}

/**
 * Client-side layout shell that renders the persistent sidebar
 * alongside the main content area. The sidebar auto-hides when
 * no workspace is selected.
 */
export function AppLayout({ children }: AppLayoutProps) {
  return (
    <div className="flex min-h-screen">
      <AppSidebar />
      <div className="flex-1">{children}</div>
    </div>
  );
}
