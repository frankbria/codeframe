import React from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import useSWR from 'swr';

import { GitHubIssueImportModal } from '@/components/tasks/GitHubIssueImportModal';
import { integrationsApi } from '@/lib/api';
import type { GitHubIssue, GitHubIssuesResponse } from '@/types';

jest.mock('swr');
jest.mock('@/lib/api', () => ({
  integrationsApi: {
    getIssues: jest.fn(),
  },
}));

const mockUseSWR = useSWR as jest.MockedFunction<typeof useSWR>;

function issue(number: number, title: string, extra: Partial<GitHubIssue> = {}): GitHubIssue {
  return {
    number,
    title,
    labels: extra.labels ?? [],
    assignee: extra.assignee ?? null,
    created_at: extra.created_at ?? '2026-05-01T12:00:00Z',
    html_url: `https://github.com/acme/app/issues/${number}`,
  };
}

/**
 * Drive useSWR's return value off the key the component passes. The key is
 * `['github-issues', workspacePath, page, search, label]`, so this lets tests
 * return different pages for different `page` values — needed to verify that
 * selection persists across page changes.
 */
function mockSWRByPage(pages: Record<number, GitHubIssue[]>, total: number) {
  mockUseSWR.mockImplementation((key) => {
    if (!key) {
      return { data: undefined, error: undefined, isLoading: false } as never;
    }
    const page = (key as unknown[])[2] as number;
    const resp: GitHubIssuesResponse = {
      issues: pages[page] ?? [],
      total,
      page,
      per_page: 25,
    };
    return { data: resp, error: undefined, isLoading: false } as never;
  });
}

const baseProps = {
  open: true,
  workspacePath: '/ws',
  repo: 'acme/app',
  onClose: jest.fn(),
  onImport: jest.fn(),
};

describe('GitHubIssueImportModal', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders issue rows with title, labels, assignee', () => {
    mockSWRByPage(
      { 1: [issue(42, 'Fix login bug', { labels: ['bug'], assignee: 'alice' })] },
      1
    );
    render(<GitHubIssueImportModal {...baseProps} />);
    expect(screen.getByText('Fix login bug')).toBeInTheDocument();
    expect(screen.getByText('#42')).toBeInTheDocument();
    expect(screen.getByText('bug')).toBeInTheDocument();
    expect(screen.getByText('@alice')).toBeInTheDocument();
  });

  it('disables Import Selected until at least one issue is selected', () => {
    mockSWRByPage({ 1: [issue(42, 'Fix login bug')] }, 1);
    render(<GitHubIssueImportModal {...baseProps} />);

    const importBtn = screen.getByRole('button', { name: /import selected/i });
    expect(importBtn).toBeDisabled();

    fireEvent.click(screen.getByLabelText('Select issue #42'));
    expect(importBtn).toBeEnabled();
  });

  it('calls onImport with the selected issues', () => {
    const onImport = jest.fn();
    mockSWRByPage(
      { 1: [issue(42, 'Fix login bug'), issue(41, 'Add dark mode')] },
      2
    );
    render(<GitHubIssueImportModal {...baseProps} onImport={onImport} />);

    fireEvent.click(screen.getByLabelText('Select issue #41'));
    fireEvent.click(screen.getByRole('button', { name: /import selected/i }));

    expect(onImport).toHaveBeenCalledTimes(1);
    const passed = onImport.mock.calls[0][0] as GitHubIssue[];
    expect(passed.map((i) => i.number)).toEqual([41]);
  });

  it('shows a selected-count badge that reflects selections', () => {
    mockSWRByPage(
      { 1: [issue(42, 'A'), issue(41, 'B')] },
      2
    );
    render(<GitHubIssueImportModal {...baseProps} />);

    expect(screen.queryByText(/selected/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByLabelText('Select issue #42'));
    fireEvent.click(screen.getByLabelText('Select issue #41'));
    expect(screen.getByText('2 selected')).toBeInTheDocument();
  });

  it('select-all-on-page selects every visible issue', () => {
    mockSWRByPage(
      { 1: [issue(42, 'A'), issue(41, 'B'), issue(40, 'C')] },
      3
    );
    render(<GitHubIssueImportModal {...baseProps} />);

    fireEvent.click(screen.getByLabelText('Select all on page'));
    expect(screen.getByText('3 selected')).toBeInTheDocument();
  });

  it('persists selection across page changes', async () => {
    mockSWRByPage(
      {
        1: [issue(42, 'Page one issue')],
        2: [issue(10, 'Page two issue')],
      },
      30 // > 25 so a second page exists
    );
    render(<GitHubIssueImportModal {...baseProps} />);

    // Select an issue on page 1.
    fireEvent.click(screen.getByLabelText('Select issue #42'));
    expect(screen.getByText('1 selected')).toBeInTheDocument();

    // Go to page 2 — different rows, but the count must persist.
    fireEvent.click(screen.getByLabelText('Next page'));
    await waitFor(() =>
      expect(screen.getByText('Page 2 of 2')).toBeInTheDocument()
    );
    expect(screen.getByText('Page two issue')).toBeInTheDocument();
    expect(screen.getByText('1 selected')).toBeInTheDocument();

    // Selecting a page-2 issue accumulates rather than replaces.
    fireEvent.click(screen.getByLabelText('Select issue #10'));
    expect(screen.getByText('2 selected')).toBeInTheDocument();
  });

  it('renders pagination with the right total page count', () => {
    mockSWRByPage({ 1: [issue(1, 'x')] }, 60); // 60 / 25 = 3 pages
    render(<GitHubIssueImportModal {...baseProps} />);
    expect(screen.getByText('Page 1 of 3')).toBeInTheDocument();
  });

  it('shows an error banner when the fetch fails', () => {
    mockUseSWR.mockReturnValue({
      data: undefined,
      error: { detail: 'GitHub unreachable' },
      isLoading: false,
    } as never);
    render(<GitHubIssueImportModal {...baseProps} />);
    expect(screen.getByRole('alert')).toHaveTextContent('GitHub unreachable');
  });

  it('does not fetch when closed (SWR key is null)', () => {
    mockUseSWR.mockReturnValue({
      data: undefined,
      error: undefined,
      isLoading: false,
    } as never);
    render(<GitHubIssueImportModal {...baseProps} open={false} />);
    // SWR is called with a null key when closed.
    const lastCallKey = mockUseSWR.mock.calls.at(-1)?.[0];
    expect(lastCallKey).toBeNull();
  });
});
