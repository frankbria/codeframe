'use client';

import { CheckListIcon, PlayCircleIcon, Loading03Icon } from '@hugeicons/react';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from '@/components/ui/select';
import type { BatchStrategy } from '@/types';

interface BatchActionsBarProps {
  selectionMode: boolean;
  onToggleSelectionMode: () => void;
  selectedCount: number;
  strategy: BatchStrategy;
  onStrategyChange: (strategy: BatchStrategy) => void;
  onExecuteBatch: () => void;
  onClearSelection: () => void;
  isExecuting: boolean;
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
}: BatchActionsBarProps) {
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

          <Button
            size="sm"
            disabled={selectedCount === 0 || isExecuting}
            onClick={onExecuteBatch}
            className="gap-1.5"
          >
            {isExecuting ? (
              <Loading03Icon className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <PlayCircleIcon className="h-3.5 w-3.5" />
            )}
            Execute
          </Button>

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
