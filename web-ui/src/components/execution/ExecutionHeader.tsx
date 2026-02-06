'use client';

import { useState } from 'react';
import { StopIcon, Loading03Icon } from '@hugeicons/react';
import { Button } from '@/components/ui/button';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog';
import { cn } from '@/lib/utils';
import {
  agentStateBadgeStyles,
  agentStateLabels,
  agentStateIcons,
  connectionDotStyles,
} from '@/lib/eventStyles';
import type { Task, UIAgentState } from '@/types';
import type { SSEStatus } from '@/hooks/useEventSource';

interface ExecutionHeaderProps {
  task: Task | null;
  agentState: UIAgentState;
  sseStatus: SSEStatus;
  onStop: () => void;
  isCompleted: boolean;
}

export function ExecutionHeader({
  task,
  agentState,
  sseStatus,
  onStop,
  isCompleted,
}: ExecutionHeaderProps) {
  const [isStopping, setIsStopping] = useState(false);
  const StateIcon = agentStateIcons[agentState];

  const handleStop = async () => {
    setIsStopping(true);
    try {
      onStop();
    } finally {
      setIsStopping(false);
    }
  };

  return (
    <div className="flex items-center justify-between gap-4 rounded-lg border bg-card p-4">
      {/* Left: task info + agent state */}
      <div className="min-w-0 flex-1">
        <h1 className="truncate text-lg font-semibold tracking-tight">
          {task?.title ?? 'Loading task...'}
        </h1>
        {task?.description && (
          <p className="mt-0.5 truncate text-sm text-muted-foreground">
            {task.description}
          </p>
        )}
      </div>

      {/* Center: agent state badge */}
      <div className="flex items-center gap-2">
        <span
          className={cn(
            'inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-semibold',
            agentStateBadgeStyles[agentState]
          )}
        >
          <StateIcon className="h-3.5 w-3.5" />
          {agentStateLabels[agentState]}
        </span>
      </div>

      {/* Right: connection dot + stop button */}
      <div className="flex items-center gap-3">
        {/* Connection status dot */}
        <div className="flex items-center gap-1.5">
          <span
            className={cn(
              'inline-block h-2 w-2 rounded-full',
              connectionDotStyles[sseStatus] ?? connectionDotStyles.idle
            )}
            title={`Connection: ${sseStatus}`}
          />
          <span className="text-[10px] text-muted-foreground">{sseStatus}</span>
        </div>

        {/* Stop button with confirmation */}
        <AlertDialog>
          <AlertDialogTrigger asChild>
            <Button
              variant="destructive"
              size="sm"
              className="h-8 gap-1.5 px-3"
              disabled={isCompleted || isStopping}
            >
              {isStopping ? (
                <Loading03Icon className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <StopIcon className="h-3.5 w-3.5" />
              )}
              Stop
            </Button>
          </AlertDialogTrigger>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Stop Execution?</AlertDialogTitle>
              <AlertDialogDescription>
                This will stop the AI agent&apos;s current work on{' '}
                <strong>{task?.title ?? 'this task'}</strong>. Any in-progress
                file changes may be left incomplete.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Cancel</AlertDialogCancel>
              <AlertDialogAction onClick={handleStop}>
                Stop Execution
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </div>
    </div>
  );
}
