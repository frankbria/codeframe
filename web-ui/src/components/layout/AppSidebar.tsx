'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  Home01Icon,
  FileEditIcon,
  Task01Icon,
  PlayIcon,
  Alert02Icon,
  GitBranchIcon,
} from '@hugeicons/react';
import { getSelectedWorkspacePath } from '@/lib/workspace-storage';

interface NavItem {
  href: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  enabled: boolean;
}

const NAV_ITEMS: NavItem[] = [
  { href: '/', label: 'Workspace', icon: Home01Icon, enabled: true },
  { href: '/prd', label: 'PRD', icon: FileEditIcon, enabled: true },
  { href: '/tasks', label: 'Tasks', icon: Task01Icon, enabled: false },
  { href: '/execution', label: 'Execution', icon: PlayIcon, enabled: false },
  { href: '/blockers', label: 'Blockers', icon: Alert02Icon, enabled: false },
  { href: '/review', label: 'Review', icon: GitBranchIcon, enabled: false },
];

export function AppSidebar() {
  const pathname = usePathname();
  const [hasWorkspace, setHasWorkspace] = useState(false);

  useEffect(() => {
    setHasWorkspace(!!getSelectedWorkspacePath());
  }, []);

  // Listen for storage changes (workspace selection/deselection)
  useEffect(() => {
    const handleStorage = () => {
      setHasWorkspace(!!getSelectedWorkspacePath());
    };
    window.addEventListener('storage', handleStorage);
    return () => window.removeEventListener('storage', handleStorage);
  }, []);

  // Don't render sidebar when no workspace is selected
  if (!hasWorkspace) return null;

  return (
    <aside className="sticky top-0 flex h-screen w-14 flex-col border-r bg-card py-4 lg:w-48">
      {/* Logo */}
      <div className="mb-6 flex items-center justify-center px-3 lg:justify-start">
        <span className="text-sm font-bold tracking-tight text-foreground lg:text-base">
          <span className="hidden lg:inline">CodeFRAME</span>
          <span className="lg:hidden">CF</span>
        </span>
      </div>

      {/* Navigation */}
      <nav className="flex flex-1 flex-col gap-1 px-2">
        {NAV_ITEMS.map(({ href, label, icon: Icon, enabled }) => {
          const isActive = href === '/'
            ? pathname === '/'
            : pathname.startsWith(href);

          if (!enabled) {
            return (
              <span
                key={href}
                className="flex items-center gap-3 rounded-md px-2 py-2 text-sm text-muted-foreground/50 lg:px-3"
                title={`${label} (coming soon)`}
              >
                <Icon className="h-5 w-5 shrink-0" />
                <span className="hidden lg:inline">{label}</span>
              </span>
            );
          }

          return (
            <Link
              key={href}
              href={href}
              className={`flex items-center gap-3 rounded-md px-2 py-2 text-sm transition-colors lg:px-3 ${
                isActive
                  ? 'bg-accent font-medium text-accent-foreground'
                  : 'text-muted-foreground hover:bg-accent/50 hover:text-foreground'
              }`}
            >
              <Icon className="h-5 w-5 shrink-0" />
              <span className="hidden lg:inline">{label}</span>
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
