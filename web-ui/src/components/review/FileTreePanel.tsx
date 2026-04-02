'use client';

import { useState, useMemo } from 'react';
import { FileAddIcon, FileRemoveIcon, FileEditIcon, ArrowDown01Icon, ArrowRight01Icon } from '@hugeicons/react';
import { ScrollArea } from '@/components/ui/scroll-area';
import { cn } from '@/lib/utils';
import { getDirectory, getFilename } from '@/lib/diffParser';
import type { FileChange, Task } from '@/types';

interface FileTreePanelProps {
  files: FileChange[];
  selectedFile: string | null;
  onFileSelect: (filePath: string) => void;
  tasks?: Task[];
  contextTask?: Task | null;
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
 * Left sidebar showing changed files grouped by directory or task.
 *
 * Files are organized into collapsible directory groups with
 * per-file insertion/deletion counts and change type icons.
 * When tasks are provided, a toggle allows grouping by task.
 */
export function FileTreePanel({ files, selectedFile, onFileSelect, tasks, contextTask }: FileTreePanelProps) {
  const [collapsedDirs, setCollapsedDirs] = useState<Set<string>>(new Set());
  const [groupBy, setGroupBy] = useState<'dir' | 'task'>('dir');

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

  const groupedByTask = useMemo(() => {
    const groups = new Map<string, { title: string; files: FileChange[] }>();
    for (const file of files) {
      const taskId = file.task_id ?? contextTask?.id ?? 'unassigned';
      const taskTitle =
        file.task_title ??
        tasks?.find((t) => t.id === taskId)?.title ??
        contextTask?.title ??
        'Unassigned';
      const existing = groups.get(taskId);
      if (existing) {
        existing.files.push(file);
      } else {
        groups.set(taskId, { title: taskTitle, files: [file] });
      }
    }
    return groups;
  }, [files, tasks, contextTask]);

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

  const hasTasks = tasks && tasks.length > 0;

  return (
    <div className="flex h-full w-64 shrink-0 flex-col rounded-lg border bg-card">
      <div className="flex items-center justify-between border-b px-3 py-2">
        <span className="text-xs font-semibold text-muted-foreground">
          Files Changed ({files.length})
        </span>
        {hasTasks && (
          <div className="flex gap-0.5">
            <button
              type="button"
              className={cn(
                'rounded px-1.5 py-0.5 text-[10px] transition-all',
                groupBy === 'dir'
                  ? 'bg-accent text-accent-foreground'
                  : 'text-muted-foreground hover:bg-muted/50'
              )}
              onClick={() => setGroupBy('dir')}
              aria-label="Group by directory"
            >
              Dir
            </button>
            <button
              type="button"
              className={cn(
                'rounded px-1.5 py-0.5 text-[10px] transition-all',
                groupBy === 'task'
                  ? 'bg-accent text-accent-foreground'
                  : 'text-muted-foreground hover:bg-muted/50'
              )}
              onClick={() => setGroupBy('task')}
              aria-label="Group by task"
            >
              Task
            </button>
          </div>
        )}
      </div>

      <ScrollArea className="flex-1">
        <div className="p-2">
          {groupBy === 'dir'
            ? Array.from(grouped.entries()).map(([dir, dirFiles]) => {
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
                              {(file.task_title ?? contextTask?.title) && (
                                <span className="mx-1 shrink-0 rounded bg-muted px-1 py-0.5 text-[10px] text-muted-foreground">
                                  {file.task_title ?? contextTask?.title}
                                </span>
                              )}
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
              })
            : Array.from(groupedByTask.entries()).map(([taskId, { title: taskTitle, files: taskFiles }]) => {
                const isCollapsed = collapsedDirs.has(`task:${taskId}`);

                return (
                  <div key={taskId} className="mb-1">
                    <button
                      type="button"
                      className="flex w-full items-center gap-1.5 rounded px-1.5 py-1 text-xs font-medium text-muted-foreground transition-all hover:bg-muted/50"
                      onClick={() => toggleDir(`task:${taskId}`)}
                      aria-expanded={!isCollapsed}
                      aria-label={`${isCollapsed ? 'Expand' : 'Collapse'} ${taskTitle}`}
                    >
                      {isCollapsed ? (
                        <ArrowRight01Icon className="h-3 w-3 shrink-0" />
                      ) : (
                        <ArrowDown01Icon className="h-3 w-3 shrink-0" />
                      )}
                      <span className="h-2 w-2 rounded-full bg-amber-500" />
                      <span className="truncate">{taskTitle}</span>
                      <span className="ml-auto text-[10px] text-muted-foreground/70">
                        {taskFiles.length}
                      </span>
                    </button>

                    {!isCollapsed && (
                      <div className="ml-2">
                        {taskFiles.map((file) => {
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
