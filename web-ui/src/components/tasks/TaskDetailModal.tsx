'use client';

import { useEffect, useState } from 'react';
import {
  PlayCircleIcon,
  CheckmarkCircle01Icon,
  LinkCircleIcon,
  Loading03Icon,
  Time01Icon,
} from '@hugeicons/react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { tasksApi } from '@/lib/api';
import type { Task, TaskStatus, ApiError } from '@/types';

const STATUS_BADGE_VARIANT: Record<TaskStatus, string> = {
  BACKLOG: 'backlog',
  READY: 'ready',
  IN_PROGRESS: 'in-progress',
  DONE: 'done',
  BLOCKED: 'blocked',
  FAILED: 'failed',
  MERGED: 'merged',
};

const STATUS_LABEL: Record<TaskStatus, string> = {
  BACKLOG: 'Backlog',
  READY: 'Ready',
  IN_PROGRESS: 'In Progress',
  DONE: 'Done',
  BLOCKED: 'Blocked',
  FAILED: 'Failed',
  MERGED: 'Merged',
};

interface TaskDetailModalProps {
  taskId: string | null;
  workspacePath: string;
  open: boolean;
  onClose: () => void;
  onExecute: (taskId: string) => void;
  onStatusChange: () => void;
}

export function TaskDetailModal({
  taskId,
  workspacePath,
  open,
  onClose,
  onExecute,
  onStatusChange,
}: TaskDetailModalProps) {
  const [task, setTask] = useState<Task | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isUpdating, setIsUpdating] = useState(false);

  useEffect(() => {
    if (!open || !taskId) {
      setTask(null);
      setError(null);
      return;
    }

    let cancelled = false;
    setIsLoading(true);
    setError(null);

    tasksApi
      .getOne(workspacePath, taskId)
      .then((data) => {
        if (!cancelled) setTask(data);
      })
      .catch((err: ApiError) => {
        if (!cancelled) setError(err.detail || 'Failed to load task');
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [open, taskId, workspacePath]);

  const handleMarkReady = async () => {
    if (!task) return;
    setIsUpdating(true);
    try {
      const updated = await tasksApi.updateStatus(workspacePath, task.id, 'READY');
      setTask(updated);
      onStatusChange();
    } catch (err) {
      const apiErr = err as ApiError;
      setError(apiErr.detail || 'Failed to update status');
    } finally {
      setIsUpdating(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(isOpen) => { if (!isOpen) onClose(); }}>
      <DialogContent className="max-w-xl">
        {isLoading && (
          <div className="flex items-center justify-center py-12">
            <Loading03Icon className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        )}

        {error && !isLoading && (
          <div className="rounded-md bg-destructive/10 px-4 py-3 text-sm text-destructive">
            {error}
          </div>
        )}

        {task && !isLoading && (
          <>
            <DialogHeader>
              <div className="flex items-center gap-2">
                <Badge variant={STATUS_BADGE_VARIANT[task.status] as never}>
                  {STATUS_LABEL[task.status]}
                </Badge>
                {task.priority > 0 && (
                  <span className="text-xs text-muted-foreground">
                    Priority {task.priority}
                  </span>
                )}
              </div>
              <DialogTitle className="mt-1">{task.title}</DialogTitle>
              <DialogDescription className="sr-only">
                Details for task {task.title}
              </DialogDescription>
            </DialogHeader>

            {/* Description */}
            <div className="max-h-[300px] overflow-y-auto">
              {task.description ? (
                <p className="whitespace-pre-wrap text-sm text-foreground">
                  {task.description}
                </p>
              ) : (
                <p className="text-sm italic text-muted-foreground">
                  No description.
                </p>
              )}
            </div>

            {/* Metadata */}
            <div className="flex flex-wrap gap-4 text-xs text-muted-foreground">
              {task.depends_on.length > 0 && (
                <span className="flex items-center gap-1">
                  <LinkCircleIcon className="h-3.5 w-3.5" />
                  {task.depends_on.length} dependenc{task.depends_on.length === 1 ? 'y' : 'ies'}:
                  {' '}{task.depends_on.map((id) => id.slice(0, 8)).join(', ')}
                </span>
              )}
              {task.estimated_hours != null && (
                <span className="flex items-center gap-1">
                  <Time01Icon className="h-3.5 w-3.5" />
                  {task.estimated_hours}h estimated
                </span>
              )}
            </div>

            <DialogFooter>
              {task.status === 'BACKLOG' && (
                <Button
                  variant="outline"
                  size="sm"
                  disabled={isUpdating}
                  onClick={handleMarkReady}
                >
                  {isUpdating ? (
                    <Loading03Icon className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <CheckmarkCircle01Icon className="mr-1.5 h-3.5 w-3.5" />
                  )}
                  Mark Ready
                </Button>
              )}
              {task.status === 'READY' && (
                <Button
                  size="sm"
                  onClick={() => onExecute(task.id)}
                >
                  <PlayCircleIcon className="mr-1.5 h-3.5 w-3.5" />
                  Execute
                </Button>
              )}
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
