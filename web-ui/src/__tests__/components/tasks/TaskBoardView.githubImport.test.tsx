import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import useSWR from 'swr';

import { TaskBoardView } from '@/components/tasks/TaskBoardView';
import type { GitHubIntegrationStatus } from '@/types';

// Focused test: the "Import from GitHub" button is gated on connection status
// and opens the issue-import modal (issue #564). Heavy children are stubbed so
// the test isolates the button/modal wiring.

jest.mock('swr');
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
jest.mock('@/hooks/useRequirementsLookup', () => ({
  useRequirementsLookup: () => ({ requirementsMap: new Map(), isLoading: false }),
}));
jest.mock('@/lib/api', () => ({
  tasksApi: { getAll: jest.fn() },
  prdApi: { getAll: jest.fn() },
  costsApi: { getTopTasks: jest.fn() },
  integrationsApi: { getStatus: jest.fn(), getIssues: jest.fn() },
}));

// Stub heavy children; surface only what the test asserts on.
jest.mock('@/components/tasks/TaskBoardContent', () => ({
  TaskBoardContent: () => <div data-testid="board-content" />,
}));
jest.mock('@/components/tasks/TaskDetailModal', () => ({
  TaskDetailModal: () => null,
}));
jest.mock('@/components/tasks/TaskFilters', () => ({
  TaskFilters: () => <div data-testid="filters" />,
}));
jest.mock('@/components/tasks/BatchActionsBar', () => ({
  BatchActionsBar: () => <div data-testid="batch-bar" />,
}));
jest.mock('@/components/tasks/BulkActionConfirmDialog', () => ({
  BulkActionConfirmDialog: () => null,
}));
jest.mock('@/components/tasks/GitHubIssueImportModal', () => ({
  GitHubIssueImportModal: ({ open }: { open: boolean }) =>
    open ? <div data-testid="import-modal">import modal open</div> : null,
}));

const mockUseSWR = useSWR as jest.MockedFunction<typeof useSWR>;

function setupSWR(ghStatus: GitHubIntegrationStatus | undefined) {
  mockUseSWR.mockImplementation((key) => {
    const k = String(key);
    if (k.includes('/integrations/github/status')) {
      return { data: ghStatus, error: undefined, isLoading: false, mutate: jest.fn() } as never;
    }
    if (k.includes('/api/v2/tasks')) {
      return {
        data: { tasks: [], total: 0 },
        error: undefined,
        isLoading: false,
        mutate: jest.fn(),
      } as never;
    }
    // costs + prd
    return { data: undefined, error: undefined, isLoading: false, mutate: jest.fn() } as never;
  });
}

const CONNECTED: GitHubIntegrationStatus = {
  connected: true,
  repo: 'acme/app',
  owner_login: 'acme',
  owner_avatar_url: '',
};
const DISCONNECTED: GitHubIntegrationStatus = {
  connected: false,
  repo: null,
  owner_login: null,
  owner_avatar_url: null,
};

describe('TaskBoardView — GitHub import button', () => {
  beforeEach(() => jest.clearAllMocks());

  it('hides the button when GitHub is not connected', () => {
    setupSWR(DISCONNECTED);
    render(<TaskBoardView workspacePath="/ws" />);
    expect(
      screen.queryByRole('button', { name: /import from github/i })
    ).not.toBeInTheDocument();
  });

  it('shows the button and opens the modal when connected', () => {
    setupSWR(CONNECTED);
    render(<TaskBoardView workspacePath="/ws" />);

    const btn = screen.getByRole('button', { name: /import from github/i });
    expect(btn).toBeInTheDocument();
    expect(screen.queryByTestId('import-modal')).not.toBeInTheDocument();

    fireEvent.click(btn);
    expect(screen.getByTestId('import-modal')).toBeInTheDocument();
  });
});
