'use client';

import { Fragment, useRef, useEffect, useState, useCallback, useMemo } from 'react';
import { ArrowDown01Icon, ArrowRight01Icon } from '@hugeicons/react';
import { ScrollArea } from '@/components/ui/scroll-area';
import { cn } from '@/lib/utils';
import type { DiffFile, DiffHunkLine } from '@/lib/diffParser';
import { getFilePath } from '@/lib/diffParser';

interface DiffViewerProps {
  diffFiles: DiffFile[];
  selectedFile: string | null;
}

function lineClassName(type: DiffHunkLine['type']): string {
  switch (type) {
    case 'addition':
      return 'bg-green-500/10';
    case 'deletion':
      return 'bg-red-500/10';
    default:
      return '';
  }
}

function lineNumberClassName(type: DiffHunkLine['type']): string {
  switch (type) {
    case 'addition':
      return 'text-green-600 bg-green-500/5';
    case 'deletion':
      return 'text-red-600 bg-red-500/5';
    default:
      return 'text-muted-foreground';
  }
}

function contentClassName(type: DiffHunkLine['type']): string {
  switch (type) {
    case 'addition':
      return 'text-green-600';
    case 'deletion':
      return 'text-red-600';
    default:
      return 'text-foreground';
  }
}

function linePrefix(type: DiffHunkLine['type']): string {
  switch (type) {
    case 'addition':
      return '+';
    case 'deletion':
      return '-';
    default:
      return ' ';
  }
}

/**
 * Main diff viewer showing syntax-highlighted unified diffs.
 *
 * Renders each file as a collapsible section with sticky headers,
 * hunk separators, and dual-column line numbers. When a file is
 * selected via FileTreePanel, the viewer scrolls to that section.
 */
export function DiffViewer({ diffFiles, selectedFile }: DiffViewerProps) {
  const fileRefs = useRef<Map<string, HTMLDivElement>>(new Map());
  const [collapsedFiles, setCollapsedFiles] = useState<Set<string>>(new Set());

  const fileKeys = useMemo(
    () => diffFiles.map((f) => getFilePath(f)),
    [diffFiles]
  );

  // Scroll to selected file
  useEffect(() => {
    if (!selectedFile) return;
    for (const [key, el] of fileRefs.current.entries()) {
      if (key === selectedFile) {
        el.scrollIntoView({ behavior: 'smooth', block: 'start' });
        break;
      }
    }
  }, [selectedFile]);

  const setFileRef = useCallback((key: string, el: HTMLDivElement | null) => {
    if (el) {
      fileRefs.current.set(key, el);
    } else {
      fileRefs.current.delete(key);
    }
  }, []);

  function toggleFile(key: string) {
    setCollapsedFiles((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  }

  if (diffFiles.length === 0) {
    return (
      <div className="flex flex-1 items-center justify-center rounded-lg border bg-card">
        <p className="text-sm text-muted-foreground">No changes to display</p>
      </div>
    );
  }

  return (
    <ScrollArea className="flex-1 rounded-lg border bg-card">
      <div className="divide-y">
        {diffFiles.map((file, fileIndex) => {
          const key = fileKeys[fileIndex];
          const isCollapsed = collapsedFiles.has(key);
          const isHighlighted =
            selectedFile !== null &&
            (key.includes(selectedFile) || selectedFile.includes(key));

          return (
            <div
              key={key}
              ref={(el) => setFileRef(key, el)}
              className={cn(
                'transition-all',
                isHighlighted && 'ring-2 ring-ring ring-offset-1'
              )}
            >
              {/* File header */}
              <button
                type="button"
                className="sticky top-0 z-10 flex w-full items-center gap-2 border-b bg-muted/50 px-4 py-2 text-left backdrop-blur-sm transition-all hover:bg-muted/70"
                onClick={() => toggleFile(key)}
                aria-expanded={!isCollapsed}
                aria-label={`${isCollapsed ? 'Expand' : 'Collapse'} ${key}`}
              >
                {isCollapsed ? (
                  <ArrowRight01Icon className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                ) : (
                  <ArrowDown01Icon className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                )}
                <span className="truncate font-mono text-sm font-medium">
                  {key}
                </span>
                <span className="ml-auto flex shrink-0 gap-2 text-xs">
                  {file.insertions > 0 && (
                    <span className="font-mono text-green-600">
                      +{file.insertions}
                    </span>
                  )}
                  {file.deletions > 0 && (
                    <span className="font-mono text-red-600">
                      -{file.deletions}
                    </span>
                  )}
                </span>
              </button>

              {/* File diff content */}
              {!isCollapsed && (
                <div className="overflow-x-auto">
                  <table className="w-full border-collapse font-mono text-sm">
                    <tbody>
                      {file.hunks.map((hunk, hunkIndex) => (
                        <Fragment key={`hunk-${hunkIndex}`}>
                          {/* Hunk header */}
                          <tr>
                            <td
                              colSpan={3}
                              className="bg-blue-500/5 px-4 py-1 text-xs text-blue-600"
                            >
                              {hunk.header}
                            </td>
                          </tr>

                          {/* Hunk lines */}
                          {hunk.lines.map((line, lineIndex) => (
                            <tr
                              key={`${hunkIndex}-${lineIndex}`}
                              className={lineClassName(line.type)}
                            >
                              <td
                                className={cn(
                                  'w-12 select-none border-r px-2 py-0 text-right text-xs',
                                  lineNumberClassName(line.type)
                                )}
                              >
                                {line.oldLineNumber ?? ''}
                              </td>
                              <td
                                className={cn(
                                  'w-12 select-none border-r px-2 py-0 text-right text-xs',
                                  lineNumberClassName(line.type)
                                )}
                              >
                                {line.newLineNumber ?? ''}
                              </td>
                              <td
                                className={cn(
                                  'whitespace-pre px-4 py-0',
                                  contentClassName(line.type)
                                )}
                              >
                                <span className="select-none opacity-50">
                                  {linePrefix(line.type)}
                                </span>
                                {line.content}
                              </td>
                            </tr>
                          ))}
                        </Fragment>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </ScrollArea>
  );
}
