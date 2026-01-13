/**
 * DiscoveryProgress Error & Recovery Tests
 *
 * Tests covering error handling and recovery:
 * - Stuck state detection (30s timeout)
 * - Restart discovery button and functionality
 * - restartDiscovery API call handling
 * - PRD retry flows
 * - retryPrdGeneration API call handling
 * - Error state display and recovery
 */

import {
  render,
  screen,
  waitFor,
  fireEvent,
  act,
  DiscoveryProgress,
  projectsApi,
  setupMocks,
  cleanupMocks,
  simulateWsMessage,
  mockRestartDiscovery,
  mockRetryPrdGeneration,
  type DiscoveryProgressResponse,
} from './DiscoveryProgress.testutils';

describe('DiscoveryProgress Error & Recovery', () => {
  beforeEach(() => {
    setupMocks();
  });

  afterEach(() => {
    cleanupMocks();
  });

  // ============================================================================
  // Stuck State Detection and Restart Discovery Tests
  // ============================================================================

  describe('Stuck State Detection', () => {
    it('should detect stuck state after 30 seconds without question', async () => {
      const discoveringNoQuestion: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'discovery',
        discovery: {
          state: 'discovering',
          progress_percentage: 0,
          answered_count: 0,
          total_required: 10,
          // No current_question
        },
      };

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: discoveringNoQuestion });

      render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        expect(screen.getByTestId('waiting-for-question')).toBeInTheDocument();
      });

      // Advance time past the stuck timeout (30 seconds)
      jest.advanceTimersByTime(35000);

      await waitFor(() => {
        expect(screen.getByTestId('discovery-stuck')).toBeInTheDocument();
        expect(screen.getByText(/discovery appears to be stuck/i)).toBeInTheDocument();
      });

      // Restart button should appear
      expect(screen.getByTestId('restart-discovery-button')).toBeInTheDocument();
    });

    it('should call restartDiscovery when restart button is clicked', async () => {
      const discoveringNoQuestion: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'discovery',
        discovery: {
          state: 'discovering',
          progress_percentage: 0,
          answered_count: 0,
          total_required: 10,
        },
      };

      const idleData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'discovery',
        discovery: {
          state: 'idle',
          progress_percentage: 0,
          answered_count: 0,
          total_required: 10,
        },
      };

      (projectsApi.getDiscoveryProgress as jest.Mock)
        .mockResolvedValueOnce({ data: discoveringNoQuestion })
        .mockResolvedValueOnce({ data: idleData });

      mockRestartDiscovery.mockResolvedValueOnce({ data: { status: 'reset' } });

      render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        expect(screen.getByTestId('waiting-for-question')).toBeInTheDocument();
      });

      // Advance time past the stuck timeout
      jest.advanceTimersByTime(35000);

      await waitFor(() => {
        expect(screen.getByTestId('restart-discovery-button')).toBeInTheDocument();
      });

      // Click restart button
      const restartButton = screen.getByTestId('restart-discovery-button');
      fireEvent.click(restartButton);

      await waitFor(() => {
        expect(mockRestartDiscovery).toHaveBeenCalledWith(1);
      });
    });

    it('should show restart error when restartDiscovery fails', async () => {
      const discoveringNoQuestion: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'discovery',
        discovery: {
          state: 'discovering',
          progress_percentage: 0,
          answered_count: 0,
          total_required: 10,
        },
      };

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: discoveringNoQuestion });
      mockRestartDiscovery.mockRejectedValueOnce(new Error('Server error'));

      render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        expect(screen.getByTestId('waiting-for-question')).toBeInTheDocument();
      });

      // Advance time past the stuck timeout
      jest.advanceTimersByTime(35000);

      await waitFor(() => {
        expect(screen.getByTestId('restart-discovery-button')).toBeInTheDocument();
      });

      // Click restart button
      const restartButton = screen.getByTestId('restart-discovery-button');
      fireEvent.click(restartButton);

      await waitFor(() => {
        expect(screen.getByText(/failed to restart discovery/i)).toBeInTheDocument();
      });
    });

    it('should call restartDiscovery when restart button is clicked in stuck state', async () => {
      const discoveringNoQuestion: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'discovery',
        discovery: {
          state: 'discovering',
          progress_percentage: 0,
          answered_count: 0,
          total_required: 10,
        },
      };

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: discoveringNoQuestion });
      // Return a promise that resolves slowly
      let resolveRestart: () => void;
      mockRestartDiscovery.mockImplementation(() => new Promise((resolve) => {
        resolveRestart = resolve as () => void;
      }));

      render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        expect(screen.getByTestId('waiting-for-question')).toBeInTheDocument();
      });

      // Advance time past the stuck timeout
      await act(async () => {
        jest.advanceTimersByTime(35000);
      });

      await waitFor(() => {
        expect(screen.getByTestId('restart-discovery-button')).toBeInTheDocument();
      });

      // Click restart button
      const restartButton = screen.getByTestId('restart-discovery-button');
      await act(async () => {
        fireEvent.click(restartButton);
      });

      // Verify the function was called
      expect(mockRestartDiscovery).toHaveBeenCalledWith(1);

      // Resolve the promise to clean up
      await act(async () => {
        resolveRestart!();
      });
    });
  });

  // ============================================================================
  // PRD Error State and Retry Tests
  // ============================================================================

  describe('PRD Error State and Retry', () => {
    it('should call retryPrdGeneration when retry button is clicked', async () => {
      const completedData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'planning',
        discovery: {
          state: 'completed',
          progress_percentage: 100,
          answered_count: 20,
          total_required: 20,
        },
      };

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: completedData });
      mockRetryPrdGeneration.mockResolvedValueOnce({ data: { status: 'started' } });

      render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        expect(screen.getByTestId('prd-generation-status')).toBeInTheDocument();
      });

      // Simulate PRD generation failure
      simulateWsMessage({
        type: 'prd_generation_failed',
        project_id: 1,
        data: { error: 'Connection timeout' },
      });

      await waitFor(() => {
        expect(screen.getByTestId('retry-prd-button')).toBeInTheDocument();
      });

      // Click retry button
      const retryButton = screen.getByTestId('retry-prd-button');
      fireEvent.click(retryButton);

      await waitFor(() => {
        expect(mockRetryPrdGeneration).toHaveBeenCalledWith(1);
      });
    });

    it('should show error when retryPrdGeneration fails', async () => {
      const completedData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'planning',
        discovery: {
          state: 'completed',
          progress_percentage: 100,
          answered_count: 20,
          total_required: 20,
        },
      };

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: completedData });
      mockRetryPrdGeneration.mockRejectedValueOnce(new Error('Service unavailable'));

      render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        expect(screen.getByTestId('prd-generation-status')).toBeInTheDocument();
      });

      // Simulate PRD generation failure
      simulateWsMessage({
        type: 'prd_generation_failed',
        project_id: 1,
        data: { error: 'Initial failure' },
      });

      await waitFor(() => {
        expect(screen.getByTestId('retry-prd-button')).toBeInTheDocument();
      });

      // Click retry button
      const retryButton = screen.getByTestId('retry-prd-button');
      fireEvent.click(retryButton);

      await waitFor(() => {
        expect(screen.getByText(/failed to retry.*service unavailable/i)).toBeInTheDocument();
      });
    });

    it('should transition to loading state when retry button is clicked', async () => {
      const completedData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'planning',
        discovery: {
          state: 'completed',
          progress_percentage: 100,
          answered_count: 20,
          total_required: 20,
        },
      };

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: completedData });
      // Return a promise that resolves slowly to give us time to check the loading state
      let resolveRetry: () => void;
      mockRetryPrdGeneration.mockImplementation(() => new Promise((resolve) => {
        resolveRetry = resolve as () => void;
      }));

      render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        expect(screen.getByTestId('prd-generation-status')).toBeInTheDocument();
      });

      // Simulate PRD generation failure
      simulateWsMessage({
        type: 'prd_generation_failed',
        project_id: 1,
        data: { error: 'Initial failure' },
      });

      await waitFor(() => {
        expect(screen.getByTestId('retry-prd-button')).toBeInTheDocument();
      });

      // Click retry button - wrap in act to allow state update to propagate
      const retryButton = screen.getByTestId('retry-prd-button');
      await act(async () => {
        fireEvent.click(retryButton);
      });

      // Verify the function was called
      expect(mockRetryPrdGeneration).toHaveBeenCalledWith(1);

      // After clicking retry, the error state is cleared and loading state appears
      // The retry button disappears and is replaced by a loading spinner with message
      await waitFor(() => {
        // Retry button should no longer be visible (error was cleared)
        expect(screen.queryByTestId('retry-prd-button')).not.toBeInTheDocument();
        // Loading state should appear (shows "Starting PRD Generation..." until API resolves)
        expect(screen.getByText(/starting prd generation/i)).toBeInTheDocument();
      });

      // Resolve the promise to clean up
      await act(async () => {
        resolveRetry!();
      });
    });
  });
});
