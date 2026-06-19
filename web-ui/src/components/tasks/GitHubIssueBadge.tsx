'use client';

import { GithubIcon } from '@hugeicons/react';

interface GitHubIssueBadgeProps {
  issueNumber: number;
  issueUrl: string;
}

/**
 * A small badge linking an imported task back to its source GitHub issue
 * (issue #565). Opens the issue in a new tab.
 */
export function GitHubIssueBadge({ issueNumber, issueUrl }: GitHubIssueBadgeProps) {
  return (
    <a
      href={issueUrl}
      target="_blank"
      rel="noopener noreferrer"
      onClick={(e) => e.stopPropagation()}
      aria-label={`Imported from GitHub issue #${issueNumber}`}
      className="inline-flex items-center gap-1.5 rounded-md border bg-muted/40 px-2 py-0.5 text-xs font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-hidden focus-visible:ring-[3px] focus-visible:ring-ring"
    >
      <GithubIcon className="h-3.5 w-3.5 shrink-0" />
      Imported from GitHub #{issueNumber}
    </a>
  );
}
