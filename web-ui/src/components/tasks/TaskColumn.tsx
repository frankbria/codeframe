'use client';

import { Badge } from '@/components/ui/badge';
import { TaskCard } from './TaskCard';
import type { Task, TaskStatus } from '@/types';

/** Human-readable column headers. */
const STATUS_LABEL: Record<TaskStatus, string> = {
  BACKLOG: 'Backlog',
  READY: 'Ready',
  IN_PROGRESS: 'In Progress',
  DONE: 'Done',
  BLOCKED: 'Blocked',
  FAILED: 'Failed',
  MERGED: 'Merged',
};

interface TaskColumnProps {
  status: TaskStatus;
  tasks: Task[];
  selectionMode: boolean;
  selectedTaskIds: Set<string>;
  onTaskClick: (taskId: string) => void;
  onToggleSelect: (taskId: string) => void;
  onExecute: (taskId: string) => void;
  onMarkReady: (taskId: string) => void;
}

export function TaskColumn({
  status,
  tasks,
  selectionMode,
  selectedTaskIds,
  onTaskClick,
  onToggleSelect,
  onExecute,
  onMarkReady,
}: TaskColumnProps) {
  return (
    <div className="flex min-w-[220px] flex-col rounded-lg bg-muted/30 p-3">
      {/* Column header */}
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          {STATUS_LABEL[status]}
        </h3>
        <Badge variant="outline" className="h-5 px-1.5 text-[10px]">
          {tasks.length}
        </Badge>
      </div>

      {/* Task list */}
      <div className="flex flex-1 flex-col gap-2 overflow-y-auto">
        {tasks.length === 0 ? (
          <p className="py-6 text-center text-xs text-muted-foreground">
            No tasks
          </p>
        ) : (
          tasks.map((task) => (
            <TaskCard
              key={task.id}
              task={task}
              selectionMode={selectionMode}
              selected={selectedTaskIds.has(task.id)}
              onToggleSelect={onToggleSelect}
              onClick={onTaskClick}
              onExecute={onExecute}
              onMarkReady={onMarkReady}
            />
          ))
        )}
      </div>
    </div>
  );
}
