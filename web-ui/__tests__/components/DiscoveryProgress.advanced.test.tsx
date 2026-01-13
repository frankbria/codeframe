/**
 * DiscoveryProgress Advanced UI Tests
 *
 * Tests covering advanced UI features:
 * - Minimized view functionality
 * - Auto-minimize after 3 seconds
 * - Expand/minimize button interactions
 * - Next phase indicators
 * - Task Generation Button (Feature 016-3)
 * - WebSocket event handling for task generation
 * - Task state initialization on mount
 * - Idempotent backend response handling
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
  mockGetPRD,
  mockTasksList,
  mockGenerateTasks,
  type DiscoveryProgressResponse,
} from './DiscoveryProgress.testutils';

describe('DiscoveryProgress Advanced UI', () => {
  beforeEach(() => {
    setupMocks();
  });

  afterEach(() => {
    cleanupMocks();
  });

  // ============================================================================
  // Minimized View Tests
  // ============================================================================

  describe('Minimized View', () => {
    it('should auto-minimize section 3 seconds after PRD completion', async () => {
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

      // Simulate PRD completion
      simulateWsMessage({ type: 'prd_generation_completed', project_id: 1 });

      await waitFor(() => {
        expect(screen.getByText(/prd generated successfully/i)).toBeInTheDocument();
      });

      // Advance time by 3 seconds to trigger auto-minimize (wrap in act for React state updates)
      await act(async () => {
        jest.advanceTimersByTime(3000);
      });

      await waitFor(() => {
        expect(screen.getByTestId('prd-minimized-view')).toBeInTheDocument();
      });
    });

    it('should show View PRD button in minimized view', async () => {
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

      // Simulate PRD completion
      simulateWsMessage({ type: 'prd_generation_completed', project_id: 1 });

      await waitFor(() => {
        expect(screen.getByText(/prd generated successfully/i)).toBeInTheDocument();
      });

      // Wait for auto-minimize (wrap in act for React state updates)
      await act(async () => {
        jest.advanceTimersByTime(3000);
      });

      await waitFor(() => {
        expect(screen.getByTestId('prd-minimized-view')).toBeInTheDocument();
      });

      // Click View PRD button in minimized view
      const viewPrdButton = screen.getByTestId('view-prd-button-minimized');
      fireEvent.click(viewPrdButton);

      expect(mockOnViewPRD).toHaveBeenCalled();
    });

    it('should expand minimized view when Expand button is clicked', async () => {
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

      // Simulate PRD completion
      simulateWsMessage({ type: 'prd_generation_completed', project_id: 1 });

      await waitFor(() => {
        expect(screen.getByText(/prd generated successfully/i)).toBeInTheDocument();
      });

      // Wait for auto-minimize (wrap in act for React state updates)
      await act(async () => {
        jest.advanceTimersByTime(3000);
      });

      await waitFor(() => {
        expect(screen.getByTestId('prd-minimized-view')).toBeInTheDocument();
      });

      // Click Expand button
      const expandButton = screen.getByTestId('expand-discovery-button');
      fireEvent.click(expandButton);

      await waitFor(() => {
        // Should no longer be minimized
        expect(screen.queryByTestId('prd-minimized-view')).not.toBeInTheDocument();
        // Full view should be shown
        expect(screen.getByText(/discovery complete/i)).toBeInTheDocument();
      });
    });

    it('should show Minimize button when PRD is complete and not minimized', async () => {
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

      // Simulate PRD completion (but don't wait for auto-minimize)
      simulateWsMessage({ type: 'prd_generation_completed', project_id: 1 });

      await waitFor(() => {
        expect(screen.getByText(/prd generated successfully/i)).toBeInTheDocument();
      });

      // Minimize button should appear
      const minimizeButton = screen.getByTestId('minimize-discovery-button');
      expect(minimizeButton).toBeInTheDocument();

      // Click Minimize button
      fireEvent.click(minimizeButton);

      await waitFor(() => {
        expect(screen.getByTestId('prd-minimized-view')).toBeInTheDocument();
      });
    });
  });

  // ============================================================================
  // Next Phase Indicator Tests
  // ============================================================================

  describe('Next Phase Indicator', () => {
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

      // Simulate PRD completion
      simulateWsMessage({ type: 'prd_generation_completed', project_id: 1 });

      await waitFor(() => {
        expect(screen.getByTestId('task-generation-section')).toBeInTheDocument();
        expect(screen.getByText(/ready for task breakdown/i)).toBeInTheDocument();
      });
    });
  });

  // ============================================================================
  // Task Generation Button Tests (Feature 016-3)
  // ============================================================================

  describe('Task Generation Button', () => {
    const mockPlanningPhaseData: DiscoveryProgressResponse = {
      project_id: 1,
      phase: 'planning',
      discovery: {
        state: 'completed',
        progress_percentage: 100,
        answered_count: 10,
        total_required: 10,
        remaining_count: 0,
      },
    };

    describe('Button Visibility', () => {
      it('should show "Generate Task Breakdown" button when PRD complete and phase is planning', async () => {
        (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: mockPlanningPhaseData });
        mockGetPRD.mockResolvedValue({ data: { status: 'available' } });

        render(<DiscoveryProgress projectId={1} />);

        // Wait for PRD completion state
        await act(async () => {
          simulateWsMessage({ type: 'prd_generation_completed', project_id: 1 });
        });

        await waitFor(() => {
          expect(screen.getByTestId('generate-tasks-button')).toBeInTheDocument();
        });

        expect(screen.getByTestId('generate-tasks-button')).toHaveTextContent('Generate Task Breakdown');
      });

      it('should not show button when PRD is still generating', async () => {
        const discoveringData: DiscoveryProgressResponse = {
          project_id: 1,
          phase: 'discovery',
          discovery: {
            state: 'completed',
            progress_percentage: 100,
            answered_count: 10,
            total_required: 10,
          },
        };

        (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: discoveringData });

        render(<DiscoveryProgress projectId={1} />);

        // Simulate PRD generation in progress (not completed)
        await act(async () => {
          simulateWsMessage({ type: 'prd_generation_started', project_id: 1 });
        });

        await waitFor(() => {
          expect(screen.queryByTestId('generate-tasks-button')).not.toBeInTheDocument();
        });
      });

      it('should not show button when phase is not planning', async () => {
        const activePhaseData: DiscoveryProgressResponse = {
          project_id: 1,
          phase: 'active', // Not planning phase
          discovery: {
            state: 'completed',
            progress_percentage: 100,
            answered_count: 10,
            total_required: 10,
          },
        };

        (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: activePhaseData });
        mockGetPRD.mockResolvedValue({ data: { status: 'available' } });

        render(<DiscoveryProgress projectId={1} />);

        await act(async () => {
          simulateWsMessage({ type: 'prd_generation_completed', project_id: 1 });
        });

        // Should not show generate button when not in planning phase
        await waitFor(() => {
          expect(screen.queryByTestId('generate-tasks-button')).not.toBeInTheDocument();
        });
      });
    });

    describe('Button Click Behavior', () => {
      it('should call generateTasks API when button is clicked', async () => {
        (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: mockPlanningPhaseData });
        mockGetPRD.mockResolvedValue({ data: { status: 'available' } });
        mockGenerateTasks.mockResolvedValue({ data: { success: true } });

        render(<DiscoveryProgress projectId={1} />);

        await act(async () => {
          simulateWsMessage({ type: 'prd_generation_completed', project_id: 1 });
        });

        await waitFor(() => {
          expect(screen.getByTestId('generate-tasks-button')).toBeInTheDocument();
        });

        const button = screen.getByTestId('generate-tasks-button');
        fireEvent.click(button);

        await waitFor(() => {
          expect(mockGenerateTasks).toHaveBeenCalledWith(1);
        });
      });

      it('should show loading state when task generation is in progress', async () => {
        (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: mockPlanningPhaseData });
        mockGetPRD.mockResolvedValue({ data: { status: 'available' } });

        render(<DiscoveryProgress projectId={1} />);

        // Wait for component to load and trigger PRD completion
        // Use advanceTimersByTime to advance just enough for state updates, not the auto-minimize
        await act(async () => {
          simulateWsMessage({ type: 'prd_generation_completed', project_id: 1 });
          jest.advanceTimersByTime(100);
        });

        await waitFor(() => {
          expect(screen.getByTestId('generate-tasks-button')).toBeInTheDocument();
        });

        // Simulate planning started via WebSocket
        await act(async () => {
          simulateWsMessage({ type: 'planning_started', project_id: 1 });
          jest.advanceTimersByTime(100);
        });

        const progressElement = screen.getByTestId('task-generation-progress');
        expect(progressElement).toBeInTheDocument();
        expect(progressElement).toHaveTextContent(/generating tasks/i);
      });

      it('should disable button while generating tasks', async () => {
        (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: mockPlanningPhaseData });
        mockGetPRD.mockResolvedValue({ data: { status: 'available' } });

        render(<DiscoveryProgress projectId={1} />);

        await act(async () => {
          simulateWsMessage({ type: 'prd_generation_completed', project_id: 1 });
        });

        await waitFor(() => {
          expect(screen.getByTestId('generate-tasks-button')).toBeInTheDocument();
        });

        // Start generation
        await act(async () => {
          simulateWsMessage({ type: 'planning_started', project_id: 1 });
        });

        await waitFor(() => {
          const progressElement = screen.getByTestId('task-generation-progress');
          expect(progressElement).toBeInTheDocument();
        });
      });
    });

    describe('WebSocket Event Handling', () => {
      it('should handle planning_started event and show generating state', async () => {
        (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: mockPlanningPhaseData });
        mockGetPRD.mockResolvedValue({ data: { status: 'available' } });

        render(<DiscoveryProgress projectId={1} />);

        await act(async () => {
          simulateWsMessage({ type: 'prd_generation_completed', project_id: 1 });
        });

        await waitFor(() => {
          expect(screen.getByTestId('generate-tasks-button')).toBeInTheDocument();
        });

        // Simulate planning started
        await act(async () => {
          simulateWsMessage({ type: 'planning_started', project_id: 1 });
        });

        await waitFor(() => {
          expect(screen.getByTestId('task-generation-progress')).toBeInTheDocument();
        });
      });

      it('should handle issues_generated event and update progress text', async () => {
        (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: mockPlanningPhaseData });
        mockGetPRD.mockResolvedValue({ data: { status: 'available' } });

        render(<DiscoveryProgress projectId={1} />);

        await act(async () => {
          simulateWsMessage({ type: 'prd_generation_completed', project_id: 1 });
        });

        // Start planning and then send issues_generated
        await act(async () => {
          simulateWsMessage({ type: 'planning_started', project_id: 1 });
          simulateWsMessage({ type: 'issues_generated', project_id: 1, issues_count: 5 });
        });

        await waitFor(() => {
          expect(screen.getByText(/5 issues/i)).toBeInTheDocument();
        });
      });

      it('should handle tasks_decomposed event and update progress text', async () => {
        (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: mockPlanningPhaseData });
        mockGetPRD.mockResolvedValue({ data: { status: 'available' } });

        render(<DiscoveryProgress projectId={1} />);

        await act(async () => {
          simulateWsMessage({ type: 'prd_generation_completed', project_id: 1 });
        });

        // Send sequence of planning events
        await act(async () => {
          simulateWsMessage({ type: 'planning_started', project_id: 1 });
          simulateWsMessage({ type: 'issues_generated', project_id: 1, issues_count: 5 });
          simulateWsMessage({ type: 'tasks_decomposed', project_id: 1, tasks_count: 24 });
        });

        await waitFor(() => {
          expect(screen.getByText(/24 tasks/i)).toBeInTheDocument();
        });
      });

      it('should handle tasks_ready event and show "Review Tasks" button', async () => {
        (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: mockPlanningPhaseData });
        mockGetPRD.mockResolvedValue({ data: { status: 'available' } });

        render(<DiscoveryProgress projectId={1} />);

        await act(async () => {
          simulateWsMessage({ type: 'prd_generation_completed', project_id: 1 });
        });

        // Complete planning sequence
        await act(async () => {
          simulateWsMessage({ type: 'planning_started', project_id: 1 });
          simulateWsMessage({ type: 'issues_generated', project_id: 1, issues_count: 5 });
          simulateWsMessage({ type: 'tasks_decomposed', project_id: 1, tasks_count: 24 });
          simulateWsMessage({ type: 'tasks_ready', project_id: 1 });
        });

        await waitFor(() => {
          expect(screen.getByTestId('review-tasks-button')).toBeInTheDocument();
          expect(screen.getByTestId('review-tasks-button')).toHaveTextContent(/review tasks/i);
        });
      });

      it('should filter events by project_id', async () => {
        (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: mockPlanningPhaseData });
        mockGetPRD.mockResolvedValue({ data: { status: 'available' } });

        render(<DiscoveryProgress projectId={1} />);

        await act(async () => {
          simulateWsMessage({ type: 'prd_generation_completed', project_id: 1 });
        });

        await waitFor(() => {
          expect(screen.getByTestId('generate-tasks-button')).toBeInTheDocument();
        });

        // Send event for different project - should be ignored
        await act(async () => {
          simulateWsMessage({ type: 'planning_started', project_id: 999 });
        });

        // Button should still be visible (not switched to generating state)
        await waitFor(() => {
          expect(screen.getByTestId('generate-tasks-button')).toBeInTheDocument();
        });
      });
    });

    describe('Navigation', () => {
      it('should call onNavigateToTasks when "Review Tasks" button is clicked', async () => {
        const mockNavigateToTasks = jest.fn();
        (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: mockPlanningPhaseData });
        mockGetPRD.mockResolvedValue({ data: { status: 'available' } });

        render(<DiscoveryProgress projectId={1} onNavigateToTasks={mockNavigateToTasks} />);

        await act(async () => {
          simulateWsMessage({ type: 'prd_generation_completed', project_id: 1 });
        });

        // Complete planning sequence
        await act(async () => {
          simulateWsMessage({ type: 'tasks_ready', project_id: 1 });
        });

        await waitFor(() => {
          expect(screen.getByTestId('review-tasks-button')).toBeInTheDocument();
        });

        const reviewButton = screen.getByTestId('review-tasks-button');
        fireEvent.click(reviewButton);

        expect(mockNavigateToTasks).toHaveBeenCalledTimes(1);
      });

      it('should not throw error if onNavigateToTasks is not provided', async () => {
        (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: mockPlanningPhaseData });
        mockGetPRD.mockResolvedValue({ data: { status: 'available' } });

        render(<DiscoveryProgress projectId={1} />);

        await act(async () => {
          simulateWsMessage({ type: 'prd_generation_completed', project_id: 1 });
        });

        await act(async () => {
          simulateWsMessage({ type: 'tasks_ready', project_id: 1 });
        });

        await waitFor(() => {
          expect(screen.getByTestId('review-tasks-button')).toBeInTheDocument();
        });

        // Should not throw when clicked without callback
        const reviewButton = screen.getByTestId('review-tasks-button');
        expect(() => fireEvent.click(reviewButton)).not.toThrow();
      });
    });

    describe('Error Handling', () => {
      it('should show error state when planning_failed event is received', async () => {
        (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: mockPlanningPhaseData });
        mockGetPRD.mockResolvedValue({ data: { status: 'available' } });

        render(<DiscoveryProgress projectId={1} />);

        await act(async () => {
          simulateWsMessage({ type: 'prd_generation_completed', project_id: 1 });
        });

        await waitFor(() => {
          expect(screen.getByTestId('generate-tasks-button')).toBeInTheDocument();
        });

        // Start planning, then fail
        await act(async () => {
          simulateWsMessage({ type: 'planning_started', project_id: 1 });
          simulateWsMessage({
            type: 'planning_failed',
            project_id: 1,
            planning_error: 'Failed to decompose PRD into tasks',
          });
        });

        await waitFor(() => {
          expect(screen.getByTestId('task-generation-error')).toBeInTheDocument();
          expect(screen.getByText(/failed to decompose prd into tasks/i)).toBeInTheDocument();
        });
      });

      it('should show retry button after task generation failure', async () => {
        (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: mockPlanningPhaseData });
        mockGetPRD.mockResolvedValue({ data: { status: 'available' } });

        render(<DiscoveryProgress projectId={1} />);

        await act(async () => {
          simulateWsMessage({ type: 'prd_generation_completed', project_id: 1 });
        });

        // Start and fail planning
        await act(async () => {
          simulateWsMessage({ type: 'planning_started', project_id: 1 });
          simulateWsMessage({
            type: 'planning_failed',
            project_id: 1,
            planning_error: 'API timeout',
          });
        });

        await waitFor(() => {
          expect(screen.getByTestId('retry-task-generation-button')).toBeInTheDocument();
        });
      });

      it('should call generateTasks when retry button is clicked', async () => {
        (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: mockPlanningPhaseData });
        mockGetPRD.mockResolvedValue({ data: { status: 'available' } });
        mockGenerateTasks.mockResolvedValue({ data: { success: true } });

        render(<DiscoveryProgress projectId={1} />);

        await act(async () => {
          simulateWsMessage({ type: 'prd_generation_completed', project_id: 1 });
        });

        // Start and fail planning
        await act(async () => {
          simulateWsMessage({ type: 'planning_started', project_id: 1 });
          simulateWsMessage({
            type: 'planning_failed',
            project_id: 1,
            planning_error: 'API timeout',
          });
        });

        await waitFor(() => {
          expect(screen.getByTestId('retry-task-generation-button')).toBeInTheDocument();
        });

        const retryButton = screen.getByTestId('retry-task-generation-button');
        fireEvent.click(retryButton);

        await waitFor(() => {
          expect(mockGenerateTasks).toHaveBeenCalledWith(1);
        });
      });
    });

    describe('Progress Display', () => {
      it('should show issues count when issues_generated event is received', async () => {
        (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: mockPlanningPhaseData });
        mockGetPRD.mockResolvedValue({ data: { status: 'available' } });

        render(<DiscoveryProgress projectId={1} />);

        await act(async () => {
          simulateWsMessage({ type: 'prd_generation_completed', project_id: 1 });
        });

        await act(async () => {
          simulateWsMessage({ type: 'planning_started', project_id: 1 });
          simulateWsMessage({ type: 'issues_generated', project_id: 1, issues_count: 8 });
        });

        await waitFor(() => {
          expect(screen.getByText(/created 8 issues/i)).toBeInTheDocument();
        });
      });

      it('should show tasks count when tasks_decomposed event is received', async () => {
        (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: mockPlanningPhaseData });
        mockGetPRD.mockResolvedValue({ data: { status: 'available' } });

        render(<DiscoveryProgress projectId={1} />);

        await act(async () => {
          simulateWsMessage({ type: 'prd_generation_completed', project_id: 1 });
        });

        await act(async () => {
          simulateWsMessage({ type: 'planning_started', project_id: 1 });
          simulateWsMessage({ type: 'tasks_decomposed', project_id: 1, tasks_count: 32 });
        });

        await waitFor(() => {
          expect(screen.getByText(/decomposed into 32 tasks/i)).toBeInTheDocument();
        });
      });

      it('should show summary when tasks_ready event is received', async () => {
        (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: mockPlanningPhaseData });
        mockGetPRD.mockResolvedValue({ data: { status: 'available' } });

        render(<DiscoveryProgress projectId={1} />);

        await act(async () => {
          simulateWsMessage({ type: 'prd_generation_completed', project_id: 1 });
        });

        await act(async () => {
          simulateWsMessage({ type: 'planning_started', project_id: 1 });
          simulateWsMessage({ type: 'issues_generated', project_id: 1, issues_count: 6 });
          simulateWsMessage({ type: 'tasks_decomposed', project_id: 1, tasks_count: 18 });
          simulateWsMessage({ type: 'tasks_ready', project_id: 1 });
        });

        await waitFor(() => {
          expect(screen.getByText(/tasks ready for review/i)).toBeInTheDocument();
        });
      });
    });

    describe('Task State Initialization on Mount', () => {
      it('should initialize tasksGenerated to true when tasks already exist on mount', async () => {
        // Arrange: Project is in planning phase with completed PRD and existing tasks
        (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: mockPlanningPhaseData });
        mockGetPRD.mockResolvedValue({ data: { status: 'available' } });
        mockTasksList.mockResolvedValue({ data: { tasks: [{ id: 1, title: 'Task 1' }], total: 1 } });

        // Act
        render(<DiscoveryProgress projectId={1} />);

        // Assert: Button should NOT appear because tasks already exist
        await waitFor(() => {
          expect(screen.queryByTestId('generate-tasks-button')).not.toBeInTheDocument();
        });

        // Verify tasks API was called to check existing tasks
        await waitFor(() => {
          expect(mockTasksList).toHaveBeenCalledWith(1, { limit: 1 });
        });
      });

      it('should show "Tasks Ready" section when tasks exist on mount', async () => {
        // Arrange: Tasks already exist
        (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: mockPlanningPhaseData });
        mockGetPRD.mockResolvedValue({ data: { status: 'available' } });
        mockTasksList.mockResolvedValue({ data: { tasks: [{ id: 1, title: 'Task 1' }], total: 5 } });

        // Act
        render(<DiscoveryProgress projectId={1} />);

        // Assert: Should show "Tasks Ready" section
        await waitFor(() => {
          expect(screen.getByTestId('tasks-ready-section')).toBeInTheDocument();
        });
      });

      it('should show generate button when no tasks exist on mount', async () => {
        // Arrange: PRD completed but no tasks yet
        (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: mockPlanningPhaseData });
        mockGetPRD.mockResolvedValue({ data: { status: 'available' } });
        mockTasksList.mockResolvedValue({ data: { tasks: [], total: 0 } });

        // Act
        render(<DiscoveryProgress projectId={1} />);

        // Assert: Button should appear
        await waitFor(() => {
          expect(screen.getByTestId('generate-tasks-button')).toBeInTheDocument();
        });
      });

      it('should handle tasks fetch failure gracefully without blocking UI', async () => {
        // Arrange: Tasks fetch fails (network error, etc.)
        (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: mockPlanningPhaseData });
        mockGetPRD.mockResolvedValue({ data: { status: 'available' } });
        mockTasksList.mockRejectedValue(new Error('Network error'));

        // Act
        render(<DiscoveryProgress projectId={1} />);

        // Assert: Component should still render and show button (fail-open)
        await waitFor(() => {
          expect(screen.getByTestId('generate-tasks-button')).toBeInTheDocument();
        });
      });
    });

    describe('Idempotent Backend Response Handling', () => {
      it('should handle tasks_already_exist response and show tasks ready section', async () => {
        // Arrange: Button is shown (tasks check failed or returned empty initially)
        (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: mockPlanningPhaseData });
        mockGetPRD.mockResolvedValue({ data: { status: 'available' } });
        mockTasksList.mockResolvedValue({ data: { tasks: [], total: 0 } }); // Initially no tasks

        // Backend returns idempotent response
        mockGenerateTasks.mockResolvedValue({
          data: {
            success: true,
            message: 'Tasks have already been generated for this project.',
            tasks_already_exist: true,
          },
        });

        // Act
        render(<DiscoveryProgress projectId={1} />);

        await waitFor(() => {
          expect(screen.getByTestId('generate-tasks-button')).toBeInTheDocument();
        });

        // Click the button
        const button = screen.getByTestId('generate-tasks-button');
        fireEvent.click(button);

        // Assert: Should transition to "tasks ready" state
        await waitFor(() => {
          expect(screen.getByTestId('tasks-ready-section')).toBeInTheDocument();
        });
      });

      it('should not show error when tasks_already_exist is returned', async () => {
        // Arrange
        (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: mockPlanningPhaseData });
        mockGetPRD.mockResolvedValue({ data: { status: 'available' } });
        mockTasksList.mockResolvedValue({ data: { tasks: [], total: 0 } });

        mockGenerateTasks.mockResolvedValue({
          data: {
            success: true,
            message: 'Tasks have already been generated for this project.',
            tasks_already_exist: true,
          },
        });

        // Act
        render(<DiscoveryProgress projectId={1} />);

        await waitFor(() => {
          expect(screen.getByTestId('generate-tasks-button')).toBeInTheDocument();
        });

        fireEvent.click(screen.getByTestId('generate-tasks-button'));

        // Assert: No error section should appear
        await waitFor(() => {
          expect(screen.queryByTestId('task-generation-error')).not.toBeInTheDocument();
        });
      });
    });
  });
});
