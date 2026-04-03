import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import useSWR from 'swr';
import { PRDVersionHistoryModal } from '@/components/prd/PRDVersionHistoryModal';
import { prdApi } from '@/lib/api';
import type { PrdResponse, PrdDiffResponse } from '@/types';

// ResizeObserver is not available in jsdom
global.ResizeObserver = jest.fn().mockImplementation(() => ({
  observe: jest.fn(),
  unobserve: jest.fn(),
  disconnect: jest.fn(),
}));

jest.mock('swr');
jest.mock('sonner', () => ({
  toast: { success: jest.fn(), error: jest.fn() },
}));
// Radix ScrollArea Viewport hides children in jsdom — render children directly
jest.mock('@/components/ui/scroll-area', () => ({
  ScrollArea: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  ScrollBar: () => null,
}));

jest.mock('@/lib/api', () => ({
  prdApi: {
    getVersions: jest.fn(),
    diff: jest.fn(),
    createVersion: jest.fn(),
  },
}));

const mockUseSWR = useSWR as jest.MockedFunction<typeof useSWR>;
const mockDiff = prdApi.diff as jest.MockedFunction<typeof prdApi.diff>;
const mockCreateVersion = prdApi.createVersion as jest.MockedFunction<typeof prdApi.createVersion>;

const WORKSPACE = '/home/user/project';

const makeVersion = (v: number, summary: string | null = null): PrdResponse => ({
  id: `prd-${v}`,
  workspace_id: 'ws-1',
  title: 'My PRD',
  content: `# Version ${v} content`,
  metadata: {},
  created_at: `2026-01-0${v}T00:00:00Z`,
  version: v,
  parent_id: v > 1 ? `prd-${v - 1}` : null,
  change_summary: summary,
  chain_id: 'chain-1',
});

const fakeVersions: PrdResponse[] = [
  makeVersion(3, 'Added section 3'),
  makeVersion(2, 'Updated intro'),
  makeVersion(1, null),
];

const currentPrd = fakeVersions[0];

const defaultProps = {
  open: true,
  onOpenChange: jest.fn(),
  prd: currentPrd,
  workspacePath: WORKSPACE,
  onVersionRestored: jest.fn(),
};

function setupSWR(versions = fakeVersions) {
  mockUseSWR.mockReturnValue({
    data: versions,
    error: undefined,
    isLoading: false,
    mutate: jest.fn(),
  } as unknown as ReturnType<typeof useSWR>);
}

describe('PRDVersionHistoryModal', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    setupSWR();
  });

  it('renders the dialog with version list', () => {
    render(<PRDVersionHistoryModal {...defaultProps} />);
    expect(screen.getByText('Version History')).toBeInTheDocument();
    expect(screen.getByText('Version 3')).toBeInTheDocument();
    expect(screen.getByText('Version 2')).toBeInTheDocument();
    expect(screen.getByText('Version 1')).toBeInTheDocument();
  });

  it('shows change_summary when present', () => {
    render(<PRDVersionHistoryModal {...defaultProps} />);
    expect(screen.getByText('Added section 3')).toBeInTheDocument();
    expect(screen.getByText('Updated intro')).toBeInTheDocument();
  });

  it('shows "No summary" for versions with null change_summary', () => {
    render(<PRDVersionHistoryModal {...defaultProps} />);
    expect(screen.getByText('No summary')).toBeInTheDocument();
  });

  it('highlights the current version with a "Current" badge', () => {
    render(<PRDVersionHistoryModal {...defaultProps} />);
    expect(screen.getByText('Current')).toBeInTheDocument();
  });

  it('shows loading state while fetching', () => {
    mockUseSWR.mockReturnValue({
      data: undefined,
      error: undefined,
      isLoading: true,
      mutate: jest.fn(),
    } as unknown as ReturnType<typeof useSWR>);

    render(<PRDVersionHistoryModal {...defaultProps} />);
    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  it('shows error state on fetch failure', () => {
    mockUseSWR.mockReturnValue({
      data: undefined,
      error: new Error('Network error'),
      isLoading: false,
      mutate: jest.fn(),
    } as unknown as ReturnType<typeof useSWR>);

    render(<PRDVersionHistoryModal {...defaultProps} />);
    expect(screen.getByText(/failed to load/i)).toBeInTheDocument();
  });

  describe('View version', () => {
    it('shows content preview when View button is clicked', async () => {
      const user = userEvent.setup();
      render(<PRDVersionHistoryModal {...defaultProps} />);

      const viewButtons = screen.getAllByRole('button', { name: /^view$/i });
      await user.click(viewButtons[0]); // click View on version 2

      expect(screen.getByText(/Version 2 content/)).toBeInTheDocument();
    });

    it('shows "Back to list" button in preview mode', async () => {
      const user = userEvent.setup();
      render(<PRDVersionHistoryModal {...defaultProps} />);

      const viewButtons = screen.getAllByRole('button', { name: /^view$/i });
      await user.click(viewButtons[0]);

      expect(screen.getByRole('button', { name: /back to list/i })).toBeInTheDocument();
    });

    it('returns to version list when Back is clicked', async () => {
      const user = userEvent.setup();
      render(<PRDVersionHistoryModal {...defaultProps} />);

      const viewButtons = screen.getAllByRole('button', { name: /^view$/i });
      await user.click(viewButtons[0]);
      await user.click(screen.getByRole('button', { name: /back to list/i }));

      expect(screen.getByText('Version History')).toBeInTheDocument();
      expect(screen.queryByText('# Version 2 content')).not.toBeInTheDocument();
    });
  });

  describe('Compare with current', () => {
    it('calls prdApi.diff and shows diff output', async () => {
      const fakeDiff: PrdDiffResponse = {
        version1: 2,
        version2: 3,
        diff: '@@ -1 +1 @@\n-# Version 2 content\n+# Version 3 content',
      };
      mockDiff.mockResolvedValueOnce(fakeDiff);

      const user = userEvent.setup();
      render(<PRDVersionHistoryModal {...defaultProps} />);

      // versions ordered newest-first; version 3 is current (no View btn), so index 0 = version 2
      const viewButtons = screen.getAllByRole('button', { name: /^view$/i });
      await user.click(viewButtons[0]); // version 2

      const compareBtn = screen.getByRole('button', { name: /compare with current/i });
      await user.click(compareBtn);

      await waitFor(() => {
        expect(mockDiff).toHaveBeenCalledWith(
          currentPrd.id,
          WORKSPACE,
          2,
          3
        );
      });

      await waitFor(() => {
        expect(screen.getByText(/@@ -1 \+1 @@/)).toBeInTheDocument();
      });
    });

    it('shows error message and re-enables Compare button on diff failure', async () => {
      mockDiff.mockRejectedValueOnce(new Error('Network error'));

      const user = userEvent.setup();
      render(<PRDVersionHistoryModal {...defaultProps} />);

      const viewButtons = screen.getAllByRole('button', { name: /^view$/i });
      await user.click(viewButtons[0]); // version 2

      const compareBtn = screen.getByRole('button', { name: /compare with current/i });
      await user.click(compareBtn);

      await waitFor(() => {
        expect(mockDiff).toHaveBeenCalled();
      });

      await waitFor(() => {
        expect(screen.getByText(/failed to load diff/i)).toBeInTheDocument();
      });

      // Compare button should be re-enabled so the user can retry
      expect(screen.getByRole('button', { name: /compare with current/i })).not.toBeDisabled();
    });
  });

  describe('Restore version', () => {
    it('shows confirmation UI when Restore is clicked', async () => {
      const user = userEvent.setup();
      render(<PRDVersionHistoryModal {...defaultProps} />);

      const viewButtons = screen.getAllByRole('button', { name: /^view$/i });
      await user.click(viewButtons[0]); // version 2

      const restoreBtn = screen.getByRole('button', { name: /restore this version/i });
      await user.click(restoreBtn);

      expect(screen.getByText(/restore version 2/i)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /confirm restore/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /cancel/i })).toBeInTheDocument();
    });

    it('calls createVersion with restored content on confirm', async () => {
      const restoredPrd = makeVersion(4, 'Restored from version 2');
      mockCreateVersion.mockResolvedValueOnce(restoredPrd);

      const user = userEvent.setup();
      render(<PRDVersionHistoryModal {...defaultProps} />);

      const viewButtons = screen.getAllByRole('button', { name: /^view$/i });
      await user.click(viewButtons[0]); // version 2
      await user.click(screen.getByRole('button', { name: /restore this version/i }));
      await user.click(screen.getByRole('button', { name: /confirm restore/i }));

      await waitFor(() => {
        expect(mockCreateVersion).toHaveBeenCalledWith(
          currentPrd.id,
          WORKSPACE,
          '# Version 2 content',
          'Restored from version 2'
        );
      });

      await waitFor(() => {
        expect(defaultProps.onVersionRestored).toHaveBeenCalledWith(restoredPrd);
      });
    });

    it('cancels restore without calling API', async () => {
      const user = userEvent.setup();
      render(<PRDVersionHistoryModal {...defaultProps} />);

      const viewButtons = screen.getAllByRole('button', { name: /^view$/i });
      await user.click(viewButtons[0]);
      await user.click(screen.getByRole('button', { name: /restore this version/i }));
      await user.click(screen.getByRole('button', { name: /cancel/i }));

      expect(mockCreateVersion).not.toHaveBeenCalled();
      // Should return to preview without confirmation UI
      expect(screen.queryByRole('button', { name: /confirm restore/i })).not.toBeInTheDocument();
    });

    it('does not show Restore button for the current version', () => {
      render(<PRDVersionHistoryModal {...defaultProps} />);

      // Version 3 is current — its View button should not be visible (or Restore should be absent)
      // The current version row should not have a "View" button at all
      const viewButtons = screen.getAllByRole('button', { name: /^view$/i });
      // Only versions 1 and 2 should have View buttons (not version 3 which is current)
      expect(viewButtons).toHaveLength(2);
    });
  });

  it('does not render version list when closed', () => {
    render(<PRDVersionHistoryModal {...defaultProps} open={false} />);
    expect(screen.queryByText('Version History')).not.toBeInTheDocument();
  });
});
