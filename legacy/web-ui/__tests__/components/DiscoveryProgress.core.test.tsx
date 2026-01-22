/**
 * DiscoveryProgress Core Functionality Tests
 * 
 * Tests covering:
 * - Data fetching and error handling
 * - Loading states
 * - Phase display (discovery/planning/active/review/complete)
 * - Discovery states (discovering/completed/idle)
 * - ProgressBar integration
 * - Question display and counters
 * - Start Discovery button functionality
 * - Auto-refresh logic (10s intervals)
 * - Accessibility (ARIA labels)
 * - Responsive design
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
  mockStartProject,
  type DiscoveryProgressResponse,
} from './DiscoveryProgress.testutils';

describe('DiscoveryProgress Core Functionality', () => {
  beforeEach(() => {
    setupMocks();
  });

  afterEach(() => {
    cleanupMocks();
  });

  describe('Data Fetching', () => {
    it('should fetch discovery progress on mount', async () => {
      const mockData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'discovery',
        discovery: {
          state: 'discovering',
          progress_percentage: 50,
          answered_count: 5,
          total_required: 10,
          remaining_count: 5,
        },
      };

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: mockData });

      render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        expect(projectsApi.getDiscoveryProgress).toHaveBeenCalledWith(1);
      });
    });

    it('should handle API errors gracefully', async () => {
      (projectsApi.getDiscoveryProgress as jest.Mock).mockRejectedValue(
        new Error('API Error')
      );

      render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        expect(screen.getByText(/failed to load discovery progress/i)).toBeInTheDocument();
      });
    });
  });

  describe('Loading State', () => {
    it('should display loading indicator while fetching', () => {
      (projectsApi.getDiscoveryProgress as jest.Mock).mockImplementation(
        () => new Promise(() => {}) // Never resolves
      );

      render(<DiscoveryProgress projectId={1} />);

      expect(screen.getByText(/loading/i)).toBeInTheDocument();
    });
  });

  describe('Phase Display', () => {
    it('should display PhaseIndicator with current phase', async () => {
      const mockData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'planning',
        discovery: null,
      };

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: mockData });

      render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        const phaseIndicator = screen.getByTestId('mock-phase-indicator');
        expect(phaseIndicator).toHaveTextContent('planning');
      });
    });

    it('should display PhaseIndicator for all phases', async () => {
      const phases: Array<'discovery' | 'planning' | 'active' | 'review' | 'complete'> = [
        'discovery',
        'planning',
        'active',
        'review',
        'complete',
      ];

      for (const phase of phases) {
        const mockData: DiscoveryProgressResponse = {
          project_id: 1,
          phase,
          discovery: null,
        };

        (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: mockData });

        const { unmount } = render(<DiscoveryProgress projectId={1} />);

        await waitFor(() => {
          const phaseIndicator = screen.getByTestId('mock-phase-indicator');
          expect(phaseIndicator).toHaveTextContent(phase);
        });

        unmount();
      }
    });
  });

  describe('Discovery State - Discovering', () => {
    it('should show ProgressBar when in discovering state', async () => {
      const mockData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'discovery',
        discovery: {
          state: 'discovering',
          progress_percentage: 60,
          answered_count: 6,
          total_required: 10,
          remaining_count: 4,
        },
      };

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: mockData });

      render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        expect(screen.getByTestId('mock-progress-bar')).toBeInTheDocument();
        expect(screen.getByText('60%')).toBeInTheDocument();
      });
    });

    it('should display current question when available', async () => {
      const mockData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'discovery',
        discovery: {
          state: 'discovering',
          progress_percentage: 40,
          answered_count: 4,
          total_required: 10,
          current_question: {
            id: 'q1',
            question: 'What is the primary goal of this project?',
            category: 'goals',
          },
        },
      };

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: mockData });

      render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        expect(
          screen.getByText(/what is the primary goal of this project/i)
        ).toBeInTheDocument();
      });
    });

    it('should display answered count and total', async () => {
      const mockData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'discovery',
        discovery: {
          state: 'discovering',
          progress_percentage: 70,
          answered_count: 7,
          total_required: 10,
          remaining_count: 3,
        },
      };

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: mockData });

      render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        expect(screen.getByText(/7.*10/)).toBeInTheDocument();
      });
    });
  });

  describe('Discovery State - Completed', () => {
    it('should show "Discovery Complete" message when completed', async () => {
      const mockData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'planning',
        discovery: {
          state: 'completed',
          progress_percentage: 100,
          answered_count: 10,
          total_required: 10,
        },
      };

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: mockData });

      render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        expect(screen.getByText(/discovery complete/i)).toBeInTheDocument();
      });
    });

    it('should not show ProgressBar when completed', async () => {
      const mockData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'planning',
        discovery: {
          state: 'completed',
          progress_percentage: 100,
          answered_count: 10,
          total_required: 10,
        },
      };

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: mockData });

      render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        expect(screen.getByText(/discovery complete/i)).toBeInTheDocument();
      });

      expect(screen.queryByTestId('mock-progress-bar')).not.toBeInTheDocument();
    });
  });

  describe('Discovery State - Idle', () => {
    it('should show "Not started" message when idle', async () => {
      const mockData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'discovery',
        discovery: {
          state: 'idle',
          progress_percentage: 0,
          answered_count: 0,
          total_required: 10,
        },
      };

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: mockData });

      render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        expect(screen.getByText(/not started/i)).toBeInTheDocument();
      });
    });

    it('should show "Not started" when discovery is null', async () => {
      const mockData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'active',
        discovery: null,
      };

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: mockData });

      render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        expect(screen.getByText(/not started/i)).toBeInTheDocument();
      });
    });
  });

  describe('Start Discovery Button', () => {
    it('should show Start Discovery button when idle', async () => {
      const mockData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'discovery',
        discovery: {
          state: 'idle',
          progress_percentage: 0,
          answered_count: 0,
          total_required: 10,
        },
      };

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: mockData });

      render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        const button = screen.getByTestId('start-discovery-button');
        expect(button).toBeInTheDocument();
        expect(button).toHaveTextContent('Start Discovery');
      });
    });

    it('should call startProject when button is clicked', async () => {
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

      mockStartProject.mockResolvedValueOnce({ data: { status: 'starting' } });

      render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        expect(screen.getByTestId('start-discovery-button')).toBeInTheDocument();
      });

      const button = screen.getByTestId('start-discovery-button');
      fireEvent.click(button);

      await waitFor(() => {
        expect(mockStartProject).toHaveBeenCalledWith(1);
      });
    });

    it('should show loading state while starting', async () => {
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

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: idleData });

      // Make startProject never resolve to test loading state
      mockStartProject.mockImplementation(() => new Promise(() => {}));

      render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        expect(screen.getByTestId('start-discovery-button')).toBeInTheDocument();
      });

      const button = screen.getByTestId('start-discovery-button');
      fireEvent.click(button);

      await waitFor(() => {
        expect(button).toHaveTextContent('Starting...');
        expect(button).toBeDisabled();
      });
    });

    it('should show error message when startProject fails', async () => {
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

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: idleData });
      mockStartProject.mockRejectedValueOnce(new Error('Failed to start'));

      render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        expect(screen.getByTestId('start-discovery-button')).toBeInTheDocument();
      });

      const button = screen.getByTestId('start-discovery-button');
      fireEvent.click(button);

      await waitFor(() => {
        expect(screen.getByRole('alert')).toHaveTextContent(/failed to start discovery/i);
      });
    });

    it('should handle "already running" response gracefully', async () => {
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

      // Mock startProject to return "already running" response (not an error)
      mockStartProject.mockResolvedValueOnce({ data: { status: 'running', message: 'Already running' } });

      render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        expect(screen.getByTestId('start-discovery-button')).toBeInTheDocument();
      });

      const button = screen.getByTestId('start-discovery-button');
      fireEvent.click(button);

      // Should not show error since it's not actually an error
      await waitFor(() => {
        expect(mockStartProject).toHaveBeenCalledWith(1);
      });

      // Wait for the 2 second fallback refresh timeout to happen
      jest.advanceTimersByTime(2000);

      // Should still try to refresh and transition
      await waitFor(() => {
        expect(projectsApi.getDiscoveryProgress).toHaveBeenCalledTimes(2);
      });
    });

    it('should transition to discovering state after successful start', async () => {
      // Use real timers for this test since it involves complex async interactions
      jest.useRealTimers();

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

      mockStartProject.mockResolvedValueOnce({ data: { status: 'starting' } });

      render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        expect(screen.getByTestId('start-discovery-button')).toBeInTheDocument();
      });

      const button = screen.getByTestId('start-discovery-button');
      fireEvent.click(button);

      // Wait for the transition to complete (includes 1s delay + API call)
      await waitFor(() => {
        // Button should be gone (no longer idle)
        expect(screen.queryByTestId('start-discovery-button')).not.toBeInTheDocument();
        // First question should appear
        expect(screen.getByText(/what is your project about/i)).toBeInTheDocument();
      }, { timeout: 3000 });

      // Restore fake timers for other tests
      jest.useFakeTimers();
    });
  });

  describe('Auto-refresh', () => {
    it('should auto-refresh every 10 seconds during discovery', async () => {
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

      // Wait for initial fetch and data to be set (which triggers interval setup)
      await waitFor(() => {
        expect(screen.getByText(/answered/i)).toBeInTheDocument();
      });

      expect(projectsApi.getDiscoveryProgress).toHaveBeenCalledTimes(1);

      // Advance 10 seconds
      jest.advanceTimersByTime(10000);

      await waitFor(() => {
        expect(projectsApi.getDiscoveryProgress).toHaveBeenCalledTimes(2);
      });

      // Advance another 10 seconds
      jest.advanceTimersByTime(10000);

      await waitFor(() => {
        expect(projectsApi.getDiscoveryProgress).toHaveBeenCalledTimes(3);
      });
    });

    it('should not auto-refresh when discovery is completed', async () => {
      const mockData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'planning',
        discovery: {
          state: 'completed',
          progress_percentage: 100,
          answered_count: 10,
          total_required: 10,
        },
      };

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: mockData });

      render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        expect(projectsApi.getDiscoveryProgress).toHaveBeenCalledTimes(1);
      });

      // Advance 30 seconds
      jest.advanceTimersByTime(30000);

      // Should still be 1 call (no refresh)
      expect(projectsApi.getDiscoveryProgress).toHaveBeenCalledTimes(1);
    });

    it('should not auto-refresh when discovery is idle', async () => {
      const mockData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'discovery',
        discovery: {
          state: 'idle',
          progress_percentage: 0,
          answered_count: 0,
          total_required: 10,
        },
      };

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: mockData });

      render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        expect(projectsApi.getDiscoveryProgress).toHaveBeenCalledTimes(1);
      });

      // Advance 30 seconds
      jest.advanceTimersByTime(30000);

      // Should still be 1 call (no refresh)
      expect(projectsApi.getDiscoveryProgress).toHaveBeenCalledTimes(1);
    });

    it('should cleanup timer on unmount', async () => {
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

      const { unmount } = render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        expect(projectsApi.getDiscoveryProgress).toHaveBeenCalledTimes(1);
      });

      unmount();

      // Advance time after unmount
      jest.advanceTimersByTime(30000);

      // Should still be 1 call (timer cleaned up)
      expect(projectsApi.getDiscoveryProgress).toHaveBeenCalledTimes(1);
    });
  });

  describe('Accessibility', () => {
    it('should have proper ARIA labels', async () => {
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
        const section = screen.getByRole('region', { name: /discovery progress/i });
        expect(section).toBeInTheDocument();
      });
    });
  });

  describe('Responsive Design', () => {
    it('should render in a responsive container', async () => {
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

      const { container } = render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        const mainContainer = container.firstChild as HTMLElement;
        expect(mainContainer).toHaveClass('w-full');
      });
    });
  });
});
