/**
 * Centralized styling constants and helpers for execution event types.
 *
 * Used by EventItem, ExecutionHeader, and other execution monitor components
 * to ensure consistent badge colors and icons across the UI.
 */
import type { ComponentType } from 'react';
import type { UIAgentState } from '@/types';
import type {
  ExecutionEvent,
  ProgressEvent,
  CompletionEvent,
} from '@/hooks/useTaskStream';
import {
  Idea01Icon,
  PlayIcon,
  CheckmarkCircle01Icon,
  ArrowTurnBackwardIcon,
  Alert02Icon,
  Cancel01Icon,
  CommandLineIcon,
  AlertDiamondIcon,
  Loading03Icon,
  WifiDisconnected01Icon,
  FileEditIcon,
} from '@hugeicons/react';

// ── Agent state derivation ─────────────────────────────────────────────

/**
 * Derive the UI agent state from a raw execution event.
 *
 * Maps backend event_type + phase/status to a display-friendly state
 * that drives badge color and icon selection.
 */
export function deriveAgentState(event: ExecutionEvent): UIAgentState {
  switch (event.event_type) {
    case 'progress': {
      const { phase } = event as ProgressEvent;
      switch (phase) {
        case 'planning':
          return 'PLANNING';
        case 'execution':
          return 'EXECUTING';
        case 'verification':
          return 'VERIFICATION';
        case 'self_correction':
          return 'SELF_CORRECTING';
        default:
          return 'EXECUTING';
      }
    }
    case 'blocker':
      return 'BLOCKED';
    case 'completion': {
      const { status } = event as CompletionEvent;
      if (status === 'completed') return 'COMPLETED';
      if (status === 'blocked') return 'BLOCKED';
      return 'FAILED';
    }
    case 'error':
      return 'FAILED';
    case 'output':
      return 'EXECUTING';
    default:
      return 'EXECUTING';
  }
}

// ── Badge styles ───────────────────────────────────────────────────────

/** Tailwind classes for the agent state badge background + text. */
export const agentStateBadgeStyles: Record<UIAgentState, string> = {
  CONNECTING: 'bg-gray-100 text-gray-800',
  PLANNING: 'bg-blue-100 text-blue-800',
  EXECUTING: 'bg-green-100 text-green-800',
  VERIFICATION: 'bg-orange-100 text-orange-800',
  SELF_CORRECTING: 'bg-yellow-100 text-yellow-800',
  BLOCKED: 'bg-red-100 text-red-800',
  COMPLETED: 'bg-green-100 text-green-800',
  FAILED: 'bg-red-100 text-red-800',
  DISCONNECTED: 'bg-gray-100 text-gray-800',
};

/** Human-readable labels for each agent state. */
export const agentStateLabels: Record<UIAgentState, string> = {
  CONNECTING: 'Connecting',
  PLANNING: 'Planning',
  EXECUTING: 'Executing',
  VERIFICATION: 'Verifying',
  SELF_CORRECTING: 'Self-Correcting',
  BLOCKED: 'Blocked',
  COMPLETED: 'Completed',
  FAILED: 'Failed',
  DISCONNECTED: 'Disconnected',
};

// ── Icon mapping ───────────────────────────────────────────────────────

// Hugeicons icon props type (size + className are the commonly used ones)
type IconProps = { size?: number; className?: string };

/** Icon component for each agent state. */
export const agentStateIcons: Record<UIAgentState, ComponentType<IconProps>> = {
  CONNECTING: Loading03Icon,
  PLANNING: Idea01Icon,
  EXECUTING: PlayIcon,
  VERIFICATION: CheckmarkCircle01Icon,
  SELF_CORRECTING: ArrowTurnBackwardIcon,
  BLOCKED: Alert02Icon,
  COMPLETED: CheckmarkCircle01Icon,
  FAILED: Cancel01Icon,
  DISCONNECTED: WifiDisconnected01Icon,
};

/**
 * Icon for specific event sub-types used inside event detail renderers
 * (e.g. shell output uses a terminal icon, errors use a diamond alert).
 */
export const eventDetailIcons = {
  shellCommand: CommandLineIcon,
  errorDetail: AlertDiamondIcon,
  fileChange: FileEditIcon,
} as const;

// ── Connection status dot ──────────────────────────────────────────────

/** CSS classes for the SSE connection status indicator dot. */
export const connectionDotStyles: Record<string, string> = {
  idle: 'bg-gray-400',
  connecting: 'bg-yellow-400 animate-pulse',
  open: 'bg-green-500',
  closed: 'bg-gray-400',
  error: 'bg-red-500',
};
