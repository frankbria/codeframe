'use client';

import { CheckListIcon, PlayCircleIcon, Loading03Icon, Cancel01Icon, ArrowTurnBackwardIcon } from '@hugeicons/react';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from '@/components/ui/select';
import type { BatchStrategy, Task } from '@/types';

interface BatchActionsBarProps {
  selectionMode: boolean;
  onToggleSelectionMode: () => void;
  selectedCount: number;
  strategy: BatchStrategy;
  onStrategyChange: (strategy: BatchStrategy) => void;
  onExecuteBatch: () => void;
  onClearSelection: () => void;
  isExecuting: boolean;
  selectedTasks?: Task[];
  onStopBatch?: () => void;
  onResetBatch?: () => void;
  isStoppingBatch?: boolean;
  isResettingBatch?: boolean;
}

export function BatchActionsBar({
  selectionMode,
  onToggleSelectionMode,
  selectedCount,
  strategy,
  onStrategyChange,
  onExecuteBatch,
  onClearSelection,
  isExecuting,
  selectedTasks = [],
  onStopBatch,
  onResetBatch,
  isStoppingBatch = false,
  isResettingBatch = false,
}: BatchActionsBarProps) {
  const readyCount = selectedTasks.filter((t) => t.status === 'READY').length;
  const inProgressCount = selectedTasks.filter((t) => t.status === 'IN_PROGRESS').length;
  const failedCount = selectedTasks.filter((t) => t.status === 'FAILED').length;

  return (
    <div className="flex items-center gap-2">
      {/* Toggle selection mode */}
      <Button
        size="sm"
        variant={selectionMode ? 'secondary' : 'outline'}
        onClick={onToggleSelectionMode}
        className="gap-1.5"
      >
        <CheckListIcon className="h-4 w-4" />
        {selectionMode ? 'Cancel' : 'Batch'}
      </Button>

      {/* Batch controls — visible only in selection mode */}
      {selectionMode && (
        <>
          <span className="text-xs text-muted-foreground">
            {selectedCount} selected
          </span>

          {/* Strategy selector — only when READY tasks are selected */}
          {readyCount > 0 && (
            <Select
              value={strategy}
              onValueChange={(v) => onStrategyChange(v as BatchStrategy)}
            >
              <SelectTrigger className="h-8 w-[110px] text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="serial">Serial</SelectItem>
                <SelectItem value="parallel">Parallel</SelectItem>
                <SelectItem value="auto">Auto</SelectItem>
              </SelectContent>
            </Select>
          )}

          {/* Execute button — READY tasks */}
          {readyCount > 0 && (
            <Button
              size="sm"
              disabled={isExecuting}
              onClick={onExecuteBatch}
              className="gap-1.5"
            >
              {isExecuting ? (
                <Loading03Icon className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <PlayCircleIcon className="h-3.5 w-3.5" />
              )}
              Execute {readyCount}
            </Button>
          )}

          {/* Stop button — IN_PROGRESS tasks */}
          {inProgressCount > 0 && onStopBatch && (
            <Button
              size="sm"
              variant="destructive"
              disabled={isStoppingBatch}
              onClick={onStopBatch}
              className="gap-1.5"
            >
              {isStoppingBatch ? (
                <Loading03Icon className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Cancel01Icon className="h-3.5 w-3.5" />
              )}
              Stop {inProgressCount}
            </Button>
          )}

          {/* Reset button — FAILED tasks */}
          {failedCount > 0 && onResetBatch && (
            <Button
              size="sm"
              variant="outline"
              disabled={isResettingBatch}
              onClick={onResetBatch}
              className="gap-1.5"
            >
              {isResettingBatch ? (
                <Loading03Icon className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <ArrowTurnBackwardIcon className="h-3.5 w-3.5" />
              )}
              Reset {failedCount}
            </Button>
          )}

          {selectedCount > 0 && (
            <button
              onClick={onClearSelection}
              className="text-xs text-muted-foreground hover:text-foreground"
            >
              Clear
            </button>
          )}
        </>
      )}
    </div>
  );
}
