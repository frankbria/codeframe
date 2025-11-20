/**
 * SessionStatus Component Tests
 * Tests for session lifecycle display (014-session-lifecycle, T030)
 */

import { render, screen, waitFor } from '@testing-library/react';
import { SessionStatus } from '@/components/SessionStatus';

// Mock fetch globally
global.fetch = jest.fn();

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
      (global.fetch as jest.Mock).mockImplementation(
        () => new Promise(() => {}) // Never resolves
      );

      render(<SessionStatus projectId={1} />);

      expect(screen.getByText('Loading session...')).toBeInTheDocument();
      expect(screen.getByText('📋')).toBeInTheDocument();
    });

    it('shows blue background for loading state', () => {
      (global.fetch as jest.Mock).mockImplementation(
        () => new Promise(() => {})
      );

      const { container } = render(<SessionStatus projectId={1} />);
      const loadingDiv = container.querySelector('.bg-blue-50');
      expect(loadingDiv).toBeInTheDocument();
    });
  });

  describe('error state', () => {
    it('displays error message when fetch fails', async () => {
      (global.fetch as jest.Mock).mockRejectedValue(
        new Error('Network error')
      );

      render(<SessionStatus projectId={1} />);

      await waitFor(() => {
        expect(screen.getByText(/Could not load session state/i)).toBeInTheDocument();
      });
    });

    it('shows warning emoji for error state', async () => {
      (global.fetch as jest.Mock).mockRejectedValue(
        new Error('Failed to fetch')
      );

      render(<SessionStatus projectId={1} />);

      await waitFor(() => {
        expect(screen.getByText('⚠️')).toBeInTheDocument();
      });
    });

    it('displays specific error message', async () => {
      (global.fetch as jest.Mock).mockRejectedValue(
        new Error('Connection timeout')
      );

      render(<SessionStatus projectId={1} />);

      await waitFor(() => {
        expect(screen.getByText(/Connection timeout/i)).toBeInTheDocument();
      });
    });
  });

  describe('new session state', () => {
    it('displays new session message when no previous session', async () => {
      (global.fetch as jest.Mock).mockResolvedValue({
        ok: true,
        json: async () => ({
          last_session: {
            summary: 'No previous session',
            timestamp: new Date().toISOString(),
          },
          next_actions: [],
          progress_pct: 0,
          active_blockers: [],
        }),
      });

      render(<SessionStatus projectId={1} />);

      await waitFor(() => {
        expect(screen.getByText('🚀 Starting new session...')).toBeInTheDocument();
      });
    });

    it('displays "No previous session state found" for new session', async () => {
      (global.fetch as jest.Mock).mockResolvedValue({
        ok: true,
        json: async () => ({
          last_session: {
            summary: 'No previous session',
            timestamp: new Date().toISOString(),
          },
          next_actions: [],
          progress_pct: 0,
          active_blockers: [],
        }),
      });

      render(<SessionStatus projectId={1} />);

      await waitFor(() => {
        expect(screen.getByText('No previous session state found')).toBeInTheDocument();
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
      (global.fetch as jest.Mock).mockResolvedValue({
        ok: true,
        json: async () => mockSessionData,
      });

      render(<SessionStatus projectId={1} />);

      await waitFor(() => {
        expect(screen.getByText('Last session:')).toBeInTheDocument();
        expect(screen.getByText('Completed 3 tasks')).toBeInTheDocument();
      });
    });

    it('displays time ago for last session', async () => {
      (global.fetch as jest.Mock).mockResolvedValue({
        ok: true,
        json: async () => mockSessionData,
      });

      render(<SessionStatus projectId={1} />);

      await waitFor(() => {
        expect(screen.getByText(/ago/i)).toBeInTheDocument();
      });
    });

    it('displays next actions section', async () => {
      (global.fetch as jest.Mock).mockResolvedValue({
        ok: true,
        json: async () => mockSessionData,
      });

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

      (global.fetch as jest.Mock).mockResolvedValue({
        ok: true,
        json: async () => dataWithManyActions,
      });

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
      (global.fetch as jest.Mock).mockResolvedValue({
        ok: true,
        json: async () => mockSessionData,
      });

      render(<SessionStatus projectId={1} />);

      await waitFor(() => {
        expect(screen.getByText('Progress:')).toBeInTheDocument();
        expect(screen.getByText('69%')).toBeInTheDocument(); // Rounded from 68.5
      });
    });

    it('displays progress bar with correct width', async () => {
      (global.fetch as jest.Mock).mockResolvedValue({
        ok: true,
        json: async () => mockSessionData,
      });

      const { container } = render(<SessionStatus projectId={1} />);

      await waitFor(() => {
        const progressBar = container.querySelector('.bg-blue-600');
        expect(progressBar).toHaveStyle({ width: '68.5%' });
      });
    });

    it('displays active blockers count', async () => {
      (global.fetch as jest.Mock).mockResolvedValue({
        ok: true,
        json: async () => mockSessionData,
      });

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

      (global.fetch as jest.Mock).mockResolvedValue({
        ok: true,
        json: async () => dataWithNoBlockers,
      });

      render(<SessionStatus projectId={1} />);

      await waitFor(() => {
        expect(screen.getByText('Blockers:')).toBeInTheDocument();
        expect(screen.getByText('None')).toBeInTheDocument();
      });
    });
  });

  describe('API interaction', () => {
    it('fetches session data with correct project ID', async () => {
      (global.fetch as jest.Mock).mockResolvedValue({
        ok: true,
        json: async () => ({
          last_session: {
            summary: 'Test',
            timestamp: new Date().toISOString(),
          },
          next_actions: [],
          progress_pct: 0,
          active_blockers: [],
        }),
      });

      render(<SessionStatus projectId={42} />);

      await waitFor(() => {
        expect(global.fetch).toHaveBeenCalledWith('/api/projects/42/session');
      });
    });

    it('handles non-ok response', async () => {
      (global.fetch as jest.Mock).mockResolvedValue({
        ok: false,
        status: 500,
      });

      render(<SessionStatus projectId={1} />);

      await waitFor(() => {
        expect(screen.getByText(/Could not load session state/i)).toBeInTheDocument();
      });
    });
  });

  describe('auto-refresh', () => {
    it('sets up interval to refresh every 30 seconds', async () => {
      (global.fetch as jest.Mock).mockResolvedValue({
        ok: true,
        json: async () => ({
          last_session: {
            summary: 'Test',
            timestamp: new Date().toISOString(),
          },
          next_actions: [],
          progress_pct: 0,
          active_blockers: [],
        }),
      });

      render(<SessionStatus projectId={1} />);

      // Wait for initial fetch
      await waitFor(() => {
        expect(global.fetch).toHaveBeenCalledTimes(1);
      });

      // Advance time by 30 seconds
      jest.advanceTimersByTime(30000);

      await waitFor(() => {
        expect(global.fetch).toHaveBeenCalledTimes(2);
      });
    });

    it('cleans up interval on unmount', async () => {
      (global.fetch as jest.Mock).mockResolvedValue({
        ok: true,
        json: async () => ({
          last_session: {
            summary: 'Test',
            timestamp: new Date().toISOString(),
          },
          next_actions: [],
          progress_pct: 0,
          active_blockers: [],
        }),
      });

      const { unmount } = render(<SessionStatus projectId={1} />);

      await waitFor(() => {
        expect(global.fetch).toHaveBeenCalledTimes(1);
      });

      unmount();

      // Advance time - should not trigger another fetch
      jest.advanceTimersByTime(30000);

      expect(global.fetch).toHaveBeenCalledTimes(1);
    });
  });

  describe('progress bar edge cases', () => {
    it('caps progress bar at 100% when value exceeds 100', async () => {
      (global.fetch as jest.Mock).mockResolvedValue({
        ok: true,
        json: async () => ({
          last_session: {
            summary: 'Test',
            timestamp: new Date().toISOString(),
          },
          next_actions: [],
          progress_pct: 150, // Invalid value > 100
          active_blockers: [],
        }),
      });

      const { container } = render(<SessionStatus projectId={1} />);

      await waitFor(() => {
        const progressBar = container.querySelector('.bg-blue-600');
        // Component uses Math.min(progress_pct, 100)
        expect(progressBar).toHaveStyle({ width: '100%' });
      });
    });

    it('handles 0% progress correctly', async () => {
      (global.fetch as jest.Mock).mockResolvedValue({
        ok: true,
        json: async () => ({
          last_session: {
            summary: 'Test',
            timestamp: new Date().toISOString(),
          },
          next_actions: [],
          progress_pct: 0,
          active_blockers: [],
        }),
      });

      const { container } = render(<SessionStatus projectId={1} />);

      await waitFor(() => {
        const progressBar = container.querySelector('.bg-blue-600');
        expect(progressBar).toHaveStyle({ width: '0%' });
      });
    });
  });

  describe('conditional rendering', () => {
    it('does not render next actions section when array is empty', async () => {
      (global.fetch as jest.Mock).mockResolvedValue({
        ok: true,
        json: async () => ({
          last_session: {
            summary: 'Test',
            timestamp: new Date().toISOString(),
          },
          next_actions: [],
          progress_pct: 50,
          active_blockers: [],
        }),
      });

      render(<SessionStatus projectId={1} />);

      await waitFor(() => {
        expect(screen.queryByText('Next actions:')).not.toBeInTheDocument();
      });
    });

    it('renders all sections when data is complete', async () => {
      (global.fetch as jest.Mock).mockResolvedValue({
        ok: true,
        json: async () => ({
          last_session: {
            summary: 'Complete session',
            timestamp: new Date().toISOString(),
          },
          next_actions: ['Action 1'],
          progress_pct: 75,
          active_blockers: [{ id: 1, question: 'Test?', priority: 'high' }],
        }),
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
