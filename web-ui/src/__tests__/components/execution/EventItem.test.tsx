import { render, screen } from '@testing-library/react';
import { EventItem } from '@/components/execution/EventItem';
import type {
  ProgressEvent,
  OutputEvent,
  CompletionEvent,
  ErrorEvent,
  HeartbeatEvent,
  BlockerEvent as BlockerEventType,
} from '@/hooks/useTaskStream';

// ── Mock child components ─────────────────────────────────────────────

jest.mock('@/components/execution/PlanningEvent', () => ({
  PlanningEvent: ({ event }: { event: ProgressEvent }) => (
    <div data-testid="planning-event">{event.message}</div>
  ),
}));

jest.mock('@/components/execution/FileChangeEvent', () => ({
  FileChangeEvent: ({ event }: { event: ProgressEvent }) => (
    <div data-testid="file-change-event">{event.message}</div>
  ),
}));

jest.mock('@/components/execution/ShellCommandEvent', () => ({
  ShellCommandEvent: ({ event }: { event: OutputEvent }) => (
    <div data-testid="shell-command-event">{event.line}</div>
  ),
}));

jest.mock('@/components/execution/VerificationEvent', () => ({
  VerificationEvent: ({ event }: { event: ProgressEvent }) => (
    <div data-testid="verification-event">{event.message}</div>
  ),
}));

jest.mock('@/components/execution/BlockerEvent', () => ({
  BlockerEvent: ({ event }: { event: BlockerEventType }) => (
    <div data-testid="blocker-event">{event.question}</div>
  ),
}));

// ── Tests ─────────────────────────────────────────────────────────────

describe('EventItem', () => {
  it('renders nothing for heartbeat events', () => {
    const heartbeat: HeartbeatEvent = {
      event_type: 'heartbeat',
      task_id: 'task-1',
      timestamp: '2026-02-06T10:00:00Z',
    };

    const { container } = render(
      <EventItem event={heartbeat} workspacePath="/test" />
    );
    expect(container.innerHTML).toBe('');
  });

  it('renders timestamp and Planning badge for planning progress', () => {
    const event: ProgressEvent = {
      event_type: 'progress',
      task_id: 'task-1',
      timestamp: '2026-02-06T14:30:15Z',
      phase: 'planning',
      step: 1,
      total_steps: 3,
      message: 'Creating plan...',
    };

    render(<EventItem event={event} workspacePath="/test" />);

    expect(screen.getByText('Planning')).toBeInTheDocument();
    expect(screen.getByTestId('planning-event')).toBeInTheDocument();
    expect(screen.getByText('Creating plan...')).toBeInTheDocument();
  });

  it('delegates file change progress events to FileChangeEvent', () => {
    const event: ProgressEvent = {
      event_type: 'progress',
      task_id: 'task-1',
      timestamp: '2026-02-06T10:00:00Z',
      phase: 'execution',
      step: 2,
      total_steps: 5,
      message: 'Creating file: src/main.py',
    };

    render(<EventItem event={event} workspacePath="/test" />);

    expect(screen.getByTestId('file-change-event')).toBeInTheDocument();
  });

  it('delegates verification phase to VerificationEvent', () => {
    const event: ProgressEvent = {
      event_type: 'progress',
      task_id: 'task-1',
      timestamp: '2026-02-06T10:00:00Z',
      phase: 'verification',
      step: 1,
      total_steps: 2,
      message: 'Running ruff',
    };

    render(<EventItem event={event} workspacePath="/test" />);

    expect(screen.getByTestId('verification-event')).toBeInTheDocument();
  });

  it('delegates self_correction phase to VerificationEvent', () => {
    const event: ProgressEvent = {
      event_type: 'progress',
      task_id: 'task-1',
      timestamp: '2026-02-06T10:00:00Z',
      phase: 'self_correction',
      step: 1,
      total_steps: 3,
      message: 'Fixing lint errors',
    };

    render(<EventItem event={event} workspacePath="/test" />);

    expect(screen.getByTestId('verification-event')).toBeInTheDocument();
  });

  it('renders generic execution step for non-special progress events', () => {
    const event: ProgressEvent = {
      event_type: 'progress',
      task_id: 'task-1',
      timestamp: '2026-02-06T10:00:00Z',
      phase: 'execution',
      step: 3,
      total_steps: 5,
      message: 'Installing dependencies',
    };

    render(<EventItem event={event} workspacePath="/test" />);

    expect(screen.getByText('Executing')).toBeInTheDocument();
    expect(screen.getByText('Installing dependencies')).toBeInTheDocument();
    expect(screen.getByText('Step 3/5')).toBeInTheDocument();
  });

  it('delegates output events to ShellCommandEvent', () => {
    const event: OutputEvent = {
      event_type: 'output',
      task_id: 'task-1',
      timestamp: '2026-02-06T10:00:00Z',
      stream: 'stdout',
      line: 'test passed',
    };

    render(<EventItem event={event} workspacePath="/test" />);

    expect(screen.getByTestId('shell-command-event')).toBeInTheDocument();
    expect(screen.getByText('test passed')).toBeInTheDocument();
  });

  it('delegates blocker events to BlockerEvent', () => {
    const event: BlockerEventType = {
      event_type: 'blocker',
      task_id: 'task-1',
      timestamp: '2026-02-06T10:00:00Z',
      blocker_id: 42,
      question: 'Which database to use?',
    };

    render(<EventItem event={event} workspacePath="/test" />);

    expect(screen.getByTestId('blocker-event')).toBeInTheDocument();
    expect(screen.getByText('Which database to use?')).toBeInTheDocument();
  });

  it('renders completion event with success styling', () => {
    const event: CompletionEvent = {
      event_type: 'completion',
      task_id: 'task-1',
      timestamp: '2026-02-06T10:00:00Z',
      status: 'completed',
      duration_seconds: 45,
      files_modified: ['a.py', 'b.py'],
    };

    render(<EventItem event={event} workspacePath="/test" />);

    expect(screen.getByText('Task completed successfully')).toBeInTheDocument();
    expect(screen.getByText('(45s)')).toBeInTheDocument();
    expect(screen.getByText('2 files modified')).toBeInTheDocument();
  });

  it('renders completion event with failed status', () => {
    const event: CompletionEvent = {
      event_type: 'completion',
      task_id: 'task-1',
      timestamp: '2026-02-06T10:00:00Z',
      status: 'failed',
      duration_seconds: 10,
    };

    render(<EventItem event={event} workspacePath="/test" />);

    expect(screen.getByText('Task failed')).toBeInTheDocument();
  });

  it('renders error event with error message and traceback', () => {
    const event: ErrorEvent = {
      event_type: 'error',
      task_id: 'task-1',
      timestamp: '2026-02-06T10:00:00Z',
      error: 'Module not found',
      error_type: 'ImportError',
      traceback: 'File "main.py", line 1\nImportError: No module named foo',
    };

    render(<EventItem event={event} workspacePath="/test" />);

    expect(screen.getByText('Module not found')).toBeInTheDocument();
    expect(
      screen.getByText(/ImportError: No module named foo/)
    ).toBeInTheDocument();
  });

  it('renders error event without traceback', () => {
    const event: ErrorEvent = {
      event_type: 'error',
      task_id: 'task-1',
      timestamp: '2026-02-06T10:00:00Z',
      error: 'Timeout',
      error_type: 'TimeoutError',
    };

    render(<EventItem event={event} workspacePath="/test" />);

    expect(screen.getByText('Timeout')).toBeInTheDocument();
  });

  it('shows 1 file modified (singular) for single file', () => {
    const event: CompletionEvent = {
      event_type: 'completion',
      task_id: 'task-1',
      timestamp: '2026-02-06T10:00:00Z',
      status: 'completed',
      duration_seconds: 5,
      files_modified: ['single.py'],
    };

    render(<EventItem event={event} workspacePath="/test" />);

    expect(screen.getByText('1 file modified')).toBeInTheDocument();
  });
});
