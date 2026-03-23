'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Tick01Icon } from '@hugeicons/react';
import { cn } from '@/lib/utils';
import { usePipelineStatus } from '@/hooks/usePipelineStatus';

interface Phase {
  key: 'think' | 'build' | 'prove' | 'ship';
  label: string;
  href: string;
  paths: string[];
}

const PHASES: Phase[] = [
  { key: 'think', label: 'Think', href: '/prd', paths: ['/prd'] },
  { key: 'build', label: 'Build', href: '/tasks', paths: ['/tasks', '/execution', '/blockers'] },
  { key: 'prove', label: 'Prove', href: '/proof', paths: ['/proof'] },
  { key: 'ship', label: 'Ship', href: '/review', paths: ['/review'] },
];

function getActivePhase(pathname: string): string | null {
  for (const phase of PHASES) {
    if (phase.paths.some((p) => pathname === p || pathname.startsWith(p + '/'))) {
      return phase.key;
    }
  }
  return null;
}

export function PipelineProgressBar() {
  const pathname = usePathname();
  const status = usePipelineStatus();

  // Hide on root (workspace selector) and any path with no matching phase
  if (pathname === '/') return null;

  const activePhase = getActivePhase(pathname);

  return (
    <nav
      aria-label="Pipeline progress"
      className="sticky top-0 z-10 flex items-center justify-center gap-0 border-b bg-card px-4 py-2 shadow-sm"
    >
      {PHASES.map((phase, index) => {
        const phaseStatus = status[phase.key];
        const isActive = activePhase === phase.key;
        const isComplete = phaseStatus.isComplete;
        const isUpcoming = !isActive && !isComplete;

        return (
          <div key={phase.key} className="flex items-center">
            <Link
              href={phase.href}
              className={cn(
                'flex min-h-[44px] min-w-[44px] items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors',
                isActive && 'bg-accent text-accent-foreground',
                isComplete && !isActive && 'text-primary',
                isUpcoming && 'text-muted-foreground hover:text-foreground'
              )}
              aria-current={isActive ? 'step' : undefined}
            >
              {isComplete ? (
                <Tick01Icon className="h-4 w-4 shrink-0" />
              ) : (
                <span
                  className={cn(
                    'flex h-5 w-5 shrink-0 items-center justify-center rounded-full border text-xs',
                    isActive
                      ? 'border-accent-foreground bg-accent-foreground text-accent'
                      : 'border-muted-foreground'
                  )}
                >
                  {index + 1}
                </span>
              )}
              <span className="hidden lg:inline">{phase.label}</span>
              <span className="lg:hidden">{phase.label.charAt(0)}</span>
            </Link>

            {index < PHASES.length - 1 && (
              <span className="mx-1 text-muted-foreground" aria-hidden>
                →
              </span>
            )}
          </div>
        );
      })}
    </nav>
  );
}
