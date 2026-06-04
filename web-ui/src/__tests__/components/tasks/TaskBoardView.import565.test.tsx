import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import useSWR from 'swr';

import { TaskBoardView } from '@/components/tasks/TaskBoardView';
import { integrationsApi } from '@/lib/api';
import type { GitHubIntegrationStatus, GitHubIssue } from '@/types';

// Focused test for the #565 import execution wiring: clicking the stubbed
// modal's import trigger calls integrationsApi.importIssues and surfaces a
// summary banner on success.

jest.mock('swr');
jest.mock('next/navigation', () => ({ useRouter: () => ({ push: jest.fn() }) }));
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
  integrationsApi: { getStatus: jest.fn(), getIssues: jest.fn(), importIssues: jest.fn() },
}));

jest.mock('@/components/tasks/TaskBoardContent', () => ({
  TaskBoardContent: () => <div data-testid="board-content" />,
}));
jest.mock('@/components/tasks/TaskDetailModal', () => ({ TaskDetailModal: () => null }));
jest.mock('@/components/tasks/TaskFilters', () => ({ TaskFilters: () => <div /> }));
jest.mock('@/components/tasks/BatchActionsBar', () => ({ BatchActionsBar: () => <div /> }));
jest.mock('@/components/tasks/BulkActionConfirmDialog', () => ({
  BulkActionConfirmDialog: () => null,
}));

// Stub the import modal: expose onImport via a trigger button and reflect the
// `importing` flag so the test can assert progress state.
jest.mock('@/components/tasks/GitHubIssueImportModal', () => ({
  GitHubIssueImportModal: ({
    open,
    importing,
    onImport,
  }: {
    open: boolean;
    importing: boolean;
    onImport: (issues: GitHubIssue[]) => void;
  }) =>
    open ? (
      <div data-testid="import-modal">
        {importing && <span>importing-flag</span>}
        <button
          onClick={() =>
            onImport([
              {
                number: 12,
                title: 'Fix login',
                labels: [],
                assignee: null,
                created_at: '',
                html_url: 'https://github.com/acme/app/issues/12',
              },
            ])
          }
        >
          trigger-import
        </button>
      </div>
    ) : null,
}));

const mockUseSWR = useSWR as jest.MockedFunction<typeof useSWR>;
const mockMutate = jest.fn();

const CONNECTED: GitHubIntegrationStatus = {
  connected: true,
  repo: 'acme/app',
  owner_login: 'acme',
  owner_avatar_url: '',
};

function setupSWR() {
  mockUseSWR.mockImplementation((key) => {
    const k = String(key);
    if (k.includes('/integrations/github/status')) {
      return { data: CONNECTED, error: undefined, isLoading: false, mutate: jest.fn() } as never;
    }
    if (k.includes('/api/v2/tasks')) {
      return {
        data: { tasks: [], total: 0 },
        error: undefined,
        isLoading: false,
        mutate: mockMutate,
      } as never;
    }
    return { data: undefined, error: undefined, isLoading: false, mutate: jest.fn() } as never;
  });
}

describe('TaskBoardView — GitHub import execution (#565)', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    setupSWR();
  });

  it('imports selected issues and shows a summary banner', async () => {
    (integrationsApi.importIssues as jest.Mock).mockResolvedValue({
      created: [{ task_id: 't1', issue_number: 12, title: 'Fix login' }],
      skipped: [],
      total_created: 1,
    });

    render(<TaskBoardView workspacePath="/ws" />);
    fireEvent.click(screen.getByRole('button', { name: /import from github/i }));
    fireEvent.click(screen.getByText('trigger-import'));

    await waitFor(() =>
      expect(integrationsApi.importIssues).toHaveBeenCalledWith('/ws', [12])
    );
    await waitFor(() =>
      expect(screen.getByRole('status')).toHaveTextContent(/1 task created/i)
    );
    expect(mockMutate).toHaveBeenCalled();
  });

  it('reports skipped duplicates in the summary', async () => {
    (integrationsApi.importIssues as jest.Mock).mockResolvedValue({
      created: [],
      skipped: [12],
      total_created: 0,
    });

    render(<TaskBoardView workspacePath="/ws" />);
    fireEvent.click(screen.getByRole('button', { name: /import from github/i }));
    fireEvent.click(screen.getByText('trigger-import'));

    await waitFor(() =>
      expect(screen.getByRole('status')).toHaveTextContent(
        /0 tasks created · 1 skipped \(already imported\)/i
      )
    );
  });

  it('surfaces an error banner when the import fails', async () => {
    (integrationsApi.importIssues as jest.Mock).mockRejectedValue({
      detail: 'No GitHub repository is connected.',
    });

    render(<TaskBoardView workspacePath="/ws" />);
    fireEvent.click(screen.getByRole('button', { name: /import from github/i }));
    fireEvent.click(screen.getByText('trigger-import'));

    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(
        /No GitHub repository is connected/i
      )
    );
  });
});
