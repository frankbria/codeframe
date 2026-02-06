'use client';

import { cn } from '@/lib/utils';
import {
  deriveAgentState,
  agentStateBadgeStyles,
  agentStateLabels,
} from '@/lib/eventStyles';
import { PlanningEvent } from './PlanningEvent';
import { FileChangeEvent } from './FileChangeEvent';
import { ShellCommandEvent } from './ShellCommandEvent';
import { VerificationEvent } from './VerificationEvent';
import { BlockerEvent } from './BlockerEvent';
import type {
  ExecutionEvent,
  ProgressEvent,
  OutputEvent,
  BlockerEvent as BlockerEventType,
  CompletionEvent,
  ErrorEvent,
} from '@/hooks/useTaskStream';

interface EventItemProps {
  event: ExecutionEvent;
  workspacePath: string;
  onBlockerAnswered?: () => void;
}

/** Format ISO timestamp to HH:mm:ss for display. */
function formatTime(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  } catch {
    return '';
  }
}

/**
 * Determine which phase a ProgressEvent belongs to for rendering delegation.
 * File-related messages delegate to FileChangeEvent,
 * verification phases to VerificationEvent, etc.
 */
function isFileChangeEvent(event: ProgressEvent): boolean {
  return /^(creating|editing|deleting) file:/i.test(event.message ?? '');
}

/**
 * Base event item component.
 *
 * Renders a timestamp and event-type badge, then delegates
 * to the appropriate specialized component for the event body.
 */
export function EventItem({ event, workspacePath, onBlockerAnswered }: EventItemProps) {
  // Skip heartbeat events in the display
  if (event.event_type === 'heartbeat') return null;

  const agentState = deriveAgentState(event);
  const badgeClasses = agentStateBadgeStyles[agentState];
  const label = agentStateLabels[agentState];

  return (
    <div className="flex gap-3 py-1.5">
      {/* Timestamp */}
      <span className="shrink-0 pt-0.5 font-mono text-[11px] text-muted-foreground">
        {formatTime(event.timestamp)}
      </span>

      {/* Badge */}
      <span
        className={cn(
          'shrink-0 rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase leading-none',
          badgeClasses
        )}
      >
        {label}
      </span>

      {/* Event body — delegates to specialized component */}
      <div className="min-w-0 flex-1">
        {renderEventBody(event, workspacePath, onBlockerAnswered)}
      </div>
    </div>
  );
}

function renderEventBody(
  event: ExecutionEvent,
  workspacePath: string,
  onBlockerAnswered?: () => void
) {
  switch (event.event_type) {
    case 'progress': {
      const pe = event as ProgressEvent;
      if (pe.phase === 'planning') {
        return <PlanningEvent event={pe} />;
      }
      if (pe.phase === 'verification' || pe.phase === 'self_correction') {
        return <VerificationEvent event={pe} />;
      }
      if (isFileChangeEvent(pe)) {
        return <FileChangeEvent event={pe} />;
      }
      // Generic execution step
      return (
        <p className="text-sm">
          {pe.total_steps > 0 && (
            <span className="mr-1.5 text-xs text-muted-foreground">
              Step {pe.step}/{pe.total_steps}
            </span>
          )}
          {pe.message}
        </p>
      );
    }

    case 'output':
      return <ShellCommandEvent event={event as OutputEvent} />;

    case 'blocker':
      return (
        <BlockerEvent
          event={event as BlockerEventType}
          workspacePath={workspacePath}
          onAnswered={onBlockerAnswered}
        />
      );

    case 'completion': {
      const ce = event as CompletionEvent;
      const isSuccess = ce.status === 'completed';
      return (
        <div className="text-sm">
          <p className={isSuccess ? 'text-green-700 dark:text-green-400' : 'text-red-700 dark:text-red-400'}>
            {isSuccess ? 'Task completed successfully' : `Task ${ce.status}`}
            {ce.duration_seconds > 0 && (
              <span className="ml-1.5 text-xs text-muted-foreground">
                ({Math.round(ce.duration_seconds)}s)
              </span>
            )}
          </p>
          {ce.files_modified && ce.files_modified.length > 0 && (
            <p className="mt-0.5 text-xs text-muted-foreground">
              {ce.files_modified.length} file{ce.files_modified.length !== 1 ? 's' : ''} modified
            </p>
          )}
        </div>
      );
    }

    case 'error': {
      const ee = event as ErrorEvent;
      return (
        <div className="text-sm">
          <p className="font-medium text-red-700 dark:text-red-400">{ee.error}</p>
          {ee.traceback && (
            <pre className="mt-1 max-h-32 overflow-auto rounded bg-red-50 p-2 font-mono text-[11px] text-red-800 dark:bg-red-950/30 dark:text-red-300">
              {ee.traceback}
            </pre>
          )}
        </div>
      );
    }

    default:
      return null;
  }
}
