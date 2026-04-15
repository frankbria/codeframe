import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import useSWR from 'swr';
import { PRHistoryPanel } from '@/components/review/PRHistoryPanel';
import { prApi } from '@/lib/api';
import type { PRHistoryResponse } from '@/types';

// ── Mocks ─────────────────────────────────────────────────────────────────

jest.mock('swr');
jest.mock('@/lib/api', () => ({
  prApi: { getHistory: jest.fn(), getFiles: jest.fn() },
  proofApi: { capture: jest.fn() },
}));

const mockGetFiles = prApi.getFiles as jest.MockedFunction<typeof prApi.getFiles>;

const mockUseSWR = useSWR as jest.MockedFunction<typeof useSWR>;

// ── Helpers ───────────────────────────────────────────────────────────────

const WORKSPACE = '/home/user/project';

const SAMPLE_HISTORY: PRHistoryResponse = {
  pull_requests: [
    {
      number: 10,
      title: 'feat: add user auth',
      merged_at: '2026-04-10T12:00:00Z',
      author: 'alice',
      url: 'https://github.com/owner/repo/pull/10',
      proof_snapshot: {
        gates_passed: 7,
        gates_total: 9,
        gate_breakdown: [
          { gate: 'unit-tests', status: 'satisfied' },
          { gate: 'lint', status: 'satisfied' },
          { gate: 'security', status: 'failed' },
        ],
      },
    },
    {
      number: 11,
      title: 'fix: resolve login bug',
      merged_at: '2026-04-11T14:00:00Z',
      author: null,
      url: 'https://github.com/owner/repo/pull/11',
      proof_snapshot: null,
    },
  ],
  total: 2,
};

const ALL_PASSED: PRHistoryResponse = {
  pull_requests: [
    {
      number: 20,
      title: 'feat: perfect PR',
      merged_at: '2026-04-12T10:00:00Z',
      author: 'bob',
      url: 'https://github.com/owner/repo/pull/20',
      proof_snapshot: {
        gates_passed: 9,
        gates_total: 9,
        gate_breakdown: [
          { gate: 'unit-tests', status: 'satisfied' },
          { gate: 'lint', status: 'satisfied' },
        ],
      },
    },
  ],
  total: 1,
};

function withData(data: PRHistoryResponse) {
  mockUseSWR.mockReturnValue({
    data,
    error: undefined,
    isLoading: false,
    isValidating: false,
    mutate: jest.fn(),
  } as ReturnType<typeof useSWR>);
}

function withLoading() {
  mockUseSWR.mockReturnValue({
    data: undefined,
    error: undefined,
    isLoading: true,
    isValidating: true,
    mutate: jest.fn(),
  } as ReturnType<typeof useSWR>);
}

function withError() {
  mockUseSWR.mockReturnValue({
    data: undefined,
    error: new Error('Network error'),
    isLoading: false,
    isValidating: false,
    mutate: jest.fn(),
  } as ReturnType<typeof useSWR>);
}

function withEmpty() {
  withData({ pull_requests: [], total: 0 });
}

// ── Tests ─────────────────────────────────────────────────────────────────

describe('PRHistoryPanel', () => {
  beforeEach(() => jest.clearAllMocks());

  describe('loading state', () => {
    it('renders heading and loading skeleton while data is pending', () => {
      withLoading();
      render(<PRHistoryPanel workspacePath={WORKSPACE} />);

      expect(screen.getByText('PR History')).toBeInTheDocument();
      // PR titles should not be present yet
      expect(screen.queryByText('feat: add user auth')).not.toBeInTheDocument();
    });
  });

  describe('empty state', () => {
    it('renders "No merged PRs yet" when list is empty', () => {
      withEmpty();
      render(<PRHistoryPanel workspacePath={WORKSPACE} />);

      expect(screen.getByText('No merged PRs yet')).toBeInTheDocument();
    });
  });

  describe('error state', () => {
    it('shows fallback message when API call fails', () => {
      withError();
      render(<PRHistoryPanel workspacePath={WORKSPACE} />);

      expect(screen.getByText('Unable to load PR history')).toBeInTheDocument();
    });
  });

  describe('PR list rendering', () => {
    it('renders PR titles', () => {
      withData(SAMPLE_HISTORY);
      render(<PRHistoryPanel workspacePath={WORKSPACE} />);

      expect(screen.getByText('feat: add user auth')).toBeInTheDocument();
      expect(screen.getByText('fix: resolve login bug')).toBeInTheDocument();
    });

    it('renders merge dates and author', () => {
      withData(SAMPLE_HISTORY);
      render(<PRHistoryPanel workspacePath={WORKSPACE} />);

      // Check that date text is present (formatted by toLocaleDateString)
      const dateText = new Date('2026-04-10T12:00:00Z').toLocaleDateString();
      expect(screen.getByText(new RegExp(dateText))).toBeInTheDocument();
      expect(screen.getByText(/by alice/)).toBeInTheDocument();
    });

    it('renders proof badge with partial pass count', () => {
      withData(SAMPLE_HISTORY);
      render(<PRHistoryPanel workspacePath={WORKSPACE} />);

      expect(screen.getByText('7/9 gates')).toBeInTheDocument();
    });

    it('renders "No proof data" badge when snapshot is null', () => {
      withData(SAMPLE_HISTORY);
      render(<PRHistoryPanel workspacePath={WORKSPACE} />);

      expect(screen.getByText('No proof data')).toBeInTheDocument();
    });

    it('renders proof badge with all-pass styling text', () => {
      withData(ALL_PASSED);
      render(<PRHistoryPanel workspacePath={WORKSPACE} />);

      expect(screen.getByText('9/9 gates')).toBeInTheDocument();
    });
  });

  describe('expand/collapse gate breakdown', () => {
    it('clicking a row shows gate breakdown', () => {
      withData(SAMPLE_HISTORY);
      render(<PRHistoryPanel workspacePath={WORKSPACE} />);

      // Gate names should not be visible initially
      expect(screen.queryByText('unit-tests')).not.toBeInTheDocument();

      // Click the first PR row
      fireEvent.click(screen.getByText('feat: add user auth'));

      // Gate breakdown should now be visible
      expect(screen.getByText('unit-tests')).toBeInTheDocument();
      expect(screen.getByText('lint')).toBeInTheDocument();
      expect(screen.getByText('security')).toBeInTheDocument();
    });

    it('clicking the same row again collapses gate breakdown', () => {
      withData(SAMPLE_HISTORY);
      render(<PRHistoryPanel workspacePath={WORKSPACE} />);

      // Expand
      fireEvent.click(screen.getByText('feat: add user auth'));
      expect(screen.getByText('unit-tests')).toBeInTheDocument();

      // Collapse
      fireEvent.click(screen.getByText('feat: add user auth'));
      expect(screen.queryByText('unit-tests')).not.toBeInTheDocument();
    });

    it('shows "No proof snapshot available" when expanding a PR without proof data', () => {
      withData(SAMPLE_HISTORY);
      render(<PRHistoryPanel workspacePath={WORKSPACE} />);

      fireEvent.click(screen.getByText('fix: resolve login bug'));
      expect(screen.getByText('No proof snapshot available for this PR.')).toBeInTheDocument();
    });
  });

  describe('SWR integration', () => {
    it('passes the correct SWR key containing workspace path', () => {
      withData(SAMPLE_HISTORY);
      render(<PRHistoryPanel workspacePath={WORKSPACE} />);

      const [key] = mockUseSWR.mock.calls[0];
      expect(key).toContain(`workspace_path=${encodeURIComponent(WORKSPACE)}`);
    });

    it('passes null SWR key when workspacePath is empty', () => {
      withLoading();
      render(<PRHistoryPanel workspacePath="" />);

      const [key] = mockUseSWR.mock.calls[0];
      expect(key).toBeNull();
    });
  });

  describe('Report Glitch button', () => {
    it('renders a Report Glitch button for each PR row', () => {
      withData(SAMPLE_HISTORY);
      render(<PRHistoryPanel workspacePath={WORKSPACE} />);

      const buttons = screen.getAllByRole('button', { name: /Report Glitch/i });
      expect(buttons).toHaveLength(2);
    });

    it('fetches PR files when Report Glitch is clicked', async () => {
      mockGetFiles.mockResolvedValue(['src/auth.py', 'tests/test_auth.py']);
      withData(SAMPLE_HISTORY);
      render(<PRHistoryPanel workspacePath={WORKSPACE} />);

      const buttons = screen.getAllByRole('button', { name: /Report Glitch/i });
      fireEvent.click(buttons[0]);

      await waitFor(() => {
        expect(mockGetFiles).toHaveBeenCalledWith(WORKSPACE, 10);
      });
    });

    it('opens the capture modal after files are fetched', async () => {
      mockGetFiles.mockResolvedValue(['src/auth.py']);
      withData(SAMPLE_HISTORY);
      render(<PRHistoryPanel workspacePath={WORKSPACE} />);

      const buttons = screen.getAllByRole('button', { name: /Report Glitch/i });
      fireEvent.click(buttons[0]);

      await waitFor(() => {
        expect(screen.getByRole('heading', { name: 'Capture Glitch' })).toBeInTheDocument();
      });
    });
  });
});
