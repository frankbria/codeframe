'use client';

import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
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
  onStop?: (taskId: string) => void;
  onReset?: (taskId: string) => void;
  onSelectAll?: (taskIds: string[]) => void;
  onDeselectAll?: (taskIds: string[]) => void;
  loadingTaskIds?: Set<string>;
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
  onStop,
  onReset,
  onSelectAll,
  onDeselectAll,
  loadingTaskIds = new Set(),
}: TaskColumnProps) {
  const taskIds = tasks.map((t) => t.id);
  const selectedCount = tasks.filter((t) => selectedTaskIds.has(t.id)).length;
  const allSelected = tasks.length > 0 && selectedCount === tasks.length;
  const someSelected = selectedCount > 0 && selectedCount < tasks.length;

  return (
    <div className="flex min-w-[220px] flex-col rounded-lg bg-muted/30 p-3">
      {/* Column header */}
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          {selectionMode && tasks.length > 0 && (
            <Checkbox
              checked={allSelected ? true : someSelected ? 'indeterminate' : false}
              onCheckedChange={() => {
                if (allSelected) {
                  onDeselectAll?.(taskIds);
                } else {
                  onSelectAll?.(taskIds);
                }
              }}
              aria-label={`Select all ${STATUS_LABEL[status]} tasks`}
            />
          )}
          <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            {STATUS_LABEL[status]}
          </h3>
        </div>
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
              onStop={onStop}
              onReset={onReset}
              isLoading={loadingTaskIds.has(task.id)}
            />
          ))
        )}
      </div>
    </div>
  );
}
