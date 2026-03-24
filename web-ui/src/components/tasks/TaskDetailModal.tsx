'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  PlayCircleIcon,
  CheckmarkCircle01Icon,
  LinkCircleIcon,
  Loading03Icon,
  Time01Icon,
  ViewIcon,
  BookOpen01Icon,
  Alert02Icon,
  CheckListIcon,
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
import { useRequirementsLookup } from '@/hooks/useRequirementsLookup';
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
  const router = useRouter();
  const [task, setTask] = useState<Task | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isUpdating, setIsUpdating] = useState(false);
  const { requirementsMap, isLoading: reqsLoading } = useRequirementsLookup(workspacePath);

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
        {/* Accessibility: DialogTitle must always be present for screen readers */}
        {(!task || isLoading) && (
          <>
            <DialogTitle className="sr-only">Task Details</DialogTitle>
            <DialogDescription className="sr-only">Loading task details</DialogDescription>
          </>
        )}

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

            {/* Requirements */}
            {(task.requirement_ids ?? []).length > 0 && (
              <div className="space-y-1.5">
                <div className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
                  <BookOpen01Icon className="h-3.5 w-3.5" />
                  Requirements
                </div>
                {reqsLoading ? (
                  <Loading03Icon className="h-3.5 w-3.5 animate-spin text-muted-foreground" />
                ) : (
                  <ul className="space-y-1">
                    {(task.requirement_ids ?? []).map((reqId) => {
                      const req = requirementsMap.get(reqId);
                      return (
                        <li key={reqId} className="flex items-start gap-2 text-xs">
                          <Link
                            href={`/proof/${encodeURIComponent(reqId)}`}
                            className="font-mono text-primary hover:underline"
                            onClick={(e) => e.stopPropagation()}
                          >
                            {reqId}
                          </Link>
                          {req && (
                            <span className="text-foreground">{req.title}</span>
                          )}
                          {req?.glitch_type && (
                            <span className="ml-auto text-muted-foreground">{req.glitch_type}</span>
                          )}
                        </li>
                      );
                    })}
                  </ul>
                )}
              </div>
            )}

            {/* FAILED-state guidance panel */}
            {task.status === 'FAILED' && (
              <div className="rounded-md border border-destructive/40 bg-destructive/5 px-3 py-2.5">
                <div className="flex items-start gap-2">
                  <Alert02Icon className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
                  <div className="space-y-0.5">
                    <p className="text-xs font-medium text-destructive">Task failed during execution</p>
                    <p className="text-xs text-muted-foreground">
                      Check PROOF9 gates to identify which quality requirements need attention.
                      {(task.requirement_ids ?? []).length === 0 && (
                        <> Use the button below to view all gates.</>
                      )}
                    </p>
                  </div>
                </div>
              </div>
            )}

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
              {task.status === 'IN_PROGRESS' && (
                <Button
                  size="sm"
                  onClick={() => {
                    onClose();
                    router.push(`/execution/${task.id}`);
                  }}
                >
                  <ViewIcon className="mr-1.5 h-3.5 w-3.5" />
                  View Execution
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
              {task.status === 'FAILED' && (() => {
                // Derive the best proof link from requirement obligations if available
                let proofLink = '/proof';
                for (const reqId of (task.requirement_ids ?? [])) {
                  const req = requirementsMap.get(reqId);
                  const gate = req?.obligations?.[0]?.gate?.toLowerCase();
                  if (gate) { proofLink = `/proof?gate=${encodeURIComponent(gate)}`; break; }
                }
                return (
                  <>
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
                      Reset to Ready
                    </Button>
                    <Button
                      size="sm"
                      onClick={() => {
                        onClose();
                        router.push(proofLink);
                      }}
                    >
                      <CheckListIcon className="mr-1.5 h-3.5 w-3.5" />
                      View PROOF9 Gates
                    </Button>
                  </>
                );
              })()}
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
