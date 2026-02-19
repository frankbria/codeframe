'use client';

import { useState, useMemo } from 'react';
import { FileAddIcon, FileRemoveIcon, FileEditIcon, ArrowDown01Icon, ArrowRight01Icon } from '@hugeicons/react';
import { ScrollArea } from '@/components/ui/scroll-area';
import { cn } from '@/lib/utils';
import { getDirectory, getFilename } from '@/lib/diffParser';
import type { FileChange } from '@/types';

interface FileTreePanelProps {
  files: FileChange[];
  selectedFile: string | null;
  onFileSelect: (filePath: string) => void;
}

const changeTypeIcon: Record<FileChange['change_type'], React.ComponentType<{ className?: string }>> = {
  added: FileAddIcon,
  deleted: FileRemoveIcon,
  modified: FileEditIcon,
  renamed: FileEditIcon,
};

const changeTypeColor: Record<FileChange['change_type'], string> = {
  added: 'text-green-600',
  deleted: 'text-red-600',
  modified: 'text-amber-600',
  renamed: 'text-blue-600',
};

/**
 * Left sidebar showing changed files grouped by directory.
 *
 * Files are organized into collapsible directory groups with
 * per-file insertion/deletion counts and change type icons.
 */
export function FileTreePanel({ files, selectedFile, onFileSelect }: FileTreePanelProps) {
  const [collapsedDirs, setCollapsedDirs] = useState<Set<string>>(new Set());

  const grouped = useMemo(() => {
    const groups = new Map<string, FileChange[]>();
    for (const file of files) {
      const dir = getDirectory(file.path) || '(root)';
      const existing = groups.get(dir);
      if (existing) {
        existing.push(file);
      } else {
        groups.set(dir, [file]);
      }
    }
    return groups;
  }, [files]);

  function toggleDir(dir: string) {
    setCollapsedDirs((prev) => {
      const next = new Set(prev);
      if (next.has(dir)) {
        next.delete(dir);
      } else {
        next.add(dir);
      }
      return next;
    });
  }

  return (
    <div className="flex h-full w-64 shrink-0 flex-col rounded-lg border bg-card">
      <div className="border-b px-3 py-2">
        <span className="text-xs font-semibold text-muted-foreground">
          Files Changed ({files.length})
        </span>
      </div>

      <ScrollArea className="flex-1">
        <div className="p-2">
          {Array.from(grouped.entries()).map(([dir, dirFiles]) => {
            const isCollapsed = collapsedDirs.has(dir);

            return (
              <div key={dir} className="mb-1">
                <button
                  type="button"
                  className="flex w-full items-center gap-1 rounded px-1.5 py-1 text-xs font-medium text-muted-foreground transition-all hover:bg-muted/50"
                  onClick={() => toggleDir(dir)}
                  aria-expanded={!isCollapsed}
                  aria-label={`${isCollapsed ? 'Expand' : 'Collapse'} ${dir}`}
                >
                  {isCollapsed ? (
                    <ArrowRight01Icon className="h-3 w-3 shrink-0" />
                  ) : (
                    <ArrowDown01Icon className="h-3 w-3 shrink-0" />
                  )}
                  <span className="truncate font-mono">{dir}</span>
                  <span className="ml-auto text-[10px] text-muted-foreground/70">
                    {dirFiles.length}
                  </span>
                </button>

                {!isCollapsed && (
                  <div className="ml-2">
                    {dirFiles.map((file) => {
                      const Icon = changeTypeIcon[file.change_type];
                      const iconColor = changeTypeColor[file.change_type];
                      const isSelected = selectedFile === file.path;

                      return (
                        <button
                          type="button"
                          key={file.path}
                          className={cn(
                            'flex w-full items-center gap-1.5 rounded px-2 py-1 text-xs transition-all',
                            isSelected
                              ? 'bg-accent text-accent-foreground'
                              : 'hover:bg-muted/50'
                          )}
                          onClick={() => onFileSelect(file.path)}
                          title={file.path}
                          aria-current={isSelected ? 'true' : undefined}
                        >
                          <Icon className={cn('h-3.5 w-3.5 shrink-0', iconColor)} />
                          <span className="truncate font-mono">
                            {getFilename(file.path)}
                          </span>
                          <span className="ml-auto flex shrink-0 gap-1 font-mono text-[10px]">
                            {file.insertions > 0 && (
                              <span className="text-green-600">+{file.insertions}</span>
                            )}
                            {file.deletions > 0 && (
                              <span className="text-red-600">-{file.deletions}</span>
                            )}
                          </span>
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </ScrollArea>
    </div>
  );
}
