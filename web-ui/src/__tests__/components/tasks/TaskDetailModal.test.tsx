import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { TaskDetailModal } from '@/components/tasks/TaskDetailModal';
import { STATUS_INFO } from '@/lib/taskStatusInfo';
import type { Task } from '@/types';

// Radix UI tooltips use portals and pointer events that don't work in jsdom.
jest.mock('@/components/ui/tooltip', () => ({
  TooltipProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  Tooltip: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  TooltipTrigger: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  TooltipContent: ({ children }: { children: React.ReactNode }) => (
    <div role="tooltip">{children}</div>
  ),
}));

// ── Mocks ────────────────────────────────────────────────────────────────

jest.mock('swr', () => ({
  __esModule: true,
  default: jest.fn(() => ({ data: { tasks: [] }, isLoading: false, error: null })),
}));

jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: jest.fn() }),
}));

jest.mock('next/link', () => {
  const MockLink = ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  );
  MockLink.displayName = 'MockLink';
  return MockLink;
});

jest.mock('@/lib/api', () => ({
  tasksApi: {
    getOne: jest.fn(),
    getAll: jest.fn(),
    updateStatus: jest.fn(),
    updateGitHubSettings: jest.fn(),
  },
}));

jest.mock('@/hooks/useRequirementsLookup', () => ({
  useRequirementsLookup: () => ({ requirementsMap: new Map(), isLoading: false }),
}));

import { tasksApi } from '@/lib/api';

const makeTask = (overrides: Partial<Task> = {}): Task => ({
  id: 'task-1',
  title: 'Test Task',
  description: 'A description',
  status: 'BACKLOG',
  priority: 0,
  depends_on: [],
  ...overrides,
});

const defaultProps = {
  taskId: 'task-1',
  workspacePath: '/ws',
  open: true,
  onClose: jest.fn(),
  onExecute: jest.fn(),
  onStatusChange: jest.fn(),
};

function renderModal(taskOverrides: Partial<Task> = {}) {
  const task = makeTask(taskOverrides);
  (tasksApi.getOne as jest.Mock).mockResolvedValue(task);
  return render(<TaskDetailModal {...defaultProps} />);
}

describe('TaskDetailModal status badge tooltip', () => {
  it('renders tooltip with BACKLOG meaning', async () => {
    renderModal({ status: 'BACKLOG' });
    await waitFor(() => expect(screen.getByText('Test Task')).toBeInTheDocument());
    expect(screen.getByRole('tooltip')).toHaveTextContent(STATUS_INFO.BACKLOG.meaning);
  });

  it('renders tooltip with DONE meaning', async () => {
    renderModal({ status: 'DONE' });
    await waitFor(() => expect(screen.getByText('Test Task')).toBeInTheDocument());
    expect(screen.getByRole('tooltip')).toHaveTextContent(STATUS_INFO.DONE.meaning);
  });

  it('renders tooltip with FAILED meaning', async () => {
    renderModal({ status: 'FAILED' });
    await waitFor(() => expect(screen.getByText('Test Task')).toBeInTheDocument());
    expect(screen.getByRole('tooltip')).toHaveTextContent(STATUS_INFO.FAILED.meaning);
  });
});

describe('TaskDetailModal valid transition guidance', () => {
  it('shows "Mark Ready" button for BACKLOG status', async () => {
    renderModal({ status: 'BACKLOG' });
    await waitFor(() => expect(screen.getByText('Test Task')).toBeInTheDocument());
    expect(screen.getByRole('button', { name: /mark ready/i })).toBeInTheDocument();
  });

  it('shows "Execute" button for READY status', async () => {
    renderModal({ status: 'READY' });
    await waitFor(() => expect(screen.getByText('Test Task')).toBeInTheDocument());
    expect(screen.getByRole('button', { name: /execute/i })).toBeInTheDocument();
  });

  it('shows next-step guidance for DONE status (no action button but guidance visible)', async () => {
    renderModal({ status: 'DONE' });
    await waitFor(() => expect(screen.getByText('Test Task')).toBeInTheDocument());
    expect(screen.getByTestId('status-next-step')).toBeInTheDocument();
    expect(screen.getByTestId('status-next-step')).toHaveTextContent(STATUS_INFO.DONE.nextSteps);
  });

  it('shows next-step guidance for BLOCKED status', async () => {
    renderModal({ status: 'BLOCKED' });
    await waitFor(() => expect(screen.getByText('Test Task')).toBeInTheDocument());
    expect(screen.getByTestId('status-next-step')).toBeInTheDocument();
    expect(screen.getByTestId('status-next-step')).toHaveTextContent(STATUS_INFO.BLOCKED.nextSteps);
  });

  it('shows next-step guidance for MERGED status', async () => {
    renderModal({ status: 'MERGED' });
    await waitFor(() => expect(screen.getByText('Test Task')).toBeInTheDocument());
    expect(screen.getByTestId('status-next-step')).toBeInTheDocument();
    expect(screen.getByTestId('status-next-step')).toHaveTextContent(STATUS_INFO.MERGED.nextSteps);
  });

  it('shows next-step guidance for FAILED status via the alert panel', async () => {
    renderModal({ status: 'FAILED' });
    await waitFor(() => expect(screen.getByText('Test Task')).toBeInTheDocument());
    expect(screen.getByTestId('status-next-step')).toBeInTheDocument();
    expect(screen.getByTestId('status-next-step')).toHaveTextContent(STATUS_INFO.FAILED.nextSteps);
  });

  it('does not show next-step guidance for BACKLOG (has action button)', async () => {
    renderModal({ status: 'BACKLOG' });
    await waitFor(() => expect(screen.getByText('Test Task')).toBeInTheDocument());
    expect(screen.queryByTestId('status-next-step')).not.toBeInTheDocument();
  });

  it('does not show next-step guidance for READY (has action button)', async () => {
    renderModal({ status: 'READY' });
    await waitFor(() => expect(screen.getByText('Test Task')).toBeInTheDocument());
    expect(screen.queryByTestId('status-next-step')).not.toBeInTheDocument();
  });
});

describe('TaskDetailModal last changed timestamp', () => {
  it('shows last changed date when updated_at is present', async () => {
    renderModal({ status: 'DONE', updated_at: '2026-01-15T10:30:00Z' });
    await waitFor(() => expect(screen.getByText('Test Task')).toBeInTheDocument());
    expect(screen.getByText(/last changed/i)).toBeInTheDocument();
  });

  it('does not show last changed when updated_at is absent', async () => {
    renderModal({ status: 'BACKLOG' });
    await waitFor(() => expect(screen.getByText('Test Task')).toBeInTheDocument());
    expect(screen.queryByText(/last changed/i)).not.toBeInTheDocument();
  });
});

describe('TaskDetailModal — GitHub traceability (#565)', () => {
  beforeEach(() => jest.clearAllMocks());

  it('shows the GitHub badge for imported tasks', async () => {
    renderModal({
      github_issue_number: 42,
      external_url: 'https://github.com/acme/app/issues/42',
    });
    await waitFor(() => expect(screen.getByText('Test Task')).toBeInTheDocument());
    const link = screen.getByRole('link', { name: /imported from github issue #42/i });
    expect(link).toHaveAttribute('href', 'https://github.com/acme/app/issues/42');
  });

  it('does not show the badge for non-imported tasks', async () => {
    renderModal({ github_issue_number: undefined, external_url: undefined });
    await waitFor(() => expect(screen.getByText('Test Task')).toBeInTheDocument());
    expect(
      screen.queryByRole('checkbox', {
        name: /close github issue when task is marked done/i,
      })
    ).not.toBeInTheDocument();
  });

  it('persists the auto-close toggle via the API', async () => {
    (tasksApi.updateGitHubSettings as jest.Mock).mockResolvedValue({});
    renderModal({
      github_issue_number: 42,
      external_url: 'https://github.com/acme/app/issues/42',
      auto_close_github_issue: false,
    });
    await waitFor(() => expect(screen.getByText('Test Task')).toBeInTheDocument());

    const checkbox = screen.getByRole('checkbox', {
      name: /close github issue when task is marked done/i,
    });
    expect(checkbox).not.toBeChecked();
    checkbox.click();

    await waitFor(() =>
      expect(tasksApi.updateGitHubSettings).toHaveBeenCalledWith('/ws', 'task-1', true)
    );
  });
});
