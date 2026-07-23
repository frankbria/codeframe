import React from 'react';
import { render, screen } from '@testing-library/react';
import useSWR from 'swr';
import { PRStatusPanel } from '@/components/review/PRStatusPanel';
import type { PRStatusResponse } from '@/types';

// ── Mocks ─────────────────────────────────────────────────────────────────

jest.mock('swr');
jest.mock('@/lib/api', () => ({
  prApi: { getStatus: jest.fn() },
}));

const mockUseSWR = useSWR as jest.MockedFunction<typeof useSWR>;

// ── Helpers ───────────────────────────────────────────────────────────────

const WORKSPACE = '/home/user/project';
const PR_NUMBER = 42;

const BASE_STATUS: PRStatusResponse = {
  ci_checks: [],
  review_status: 'pending',
  merge_state: 'open',
  pr_url: 'https://github.com/owner/repo/pull/42',
  pr_number: 42,
};

function withData(overrides: Partial<PRStatusResponse> = {}) {
  mockUseSWR.mockReturnValue({
    data: { ...BASE_STATUS, ...overrides },
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

function setup(overrides?: Partial<PRStatusResponse>) {
  withData(overrides);
  return render(<PRStatusPanel prNumber={PR_NUMBER} workspacePath={WORKSPACE} />);
}

// ── Tests ─────────────────────────────────────────────────────────────────

describe('PRStatusPanel', () => {
  beforeEach(() => jest.clearAllMocks());

  describe('loading state', () => {
    it('renders heading and loading skeleton while data is pending', () => {
      withLoading();
      render(<PRStatusPanel prNumber={PR_NUMBER} workspacePath={WORKSPACE} />);

      expect(screen.getByText('PR Status')).toBeInTheDocument();
      // Badge labels should not be present yet
      expect(screen.queryByText('Open')).not.toBeInTheDocument();
      expect(screen.queryByText('Pending Review')).not.toBeInTheDocument();
    });
  });

  describe('merge state badge', () => {
    it('shows Open badge for an open PR', () => {
      setup({ merge_state: 'open' });
      expect(screen.getByText('Open')).toBeInTheDocument();
    });

    it('shows Merged badge when PR is merged', () => {
      setup({ merge_state: 'merged' });
      expect(screen.getByText('Merged')).toBeInTheDocument();
    });

    it('shows Closed badge when PR is closed without merge', () => {
      setup({ merge_state: 'closed' });
      expect(screen.getByText('Closed')).toBeInTheDocument();
    });
  });

  describe('review status badge', () => {
    it('shows Pending Review when there are no reviews', () => {
      setup({ review_status: 'pending' });
      expect(screen.getByText('Pending Review')).toBeInTheDocument();
    });

    it('shows Approved badge', () => {
      setup({ review_status: 'approved' });
      expect(screen.getByText('Approved')).toBeInTheDocument();
    });

    it('shows Changes Requested badge', () => {
      setup({ review_status: 'changes_requested' });
      expect(screen.getByText('Changes Requested')).toBeInTheDocument();
    });
  });

  describe('CI checks', () => {
    it('shows "No checks found" when ci_checks is empty', () => {
      setup({ ci_checks: [] });
      expect(screen.getByText('No checks found.')).toBeInTheDocument();
    });

    it('renders each check name', () => {
      setup({
        ci_checks: [
          { name: 'lint', status: 'completed', conclusion: 'success' },
          { name: 'test-suite', status: 'in_progress', conclusion: null },
        ],
      });
      expect(screen.getByText('lint')).toBeInTheDocument();
      expect(screen.getByText('test-suite')).toBeInTheDocument();
    });

    it('labels an in-progress check as Running', () => {
      setup({
        ci_checks: [{ name: 'build', status: 'in_progress', conclusion: null }],
      });
      expect(screen.getByText('Running')).toBeInTheDocument();
    });

    it('labels a queued check as Queued', () => {
      setup({
        ci_checks: [{ name: 'deploy', status: 'queued', conclusion: null }],
      });
      expect(screen.getByText('Queued')).toBeInTheDocument();
    });

    it('shows the conclusion value for a completed check', () => {
      setup({
        ci_checks: [{ name: 'lint', status: 'completed', conclusion: 'success' }],
      });
      expect(screen.getByText('success')).toBeInTheDocument();
    });

    it('shows the conclusion for a failed check', () => {
      setup({
        ci_checks: [{ name: 'test', status: 'completed', conclusion: 'failure' }],
      });
      expect(screen.getByText('failure')).toBeInTheDocument();
    });
  });

  describe('error state', () => {
    it('shows fallback message when API call fails and no data cached', () => {
      withError();
      render(<PRStatusPanel prNumber={PR_NUMBER} workspacePath={WORKSPACE} />);
      expect(screen.getByText(/Unable to load PR status/i)).toBeInTheDocument();
    });
  });

  describe('SWR integration', () => {
    it('passes the correct SWR key', () => {
      withData();
      render(<PRStatusPanel prNumber={PR_NUMBER} workspacePath={WORKSPACE} />);

      const [key] = mockUseSWR.mock.calls[0];
      expect(key).toContain(`pr_number=${PR_NUMBER}`);
      expect(key).toContain(`workspace_path=${encodeURIComponent(WORKSPACE)}`);
    });

    it('passes a refreshInterval function to SWR config', () => {
      withData();
      render(<PRStatusPanel prNumber={PR_NUMBER} workspacePath={WORKSPACE} />);

      const config = mockUseSWR.mock.calls[0][2] as { refreshInterval: unknown };
      expect(typeof config.refreshInterval).toBe('function');
    });

    it('refreshInterval returns 0 when merge_state is merged', () => {
      withData({ merge_state: 'merged' });
      render(<PRStatusPanel prNumber={PR_NUMBER} workspacePath={WORKSPACE} />);

      const config = mockUseSWR.mock.calls[0][2] as {
        refreshInterval: (data: PRStatusResponse) => number;
      };
      expect(config.refreshInterval({ ...BASE_STATUS, merge_state: 'merged' })).toBe(0);
    });

    it('refreshInterval returns 0 when merge_state is closed', () => {
      withData({ merge_state: 'closed' });
      render(<PRStatusPanel prNumber={PR_NUMBER} workspacePath={WORKSPACE} />);

      const config = mockUseSWR.mock.calls[0][2] as {
        refreshInterval: (data: PRStatusResponse) => number;
      };
      expect(config.refreshInterval({ ...BASE_STATUS, merge_state: 'closed' })).toBe(0);
    });

    it('refreshInterval returns 30000 when PR is still open', () => {
      withData({ merge_state: 'open' });
      render(<PRStatusPanel prNumber={PR_NUMBER} workspacePath={WORKSPACE} />);

      const config = mockUseSWR.mock.calls[0][2] as {
        refreshInterval: (data: PRStatusResponse) => number;
      };
      expect(config.refreshInterval({ ...BASE_STATUS, merge_state: 'open' })).toBe(30_000);
    });
  });
});
