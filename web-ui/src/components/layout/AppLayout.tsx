'use client';

import type { ReactNode } from 'react';
import { AppSidebar } from './AppSidebar';
import { PipelineProgressBar } from './PipelineProgressBar';

interface AppLayoutProps {
  children: ReactNode;
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
      <div className="flex flex-1 flex-col">
        <PipelineProgressBar />
        {children}
      </div>
    </div>
  );
}
