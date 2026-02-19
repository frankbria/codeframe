'use client';

import { useMemo } from 'react';
import { TaskColumn } from './TaskColumn';
import type { Task, TaskStatus } from '@/types';

/** Column display order matches the task lifecycle. */
const COLUMN_ORDER: TaskStatus[] = [
  'BACKLOG',
  'READY',
  'IN_PROGRESS',
  'BLOCKED',
  'FAILED',
  'DONE',
];

interface TaskBoardContentProps {
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

export function TaskBoardContent({
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
  loadingTaskIds,
}: TaskBoardContentProps) {
  /** Group flat task array into per-status buckets. */
  const tasksByStatus = useMemo(() => {
    const grouped: Record<string, Task[]> = {};
    for (const status of COLUMN_ORDER) {
      grouped[status] = [];
    }
    for (const task of tasks) {
      if (grouped[task.status]) {
        grouped[task.status].push(task);
      }
    }
    return grouped;
  }, [tasks]);

  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
      {COLUMN_ORDER.map((status) => (
        <TaskColumn
          key={status}
          status={status}
          tasks={tasksByStatus[status]}
          selectionMode={selectionMode}
          selectedTaskIds={selectedTaskIds}
          onTaskClick={onTaskClick}
          onToggleSelect={onToggleSelect}
          onExecute={onExecute}
          onMarkReady={onMarkReady}
          onStop={onStop}
          onReset={onReset}
          onSelectAll={onSelectAll}
          onDeselectAll={onDeselectAll}
          loadingTaskIds={loadingTaskIds}
        />
      ))}
    </div>
  );
}
