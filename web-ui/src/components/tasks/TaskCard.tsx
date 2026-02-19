'use client';

import { PlayCircleIcon, CheckmarkCircle01Icon, LinkCircleIcon, Cancel01Icon, ArrowTurnBackwardIcon, Loading03Icon } from '@hugeicons/react';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import type { Task, TaskStatus } from '@/types';

/** Map backend TaskStatus to badge variant name. */
const STATUS_BADGE_VARIANT: Record<TaskStatus, string> = {
  BACKLOG: 'backlog',
  READY: 'ready',
  IN_PROGRESS: 'in-progress',
  DONE: 'done',
  BLOCKED: 'blocked',
  FAILED: 'failed',
  MERGED: 'merged',
};

/** Human-readable status labels. */
const STATUS_LABEL: Record<TaskStatus, string> = {
  BACKLOG: 'Backlog',
  READY: 'Ready',
  IN_PROGRESS: 'In Progress',
  DONE: 'Done',
  BLOCKED: 'Blocked',
  FAILED: 'Failed',
  MERGED: 'Merged',
};

interface TaskCardProps {
  task: Task;
  selectionMode: boolean;
  selected: boolean;
  onToggleSelect: (taskId: string) => void;
  onClick: (taskId: string) => void;
  onExecute: (taskId: string) => void;
  onMarkReady: (taskId: string) => void;
  /** Optional — when omitted, IN_PROGRESS cards silently hide the Stop button. TaskBoardView always provides this. */
  onStop?: (taskId: string) => void;
  /** Optional — when omitted, FAILED cards silently hide the Reset button. TaskBoardView always provides this. */
  onReset?: (taskId: string) => void;
  isLoading?: boolean;
}

export function TaskCard({
  task,
  selectionMode,
  selected,
  onToggleSelect,
  onClick,
  onExecute,
  onMarkReady,
  onStop,
  onReset,
  isLoading = false,
}: TaskCardProps) {
  return (
    <Card
      className="cursor-pointer transition-colors hover:border-primary/50 focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-ring"
      onClick={() => onClick(task.id)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onClick(task.id);
        }
      }}
      role="button"
      tabIndex={0}
      aria-label={`View details for ${task.title}`}
    >
      <CardContent className="p-3">
        {/* Top row: checkbox (if selection mode) + status badge */}
        <div className="mb-2 flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            {selectionMode && (
              <Checkbox
                checked={selected}
                onCheckedChange={() => onToggleSelect(task.id)}
                onClick={(e) => e.stopPropagation()}
                aria-label={`Select ${task.title}`}
              />
            )}
            <Badge
              variant={STATUS_BADGE_VARIANT[task.status] as never}
            >
              {STATUS_LABEL[task.status]}
            </Badge>
          </div>
          {task.depends_on.length > 0 && (
            <span className="flex items-center gap-1 text-xs text-muted-foreground" title={`Depends on ${task.depends_on.length} task(s)`}>
              <LinkCircleIcon className="h-3.5 w-3.5" />
              {task.depends_on.length}
            </span>
          )}
        </div>

        {/* Title */}
        <h4 className="truncate text-sm font-medium">{task.title}</h4>

        {/* Description snippet */}
        {task.description && (
          <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">
            {task.description}
          </p>
        )}

        {/* Action buttons */}
        {(task.status === 'READY' || task.status === 'BACKLOG' || task.status === 'IN_PROGRESS' || task.status === 'FAILED') && (
          <div className="mt-2 flex gap-1">
            {isLoading ? (
              <span role="status" aria-label="Loading">
                <Loading03Icon className="h-3.5 w-3.5 animate-spin text-muted-foreground" />
              </span>
            ) : (
              <>
                {task.status === 'READY' && (
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-7 gap-1 px-2 text-xs"
                    onClick={(e) => {
                      e.stopPropagation();
                      onExecute(task.id);
                    }}
                  >
                    <PlayCircleIcon className="h-3.5 w-3.5" />
                    Execute
                  </Button>
                )}
                {task.status === 'BACKLOG' && (
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-7 gap-1 px-2 text-xs"
                    onClick={(e) => {
                      e.stopPropagation();
                      onMarkReady(task.id);
                    }}
                  >
                    <CheckmarkCircle01Icon className="h-3.5 w-3.5" />
                    Mark Ready
                  </Button>
                )}
                {task.status === 'IN_PROGRESS' && onStop && (
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-7 gap-1 px-2 text-xs text-destructive"
                    onClick={(e) => {
                      e.stopPropagation();
                      onStop(task.id);
                    }}
                  >
                    <Cancel01Icon className="h-3.5 w-3.5" />
                    Stop
                  </Button>
                )}
                {task.status === 'FAILED' && onReset && (
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-7 gap-1 px-2 text-xs"
                    onClick={(e) => {
                      e.stopPropagation();
                      onReset(task.id);
                    }}
                  >
                    <ArrowTurnBackwardIcon className="h-3.5 w-3.5" />
                    Reset
                  </Button>
                )}
              </>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
