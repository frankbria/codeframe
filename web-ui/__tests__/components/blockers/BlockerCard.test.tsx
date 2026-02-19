import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BlockerCard } from '@/components/blockers/BlockerCard';
import { blockersApi } from '@/lib/api';
import type { Blocker } from '@/types';

// Mock the API
jest.mock('@/lib/api', () => ({
  blockersApi: {
    answer: jest.fn(),
  },
}));

const mockAnswer = blockersApi.answer as jest.MockedFunction<typeof blockersApi.answer>;

function makeBlocker(overrides: Partial<Blocker> = {}): Blocker {
  return {
    id: 'blocker-1',
    workspace_id: 'ws-1',
    task_id: 'task-42',
    question: 'Which database should we use?',
    answer: null,
    status: 'OPEN',
    created_at: new Date(Date.now() - 30 * 60 * 1000).toISOString(), // 30m ago
    answered_at: null,
    ...overrides,
  };
}

describe('BlockerCard', () => {
  const workspacePath = '/home/user/project';
  const onAnswered = jest.fn();

  beforeEach(() => {
    jest.clearAllMocks();
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it('renders the blocker question prominently', () => {
    render(
      <BlockerCard blocker={makeBlocker()} workspacePath={workspacePath} onAnswered={onAnswered} />
    );

    expect(screen.getByText('Which database should we use?')).toBeInTheDocument();
  });

  it('displays the task ID', () => {
    render(
      <BlockerCard blocker={makeBlocker()} workspacePath={workspacePath} onAnswered={onAnswered} />
    );

    expect(screen.getByText('Task task-42')).toBeInTheDocument();
  });

  it('shows OPEN badge', () => {
    render(
      <BlockerCard blocker={makeBlocker()} workspacePath={workspacePath} onAnswered={onAnswered} />
    );

    expect(screen.getByText('OPEN')).toBeInTheDocument();
  });

  it('shows relative timestamp', () => {
    render(
      <BlockerCard blocker={makeBlocker()} workspacePath={workspacePath} onAnswered={onAnswered} />
    );

    expect(screen.getByText('30m ago')).toBeInTheDocument();
  });

  it('shows the answer form for OPEN blockers', () => {
    render(
      <BlockerCard blocker={makeBlocker()} workspacePath={workspacePath} onAnswered={onAnswered} />
    );

    expect(screen.getByTestId('blocker-answer-form')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('Type your answer...')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /answer blocker/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /skip/i })).toBeInTheDocument();
  });

  it('disables submit button when answer is empty', () => {
    render(
      <BlockerCard blocker={makeBlocker()} workspacePath={workspacePath} onAnswered={onAnswered} />
    );

    expect(screen.getByRole('button', { name: /answer blocker/i })).toBeDisabled();
  });

  it('enables submit button when answer has text', async () => {
    jest.useRealTimers();
    const user = userEvent.setup();

    render(
      <BlockerCard blocker={makeBlocker()} workspacePath={workspacePath} onAnswered={onAnswered} />
    );

    const textarea = screen.getByPlaceholderText('Type your answer...');
    await user.type(textarea, 'Use PostgreSQL');

    expect(screen.getByRole('button', { name: /answer blocker/i })).toBeEnabled();
  });

  it('shows success state after successful submission', async () => {
    jest.useRealTimers();
    const user = userEvent.setup();
    mockAnswer.mockResolvedValueOnce(makeBlocker({ status: 'ANSWERED', answer: 'Use PostgreSQL' }));

    render(
      <BlockerCard blocker={makeBlocker()} workspacePath={workspacePath} onAnswered={onAnswered} />
    );

    const textarea = screen.getByPlaceholderText('Type your answer...');
    await user.type(textarea, 'Use PostgreSQL');
    await user.click(screen.getByRole('button', { name: /answer blocker/i }));

    await waitFor(() => {
      expect(screen.getByText(/blocker answered/i)).toBeInTheDocument();
    });
  });

  it('calls blockersApi.answer with correct arguments', async () => {
    jest.useRealTimers();
    const user = userEvent.setup();
    mockAnswer.mockResolvedValueOnce(makeBlocker({ status: 'ANSWERED', answer: 'Use PostgreSQL' }));

    render(
      <BlockerCard blocker={makeBlocker()} workspacePath={workspacePath} onAnswered={onAnswered} />
    );

    const textarea = screen.getByPlaceholderText('Type your answer...');
    await user.type(textarea, 'Use PostgreSQL');
    await user.click(screen.getByRole('button', { name: /answer blocker/i }));

    expect(mockAnswer).toHaveBeenCalledWith(workspacePath, 'blocker-1', 'Use PostgreSQL');
  });

  it('displays error when API call fails', async () => {
    jest.useRealTimers();
    const user = userEvent.setup();
    mockAnswer.mockRejectedValueOnce({ detail: 'Blocker already resolved' });

    render(
      <BlockerCard blocker={makeBlocker()} workspacePath={workspacePath} onAnswered={onAnswered} />
    );

    const textarea = screen.getByPlaceholderText('Type your answer...');
    await user.type(textarea, 'Some answer');
    await user.click(screen.getByRole('button', { name: /answer blocker/i }));

    await waitFor(() => {
      expect(screen.getByText('Blocker already resolved')).toBeInTheDocument();
    });
  });

  it('hides form when Skip is clicked and shows "Show answer form" button', async () => {
    jest.useRealTimers();
    const user = userEvent.setup();

    render(
      <BlockerCard blocker={makeBlocker()} workspacePath={workspacePath} onAnswered={onAnswered} />
    );

    await user.click(screen.getByRole('button', { name: /skip/i }));

    expect(screen.queryByTestId('blocker-answer-form')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /show answer form/i })).toBeInTheDocument();
  });

  it('re-expands form when "Show answer form" is clicked after Skip', async () => {
    jest.useRealTimers();
    const user = userEvent.setup();

    render(
      <BlockerCard blocker={makeBlocker()} workspacePath={workspacePath} onAnswered={onAnswered} />
    );

    await user.click(screen.getByRole('button', { name: /skip/i }));
    await user.click(screen.getByRole('button', { name: /show answer form/i }));

    expect(screen.getByTestId('blocker-answer-form')).toBeInTheDocument();
  });

  it('shows character count', async () => {
    jest.useRealTimers();
    const user = userEvent.setup();

    render(
      <BlockerCard blocker={makeBlocker()} workspacePath={workspacePath} onAnswered={onAnswered} />
    );

    expect(screen.getByText('0 characters')).toBeInTheDocument();

    const textarea = screen.getByPlaceholderText('Type your answer...');
    await user.type(textarea, 'Hello');

    expect(screen.getByText('5 characters')).toBeInTheDocument();
  });

  it('has correct data-testid attributes', () => {
    render(
      <BlockerCard blocker={makeBlocker()} workspacePath={workspacePath} onAnswered={onAnswered} />
    );

    expect(screen.getByTestId('blocker-card')).toBeInTheDocument();
    expect(screen.getByTestId('blocker-answer-form')).toBeInTheDocument();
  });

  it('has correct aria-label on textarea', () => {
    render(
      <BlockerCard blocker={makeBlocker()} workspacePath={workspacePath} onAnswered={onAnswered} />
    );

    expect(screen.getByLabelText('Your answer to the blocker question')).toBeInTheDocument();
  });
});
