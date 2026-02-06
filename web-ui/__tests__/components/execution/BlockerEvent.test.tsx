import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BlockerEvent } from '@/components/execution/BlockerEvent';
import type { BlockerEvent as BlockerEventType } from '@/hooks/useTaskStream';

// ── Mock API ──────────────────────────────────────────────────────────

const mockAnswer = jest.fn();

jest.mock('@/lib/api', () => ({
  blockersApi: {
    answer: (...args: unknown[]) => mockAnswer(...args),
  },
}));

// ── Fixtures ──────────────────────────────────────────────────────────

function makeBlockerEvent(overrides: Partial<BlockerEventType> = {}): BlockerEventType {
  return {
    event_type: 'blocker',
    task_id: 'task-1',
    timestamp: '2026-02-06T10:00:00Z',
    blocker_id: 42,
    question: 'Which database should be used?',
    ...overrides,
  };
}

beforeEach(() => {
  jest.clearAllMocks();
  mockAnswer.mockResolvedValue({});
});

// ── Tests ─────────────────────────────────────────────────────────────

describe('BlockerEvent', () => {
  it('renders the blocker question and header', () => {
    render(
      <BlockerEvent
        event={makeBlockerEvent()}
        workspacePath="/test"
      />
    );

    expect(screen.getByText('Agent needs your help')).toBeInTheDocument();
    expect(screen.getByText('Which database should be used?')).toBeInTheDocument();
    expect(screen.getByText('Execution paused — waiting for response...')).toBeInTheDocument();
  });

  it('renders context when provided', () => {
    render(
      <BlockerEvent
        event={makeBlockerEvent({ context: 'The project needs a database for persistence.' })}
        workspacePath="/test"
      />
    );

    expect(screen.getByText('The project needs a database for persistence.')).toBeInTheDocument();
  });

  it('disables submit button when answer is empty', () => {
    render(
      <BlockerEvent
        event={makeBlockerEvent()}
        workspacePath="/test"
      />
    );

    const button = screen.getByRole('button', { name: /answer blocker/i });
    expect(button).toBeDisabled();
  });

  it('enables submit button when answer is typed', async () => {
    const user = userEvent.setup();

    render(
      <BlockerEvent
        event={makeBlockerEvent()}
        workspacePath="/test"
      />
    );

    const textarea = screen.getByPlaceholderText('Type your answer...');
    await user.type(textarea, 'PostgreSQL');

    const button = screen.getByRole('button', { name: /answer blocker/i });
    expect(button).toBeEnabled();
  });

  it('calls blockersApi.answer on submit and shows confirmation', async () => {
    const user = userEvent.setup();
    const onAnswered = jest.fn();

    render(
      <BlockerEvent
        event={makeBlockerEvent()}
        workspacePath="/test"
        onAnswered={onAnswered}
      />
    );

    const textarea = screen.getByPlaceholderText('Type your answer...');
    await user.type(textarea, 'PostgreSQL');
    await user.click(screen.getByRole('button', { name: /answer blocker/i }));

    await waitFor(() => {
      expect(mockAnswer).toHaveBeenCalledWith('/test', '42', 'PostgreSQL');
    });

    expect(screen.getByText('Blocker answered. Execution resuming...')).toBeInTheDocument();
    expect(onAnswered).toHaveBeenCalled();
  });

  it('shows error when API call fails', async () => {
    const user = userEvent.setup();
    mockAnswer.mockRejectedValue({ detail: 'Blocker not found' });

    render(
      <BlockerEvent
        event={makeBlockerEvent()}
        workspacePath="/test"
      />
    );

    const textarea = screen.getByPlaceholderText('Type your answer...');
    await user.type(textarea, 'Some answer');
    await user.click(screen.getByRole('button', { name: /answer blocker/i }));

    await waitFor(() => {
      expect(screen.getByText('Blocker not found')).toBeInTheDocument();
    });

    // Form should still be visible (not replaced with success)
    expect(screen.getByPlaceholderText('Type your answer...')).toBeInTheDocument();
  });

  it('trims whitespace from answer before submitting', async () => {
    const user = userEvent.setup();

    render(
      <BlockerEvent
        event={makeBlockerEvent()}
        workspacePath="/test"
      />
    );

    const textarea = screen.getByPlaceholderText('Type your answer...');
    await user.type(textarea, '  PostgreSQL  ');
    await user.click(screen.getByRole('button', { name: /answer blocker/i }));

    await waitFor(() => {
      expect(mockAnswer).toHaveBeenCalledWith('/test', '42', 'PostgreSQL');
    });
  });

  it('does not submit when answer is only whitespace', async () => {
    const user = userEvent.setup();

    render(
      <BlockerEvent
        event={makeBlockerEvent()}
        workspacePath="/test"
      />
    );

    const textarea = screen.getByPlaceholderText('Type your answer...');
    await user.type(textarea, '   ');

    const button = screen.getByRole('button', { name: /answer blocker/i });
    expect(button).toBeDisabled();
  });
});
