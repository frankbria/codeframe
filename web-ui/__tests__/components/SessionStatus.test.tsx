/**
 * SessionStatus Component Tests
 * Tests for session lifecycle display (014-session-lifecycle, T030)
 */

// Mock Hugeicons used by SessionStatus
jest.mock('@hugeicons/react', () => ({
  ClipboardIcon: ({ className }: { className?: string }) => (
    <svg className={className} data-testid="clipboard-icon" />
  ),
  Alert02Icon: ({ className }: { className?: string }) => (
    <svg className={className} data-testid="alert-icon" />
  ),
}));

// Mock the api-client module BEFORE imports
jest.mock('@/lib/api-client', () => ({
  authFetch: jest.fn(),
}));

import { render, screen, waitFor } from '@testing-library/react';
import { SessionStatus } from '@/components/SessionStatus';
import { authFetch } from '@/lib/api-client';

const mockAuthFetch = authFetch as jest.MockedFunction<typeof authFetch>;

describe('SessionStatus', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.runOnlyPendingTimers();
    jest.useRealTimers();
  });

  describe('loading state', () => {
    it('displays loading state initially', () => {
      mockAuthFetch.mockImplementation(
        () => new Promise(() => {}) // Never resolves
      );

      render(<SessionStatus projectId={1} />);

      expect(screen.getByText('Loading session...')).toBeInTheDocument();
      expect(screen.getByTestId('clipboard-icon')).toBeInTheDocument();
    });

    it('shows blue background for loading state', () => {
      mockAuthFetch.mockImplementation(
        () => new Promise(() => {})
      );

      const { container } = render(<SessionStatus projectId={1} />);
      const loadingDiv = container.querySelector('.bg-primary\\/10');
      expect(loadingDiv).toBeInTheDocument();
    });
  });

  describe('error state', () => {
    it('displays error message when fetch fails', async () => {
      mockAuthFetch.mockRejectedValueOnce(
        new Error('Network error')
      );

      render(<SessionStatus projectId={1} />);

      await waitFor(() => {
        expect(screen.getByText(/Could not load session state/i)).toBeInTheDocument();
      });
    });

    it('shows alert icon for error state', async () => {
      mockAuthFetch.mockRejectedValueOnce(
        new Error('Failed to fetch')
      );

      render(<SessionStatus projectId={1} />);

      await waitFor(() => {
        expect(screen.getByTestId('alert-icon')).toBeInTheDocument();
      });
    });

    it('displays specific error message', async () => {
      mockAuthFetch.mockRejectedValueOnce(
        new Error('Connection timeout')
      );

      render(<SessionStatus projectId={1} />);

      await waitFor(() => {
        expect(screen.getByText(/Connection timeout/i)).toBeInTheDocument();
      });
    });
  });

  describe('new session state', () => {
    it('displays "No previous session" as regular summary for new projects', async () => {
      mockAuthFetch.mockResolvedValueOnce({
        last_session: {
          summary: 'No previous session',
          timestamp: new Date().toISOString(),
        },
        next_actions: [],
        progress_pct: 0,
        active_blockers: [],
      });

      render(<SessionStatus projectId={1} />);

      await waitFor(() => {
        // New sessions should display summary as regular text, not placeholder
        expect(screen.getByText('Last session:')).toBeInTheDocument();
        expect(screen.getByText('No previous session')).toBeInTheDocument();
      });
    });

    it('displays full session UI even for new sessions', async () => {
      mockAuthFetch.mockResolvedValueOnce({
        last_session: {
          summary: 'No previous session',
          timestamp: new Date().toISOString(),
        },
        next_actions: [],
        progress_pct: 0,
        active_blockers: [],
      });

      render(<SessionStatus projectId={1} />);

      await waitFor(() => {
        // All standard session UI elements should be present
        expect(screen.getByText('Session Context')).toBeInTheDocument();
        expect(screen.getByText('Progress:')).toBeInTheDocument();
        expect(screen.getByText('Blockers:')).toBeInTheDocument();
        expect(screen.getByText('0%')).toBeInTheDocument();
        expect(screen.getByText('None')).toBeInTheDocument();
      });
    });
  });

  describe('existing session state', () => {
    const mockSessionData = {
      last_session: {
        summary: 'Completed 3 tasks',
        timestamp: new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString(), // 2 hours ago
      },
      next_actions: ['Complete Task #4', 'Review PR #12', 'Fix bug in auth'],
      progress_pct: 68.5,
      active_blockers: [
        { id: 1, question: 'Which OAuth provider?', priority: 'high' },
        { id: 2, question: 'Database schema?', priority: 'medium' },
      ],
    };

    it('displays last session summary', async () => {
      mockAuthFetch.mockResolvedValueOnce(mockSessionData);

      render(<SessionStatus projectId={1} />);

      await waitFor(() => {
        expect(screen.getByText('Last session:')).toBeInTheDocument();
        expect(screen.getByText('Completed 3 tasks')).toBeInTheDocument();
      });
    });

    it('displays time ago for last session', async () => {
      mockAuthFetch.mockResolvedValueOnce(mockSessionData);

      render(<SessionStatus projectId={1} />);

      await waitFor(() => {
        expect(screen.getByText(/ago/i)).toBeInTheDocument();
      });
    });

    it('displays next actions section', async () => {
      mockAuthFetch.mockResolvedValueOnce(mockSessionData);

      render(<SessionStatus projectId={1} />);

      await waitFor(() => {
        expect(screen.getByText('Next actions:')).toBeInTheDocument();
        expect(screen.getByText('Complete Task #4')).toBeInTheDocument();
        expect(screen.getByText('Review PR #12')).toBeInTheDocument();
        expect(screen.getByText('Fix bug in auth')).toBeInTheDocument();
      });
    });

    it('limits next actions to 3 items', async () => {
      const dataWithManyActions = {
        ...mockSessionData,
        next_actions: ['Action 1', 'Action 2', 'Action 3', 'Action 4', 'Action 5'],
      };

      mockAuthFetch.mockResolvedValueOnce(dataWithManyActions);

      render(<SessionStatus projectId={1} />);

      await waitFor(() => {
        expect(screen.getByText('Action 1')).toBeInTheDocument();
        expect(screen.getByText('Action 2')).toBeInTheDocument();
        expect(screen.getByText('Action 3')).toBeInTheDocument();
        expect(screen.queryByText('Action 4')).not.toBeInTheDocument();
        expect(screen.queryByText('Action 5')).not.toBeInTheDocument();
      });
    });

    it('displays progress percentage', async () => {
      mockAuthFetch.mockResolvedValueOnce(mockSessionData);

      render(<SessionStatus projectId={1} />);

      await waitFor(() => {
        expect(screen.getByText('Progress:')).toBeInTheDocument();
        expect(screen.getByText('69%')).toBeInTheDocument(); // Rounded from 68.5
      });
    });

    it('displays progress bar with correct width', async () => {
      mockAuthFetch.mockResolvedValueOnce(mockSessionData);

      const { container } = render(<SessionStatus projectId={1} />);

      await waitFor(() => {
        const progressBar = container.querySelector('.bg-primary');
        expect(progressBar).toHaveStyle({ width: '68.5%' });
      });
    });

    it('displays active blockers count', async () => {
      mockAuthFetch.mockResolvedValueOnce(mockSessionData);

      render(<SessionStatus projectId={1} />);

      await waitFor(() => {
        expect(screen.getByText('Blockers:')).toBeInTheDocument();
        expect(screen.getByText('2 active')).toBeInTheDocument();
      });
    });

    it('displays "None" when no blockers', async () => {
      const dataWithNoBlockers = {
        ...mockSessionData,
        active_blockers: [],
      };

      mockAuthFetch.mockResolvedValueOnce(dataWithNoBlockers);

      render(<SessionStatus projectId={1} />);

      await waitFor(() => {
        expect(screen.getByText('Blockers:')).toBeInTheDocument();
        expect(screen.getByText('None')).toBeInTheDocument();
      });
    });
  });

  describe('API interaction', () => {
    it('fetches session data with correct project ID', async () => {
      mockAuthFetch.mockResolvedValueOnce({
        last_session: {
          summary: 'Test',
          timestamp: new Date().toISOString(),
        },
        next_actions: [],
        progress_pct: 0,
        active_blockers: [],
      });

      render(<SessionStatus projectId={42} />);

      await waitFor(() => {
        expect(mockAuthFetch).toHaveBeenCalledWith(
          expect.stringContaining('/api/projects/42/session')
        );
      });
    });

    it('handles non-ok response', async () => {
      // authFetch throws on non-ok responses
      mockAuthFetch.mockRejectedValueOnce(
        new Error('Request failed: 500')
      );

      render(<SessionStatus projectId={1} />);

      await waitFor(() => {
        expect(screen.getByText(/Could not load session state/i)).toBeInTheDocument();
      });
    });
  });

  describe('auto-refresh', () => {
    it('sets up interval to refresh every 30 seconds', async () => {
      mockAuthFetch.mockResolvedValue({
        last_session: {
          summary: 'Test',
          timestamp: new Date().toISOString(),
        },
        next_actions: [],
        progress_pct: 0,
        active_blockers: [],
      });

      render(<SessionStatus projectId={1} />);

      // Wait for initial fetch
      await waitFor(() => {
        expect(mockAuthFetch).toHaveBeenCalledTimes(1);
      });

      // Advance time by 30 seconds
      jest.advanceTimersByTime(30000);

      await waitFor(() => {
        expect(mockAuthFetch).toHaveBeenCalledTimes(2);
      });
    });

    it('cleans up interval on unmount', async () => {
      mockAuthFetch.mockResolvedValue({
        last_session: {
          summary: 'Test',
          timestamp: new Date().toISOString(),
        },
        next_actions: [],
        progress_pct: 0,
        active_blockers: [],
      });

      const { unmount } = render(<SessionStatus projectId={1} />);

      await waitFor(() => {
        expect(mockAuthFetch).toHaveBeenCalledTimes(1);
      });

      unmount();

      // Advance time - should not trigger another fetch
      jest.advanceTimersByTime(30000);

      expect(mockAuthFetch).toHaveBeenCalledTimes(1);
    });
  });

  describe('progress bar edge cases', () => {
    it('caps progress bar at 100% when value exceeds 100', async () => {
      mockAuthFetch.mockResolvedValueOnce({
        last_session: {
          summary: 'Test',
          timestamp: new Date().toISOString(),
        },
        next_actions: [],
        progress_pct: 150, // Invalid value > 100
        active_blockers: [],
      });

      const { container } = render(<SessionStatus projectId={1} />);

      await waitFor(() => {
        const progressBar = container.querySelector('.bg-primary');
        // Component uses Math.min(progress_pct, 100)
        expect(progressBar).toHaveStyle({ width: '100%' });
      });
    });

    it('handles 0% progress correctly', async () => {
      mockAuthFetch.mockResolvedValueOnce({
        last_session: {
          summary: 'Test',
          timestamp: new Date().toISOString(),
        },
        next_actions: [],
        progress_pct: 0,
        active_blockers: [],
      });

      const { container } = render(<SessionStatus projectId={1} />);

      await waitFor(() => {
        const progressBar = container.querySelector('.bg-primary');
        expect(progressBar).toHaveStyle({ width: '0%' });
      });
    });
  });

  describe('conditional rendering', () => {
    it('does not render next actions section when array is empty', async () => {
      mockAuthFetch.mockResolvedValueOnce({
        last_session: {
          summary: 'Test',
          timestamp: new Date().toISOString(),
        },
        next_actions: [],
        progress_pct: 50,
        active_blockers: [],
      });

      render(<SessionStatus projectId={1} />);

      await waitFor(() => {
        expect(screen.queryByText('Next actions:')).not.toBeInTheDocument();
      });
    });

    it('renders all sections when data is complete', async () => {
      mockAuthFetch.mockResolvedValueOnce({
        last_session: {
          summary: 'Complete session',
          timestamp: new Date().toISOString(),
        },
        next_actions: ['Action 1'],
        progress_pct: 75,
        active_blockers: [{ id: 1, question: 'Test?', priority: 'high' }],
      });

      render(<SessionStatus projectId={1} />);

      await waitFor(() => {
        expect(screen.getByText('Last session:')).toBeInTheDocument();
        expect(screen.getByText('Next actions:')).toBeInTheDocument();
        expect(screen.getByText('Progress:')).toBeInTheDocument();
        expect(screen.getByText('Blockers:')).toBeInTheDocument();
      });
    });
  });
});
