'use client';

import { useMemo } from 'react';
import { TaskColumn } from './TaskColumn';
import type { Task, TaskStatus, ProofRequirement, TaskCostEntry } from '@/types';

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
  requirementsMap?: Map<string, ProofRequirement>;
  costMap?: Map<string, TaskCostEntry>;
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
  requirementsMap,
  costMap,
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
    // Six columns never shrink below a card's 220px: grid-cols-6 tracks did,
    // so columns overlapped and Done was clipped at 1280-1440px (#1297). The
    // board scrolls sideways instead.
    <div className="overflow-x-auto pb-2">
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-[repeat(6,minmax(220px,1fr))]">
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
            requirementsMap={requirementsMap}
            costMap={costMap}
          />
        ))}
      </div>
    </div>
  );
}
