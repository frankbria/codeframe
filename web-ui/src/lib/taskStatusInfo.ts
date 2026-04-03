import type { TaskStatus } from '@/types';

export interface StatusInfo {
  /** One-sentence explanation of what this status means. */
  meaning: string;
  /** How the task entered this state. */
  enteredWhen: string;
  /** What the user should do next. */
  nextSteps: string;
}

export const STATUS_INFO: Record<TaskStatus, StatusInfo> = {
  BACKLOG: {
    meaning: 'Task identified but not yet ready to work on.',
    enteredWhen: 'Created, or moved back from Ready.',
    nextSteps: 'Mark Ready when prerequisites are met to enable execution.',
  },
  READY: {
    meaning: 'Task is queued and ready for AI agent execution.',
    enteredWhen: 'Marked Ready manually or promoted from Backlog.',
    nextSteps: 'Click Execute to start the AI agent on this task.',
  },
  IN_PROGRESS: {
    meaning: 'AI agent is actively executing this task.',
    enteredWhen: 'Execution was started.',
    nextSteps: 'Watch execution output — or Stop to cancel.',
  },
  DONE: {
    meaning: 'Task completed — all verification gates passed.',
    enteredWhen: 'Agent finished with all quality gates passing.',
    nextSteps: 'Review changes and create a PR to merge.',
  },
  BLOCKED: {
    meaning: 'Agent needs human input before it can continue.',
    enteredWhen: 'Agent detected it cannot proceed without an answer.',
    nextSteps: 'Answer the blocker to resume execution.',
  },
  FAILED: {
    meaning: 'Execution failed due to a technical error.',
    enteredWhen: 'Agent exceeded retry limit or hit an unrecoverable error.',
    nextSteps: 'Check PROOF9 gates for details, then Reset to retry.',
  },
  MERGED: {
    meaning: 'Task changes have been merged. No further actions.',
    enteredWhen: 'PR was merged.',
    nextSteps: 'This task is complete.',
  },
};
