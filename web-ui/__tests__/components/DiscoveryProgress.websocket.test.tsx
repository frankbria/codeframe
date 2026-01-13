/**
 * DiscoveryProgress WebSocket Tests
 *
 * Tests covering WebSocket message handling:
 * - WebSocket message handler verification
 * - Discovery event handling (discovery_starting, discovery_reset, question_ready)
 * - PRD generation event handling (prd_generation_started, prd_generation_progress, prd_generation_completed, prd_generation_failed)
 * - Project ID filtering (ignore messages for other projects)
 * - WebSocket connection lifecycle
 */

import {
  render,
  screen,
  waitFor,
  fireEvent,
  DiscoveryProgress,
  projectsApi,
  setupMocks,
  cleanupMocks,
  simulateWsMessage,
  type DiscoveryProgressResponse,
} from './DiscoveryProgress.testutils';

describe('DiscoveryProgress WebSocket', () => {
  beforeEach(() => {
    setupMocks();
  });

  afterEach(() => {
    cleanupMocks();
  });

  // ============================================================================
  // WebSocket Message Handlers Tests
  // ============================================================================

  describe('WebSocket Message Handlers', () => {
    it('should handle discovery_starting message', async () => {
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

      const discoveringData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'discovery',
        discovery: {
          state: 'discovering',
          progress_percentage: 0,
          answered_count: 0,
          total_required: 10,
          current_question: {
            id: 'q1',
            question: 'What is your project about?',
            category: 'overview',
          },
        },
      };

      (projectsApi.getDiscoveryProgress as jest.Mock)
        .mockResolvedValueOnce({ data: idleData })
        .mockResolvedValueOnce({ data: discoveringData });

      render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        expect(screen.getByTestId('start-discovery-button')).toBeInTheDocument();
      });

      // Simulate WebSocket discovery_starting message
      simulateWsMessage({ type: 'discovery_starting', project_id: 1 });

      // Should trigger a refresh
      jest.advanceTimersByTime(500);

      await waitFor(() => {
        expect(projectsApi.getDiscoveryProgress).toHaveBeenCalledTimes(2);
      });
    });

    it('should handle prd_generation_started message', async () => {
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

      render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        expect(screen.getByTestId('prd-generation-status')).toBeInTheDocument();
      });

      // Simulate WebSocket prd_generation_started message
      simulateWsMessage({ type: 'prd_generation_started', project_id: 1 });

      await waitFor(() => {
        expect(screen.getByText(/initializing prd generation/i)).toBeInTheDocument();
      });
    });

    it('should handle prd_generation_progress message with progress updates', async () => {
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

      render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        expect(screen.getByTestId('prd-generation-status')).toBeInTheDocument();
      });

      // Simulate WebSocket prd_generation_progress message
      simulateWsMessage({
        type: 'prd_generation_progress',
        project_id: 1,
        stage: 'analyzing',
        message: 'Analyzing requirements...',
        progress_pct: 30,
      });

      await waitFor(() => {
        expect(screen.getByText(/analyzing requirements/i)).toBeInTheDocument();
        expect(screen.getByText('30%')).toBeInTheDocument();
      });
    });

    it('should handle prd_generation_completed message', async () => {
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

      const mockOnViewPRD = jest.fn();
      render(<DiscoveryProgress projectId={1} onViewPRD={mockOnViewPRD} />);

      await waitFor(() => {
        expect(screen.getByTestId('prd-generation-status')).toBeInTheDocument();
      });

      // Simulate WebSocket prd_generation_completed message
      simulateWsMessage({ type: 'prd_generation_completed', project_id: 1 });

      await waitFor(() => {
        expect(screen.getByText(/prd generated successfully/i)).toBeInTheDocument();
      });

      // View PRD button should appear
      const viewPrdButton = screen.getByTestId('view-prd-button');
      expect(viewPrdButton).toBeInTheDocument();

      // Click View PRD button
      fireEvent.click(viewPrdButton);
      expect(mockOnViewPRD).toHaveBeenCalled();
    });

    it('should handle prd_generation_failed message', async () => {
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

      render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        expect(screen.getByTestId('prd-generation-status')).toBeInTheDocument();
      });

      // Simulate WebSocket prd_generation_failed message
      simulateWsMessage({
        type: 'prd_generation_failed',
        project_id: 1,
        data: { error: 'API rate limit exceeded' },
      });

      await waitFor(() => {
        expect(screen.getByText(/prd generation failed/i)).toBeInTheDocument();
        expect(screen.getByText(/api rate limit exceeded/i)).toBeInTheDocument();
      });

      // Retry button should appear
      expect(screen.getByTestId('retry-prd-button')).toBeInTheDocument();
    });

    it('should handle discovery_reset message', async () => {
      const discoveringData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'discovery',
        discovery: {
          state: 'discovering',
          progress_percentage: 50,
          answered_count: 5,
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
        .mockResolvedValueOnce({ data: discoveringData })
        .mockResolvedValueOnce({ data: idleData });

      render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        expect(screen.getByText(/answered/i)).toBeInTheDocument();
      });

      // Simulate WebSocket discovery_reset message
      simulateWsMessage({ type: 'discovery_reset', project_id: 1 });

      await waitFor(() => {
        expect(projectsApi.getDiscoveryProgress).toHaveBeenCalledTimes(2);
      });
    });

    it('should handle discovery_question_ready message', async () => {
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

      const discoveringWithQuestion: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'discovery',
        discovery: {
          state: 'discovering',
          progress_percentage: 0,
          answered_count: 0,
          total_required: 10,
          current_question: {
            id: 'q1',
            question: 'What is your project about?',
            category: 'overview',
          },
        },
      };

      (projectsApi.getDiscoveryProgress as jest.Mock)
        .mockResolvedValueOnce({ data: discoveringNoQuestion })
        .mockResolvedValueOnce({ data: discoveringWithQuestion });

      render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        expect(screen.getByTestId('waiting-for-question')).toBeInTheDocument();
      });

      // Simulate WebSocket discovery_question_ready message
      simulateWsMessage({ type: 'discovery_question_ready', project_id: 1 });

      await waitFor(() => {
        expect(screen.getByText(/what is your project about/i)).toBeInTheDocument();
      });
    });

    it('should ignore WebSocket messages for different projects', async () => {
      const mockData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'discovery',
        discovery: {
          state: 'discovering',
          progress_percentage: 50,
          answered_count: 5,
          total_required: 10,
        },
      };

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: mockData });

      render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        expect(screen.getByText(/answered/i)).toBeInTheDocument();
      });

      const initialCallCount = (projectsApi.getDiscoveryProgress as jest.Mock).mock.calls.length;

      // Simulate WebSocket message for different project
      simulateWsMessage({ type: 'discovery_reset', project_id: 999 });

      // Should not trigger a refresh for the wrong project
      await waitFor(() => {
        expect(projectsApi.getDiscoveryProgress).toHaveBeenCalledTimes(initialCallCount);
      });
    });
  });
});
