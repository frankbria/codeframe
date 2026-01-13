/**
 * DiscoveryProgress PRD Generation Tests
 *
 * Tests covering PRD generation functionality:
 * - View PRD button display and functionality
 * - Minimize/expand functionality
 * - Task creation indicators
 * - WebSocket-driven PRD progress tracking
 * - PRD generation states (started/progress/completed/failed)
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
  mockGetPRD,
  mockTasksList,
  type DiscoveryProgressResponse,
} from './DiscoveryProgress.testutils';

describe('DiscoveryProgress PRD Generation', () => {
  beforeEach(() => {
    setupMocks();
  });

  afterEach(() => {
    cleanupMocks();
  });

  // ============================================================================
  // PRD Progress Tracking Tests
  // ============================================================================

  describe('PRD Generation Progress Tracking', () => {
    it('should show View PRD button when prdCompleted is true', async () => {
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

      // Simulate prd_generation_completed WebSocket message to trigger prdCompleted state
      simulateWsMessage({ type: 'prd_generation_completed', project_id: 1 });

      await waitFor(() => {
        expect(screen.getByTestId('view-prd-button')).toBeInTheDocument();
      });
    });

    it('should call onViewPRD callback when View PRD button is clicked', async () => {
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

      // Simulate prd_generation_completed WebSocket message
      simulateWsMessage({ type: 'prd_generation_completed', project_id: 1 });

      await waitFor(() => {
        expect(screen.getByTestId('view-prd-button')).toBeInTheDocument();
      });

      // Click the View PRD button
      fireEvent.click(screen.getByTestId('view-prd-button'));

      expect(mockOnViewPRD).toHaveBeenCalledTimes(1);
    });

    it('should show minimize button when PRD is completed', async () => {
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

      // Simulate prd_generation_completed WebSocket message
      simulateWsMessage({ type: 'prd_generation_completed', project_id: 1 });

      await waitFor(() => {
        expect(screen.getByTestId('minimize-discovery-button')).toBeInTheDocument();
      });
    });

    it('should show task creation phase indicator when PRD is complete and phase is planning', async () => {
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
      // Mock PRD as available and no existing tasks (required for taskStateInitialized)
      mockGetPRD.mockResolvedValue({ data: { status: 'available' } });
      mockTasksList.mockResolvedValue({ data: { tasks: [], total: 0 } });

      render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        expect(screen.getByTestId('prd-generation-status')).toBeInTheDocument();
      });

      // Simulate prd_generation_completed WebSocket message
      simulateWsMessage({ type: 'prd_generation_completed', project_id: 1 });

      await waitFor(() => {
        expect(screen.getByTestId('task-generation-section')).toBeInTheDocument();
        expect(screen.getByText(/ready for task breakdown/i)).toBeInTheDocument();
      });
    });

    it('should show PRD generation status section when discovery is completed', async () => {
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
        const prdStatus = screen.getByTestId('prd-generation-status');
        expect(prdStatus).toBeInTheDocument();
      });
    });

    it('should display PRD progress percentage during generation', async () => {
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

      // Simulate prd_generation_started to initialize PRD generation state
      simulateWsMessage({ type: 'prd_generation_started', project_id: 1 });

      await waitFor(() => {
        expect(screen.getByText(/initializing/i)).toBeInTheDocument();
      });

      // Simulate progress at 10%
      simulateWsMessage({
        type: 'prd_generation_progress',
        project_id: 1,
        stage: 'analyzing',
        message: 'Analyzing project requirements...',
        progress_pct: 10,
      });

      await waitFor(() => {
        expect(screen.getByText('10%')).toBeInTheDocument();
      });

      // Simulate progress at 30%
      simulateWsMessage({
        type: 'prd_generation_progress',
        project_id: 1,
        stage: 'structuring',
        message: 'Structuring document...',
        progress_pct: 30,
      });

      await waitFor(() => {
        expect(screen.getByText('30%')).toBeInTheDocument();
      });

      // Simulate progress at 80%
      simulateWsMessage({
        type: 'prd_generation_progress',
        project_id: 1,
        stage: 'generating',
        message: 'Generating PRD content...',
        progress_pct: 80,
      });

      await waitFor(() => {
        expect(screen.getByText('80%')).toBeInTheDocument();
      });

      // Simulate completion at 100%
      simulateWsMessage({ type: 'prd_generation_completed', project_id: 1 });

      await waitFor(() => {
        expect(screen.getByText(/prd generated successfully/i)).toBeInTheDocument();
      });
    });
  });
});
