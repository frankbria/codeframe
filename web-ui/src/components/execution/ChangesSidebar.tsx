'use client';

import { useState } from 'react';
import { FileEditIcon, SidebarLeftIcon } from '@hugeicons/react';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';

interface ChangesSidebarProps {
  /** List of file paths modified during execution. */
  changedFiles: string[];
}

/**
 * Collapsible right sidebar showing files changed during execution.
 *
 * Renders a simple file list (not a nested tree — YAGNI until we have
 * enough files to warrant it). Each file shows its path as a truncated
 * monospace string.
 */
export function ChangesSidebar({ changedFiles }: ChangesSidebarProps) {
  const [collapsed, setCollapsed] = useState(false);

  if (changedFiles.length === 0) return null;

  return (
    <div
      className={`shrink-0 rounded-lg border bg-card transition-all ${
        collapsed ? 'w-10' : 'w-64'
      }`}
    >
      {/* Header with toggle */}
      <div className="flex items-center justify-between border-b px-3 py-2">
        {!collapsed && (
          <span className="text-xs font-semibold text-muted-foreground">
            Changes ({changedFiles.length})
          </span>
        )}
        <Button
          variant="ghost"
          size="sm"
          className="h-6 w-6 p-0"
          onClick={() => setCollapsed(!collapsed)}
          title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          aria-expanded={!collapsed}
        >
          <SidebarLeftIcon className="h-3.5 w-3.5" />
        </Button>
      </div>

      {/* File list */}
      {!collapsed && (
        <ScrollArea className="h-[calc(100%-37px)]">
          <div className="p-2">
            {changedFiles.map((filePath) => (
              <div
                key={filePath}
                className="flex items-center gap-1.5 rounded px-2 py-1 text-xs hover:bg-muted/50"
                title={filePath}
              >
                <FileEditIcon className="h-3 w-3 shrink-0 text-muted-foreground" />
                <span className="truncate font-mono">{filePath}</span>
              </div>
            ))}
          </div>
        </ScrollArea>
      )}
    </div>
  );
}
