import { deriveAgentState, agentStateBadgeStyles, agentStateLabels, agentStateIcons, connectionDotStyles } from '@/lib/eventStyles';
import type {
  ProgressEvent,
  CompletionEvent,
  ErrorEvent,
  OutputEvent,
  HeartbeatEvent,
  BlockerEvent,
} from '@/hooks/useTaskStream';

// ── deriveAgentState ──────────────────────────────────────────────────

describe('deriveAgentState', () => {
  it('returns PLANNING for progress events with planning phase', () => {
    const event: ProgressEvent = {
      event_type: 'progress',
      task_id: 't1',
      timestamp: '',
      phase: 'planning',
      step: 1,
      total_steps: 3,
      message: '',
    };
    expect(deriveAgentState(event)).toBe('PLANNING');
  });

  it('returns EXECUTING for progress events with execution phase', () => {
    const event: ProgressEvent = {
      event_type: 'progress',
      task_id: 't1',
      timestamp: '',
      phase: 'execution',
      step: 1,
      total_steps: 3,
      message: '',
    };
    expect(deriveAgentState(event)).toBe('EXECUTING');
  });

  it('returns VERIFICATION for progress events with verification phase', () => {
    const event: ProgressEvent = {
      event_type: 'progress',
      task_id: 't1',
      timestamp: '',
      phase: 'verification',
      step: 1,
      total_steps: 2,
      message: '',
    };
    expect(deriveAgentState(event)).toBe('VERIFICATION');
  });

  it('returns SELF_CORRECTING for self_correction phase', () => {
    const event: ProgressEvent = {
      event_type: 'progress',
      task_id: 't1',
      timestamp: '',
      phase: 'self_correction',
      step: 1,
      total_steps: 3,
      message: '',
    };
    expect(deriveAgentState(event)).toBe('SELF_CORRECTING');
  });

  it('returns EXECUTING for unknown progress phases', () => {
    const event: ProgressEvent = {
      event_type: 'progress',
      task_id: 't1',
      timestamp: '',
      phase: 'unknown_phase',
      step: 1,
      total_steps: 3,
      message: '',
    };
    expect(deriveAgentState(event)).toBe('EXECUTING');
  });

  it('returns BLOCKED for blocker events', () => {
    const event: BlockerEvent = {
      event_type: 'blocker',
      task_id: 't1',
      timestamp: '',
      blocker_id: 1,
      question: 'test',
    };
    expect(deriveAgentState(event)).toBe('BLOCKED');
  });

  it('returns COMPLETED for successful completion events', () => {
    const event: CompletionEvent = {
      event_type: 'completion',
      task_id: 't1',
      timestamp: '',
      status: 'completed',
      duration_seconds: 10,
    };
    expect(deriveAgentState(event)).toBe('COMPLETED');
  });

  it('returns FAILED for failed completion events', () => {
    const event: CompletionEvent = {
      event_type: 'completion',
      task_id: 't1',
      timestamp: '',
      status: 'failed',
      duration_seconds: 5,
    };
    expect(deriveAgentState(event)).toBe('FAILED');
  });

  it('returns FAILED for error events', () => {
    const event: ErrorEvent = {
      event_type: 'error',
      task_id: 't1',
      timestamp: '',
      error: 'some error',
      error_type: 'RuntimeError',
    };
    expect(deriveAgentState(event)).toBe('FAILED');
  });

  it('returns EXECUTING for output events', () => {
    const event: OutputEvent = {
      event_type: 'output',
      task_id: 't1',
      timestamp: '',
      stream: 'stdout',
      line: 'hello',
    };
    expect(deriveAgentState(event)).toBe('EXECUTING');
  });

  it('returns EXECUTING for heartbeat events (default case)', () => {
    const event: HeartbeatEvent = {
      event_type: 'heartbeat',
      task_id: 't1',
      timestamp: '',
    };
    expect(deriveAgentState(event)).toBe('EXECUTING');
  });
});

// ── Style maps ────────────────────────────────────────────────────────

describe('style maps', () => {
  it('has badge styles for all UIAgentState values', () => {
    const states = [
      'CONNECTING', 'PLANNING', 'EXECUTING', 'VERIFICATION',
      'SELF_CORRECTING', 'BLOCKED', 'COMPLETED', 'FAILED', 'DISCONNECTED',
    ] as const;

    states.forEach((state) => {
      expect(agentStateBadgeStyles[state]).toBeDefined();
      expect(typeof agentStateBadgeStyles[state]).toBe('string');
    });
  });

  it('has labels for all UIAgentState values', () => {
    const states = [
      'CONNECTING', 'PLANNING', 'EXECUTING', 'VERIFICATION',
      'SELF_CORRECTING', 'BLOCKED', 'COMPLETED', 'FAILED', 'DISCONNECTED',
    ] as const;

    states.forEach((state) => {
      expect(agentStateLabels[state]).toBeDefined();
      expect(typeof agentStateLabels[state]).toBe('string');
    });
  });

  it('has icons for all UIAgentState values', () => {
    const states = [
      'CONNECTING', 'PLANNING', 'EXECUTING', 'VERIFICATION',
      'SELF_CORRECTING', 'BLOCKED', 'COMPLETED', 'FAILED', 'DISCONNECTED',
    ] as const;

    states.forEach((state) => {
      expect(agentStateIcons[state]).toBeDefined();
      expect(agentStateIcons[state]).toBeTruthy();
    });
  });

  it('has connection dot styles for all SSE statuses', () => {
    const statuses = ['idle', 'connecting', 'open', 'closed', 'error'];

    statuses.forEach((status) => {
      expect(connectionDotStyles[status]).toBeDefined();
      expect(typeof connectionDotStyles[status]).toBe('string');
    });
  });
});
