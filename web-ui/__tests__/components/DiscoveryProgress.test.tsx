/**
 * Tests for DiscoveryProgress Component (cf-17.2)
 * Migrated from src/components/__tests__/DiscoveryProgress.test.tsx
 */

import { render, screen, waitFor, fireEvent, act } from '@testing-library/react';
import DiscoveryProgress from '@/components/DiscoveryProgress';
import { projectsApi, tasksApi } from '@/lib/api';
import type { DiscoveryProgressResponse } from '@/types/api';

// Mock Hugeicons
jest.mock('@hugeicons/react', () => ({
  Cancel01Icon: ({ className }: { className?: string }) => <span className={className} data-testid="cancel-icon" />,
  CheckmarkCircle01Icon: ({ className }: { className?: string }) => <span className={className} data-testid="checkmark-icon" />,
  Alert02Icon: ({ className }: { className?: string }) => <span className={className} data-testid="alert-icon" />,
}));

// Mock the API
const mockStartProject = jest.fn();
const mockRestartDiscovery = jest.fn();
const mockRetryPrdGeneration = jest.fn();
const mockGenerateTasks = jest.fn();
const mockGetPRD = jest.fn();
const mockTasksList = jest.fn();
jest.mock('@/lib/api', () => ({
  projectsApi: {
    getDiscoveryProgress: jest.fn(),
    startProject: (...args: unknown[]) => mockStartProject(...args),
    restartDiscovery: (...args: unknown[]) => mockRestartDiscovery(...args),
    retryPrdGeneration: (...args: unknown[]) => mockRetryPrdGeneration(...args),
    generateTasks: (...args: unknown[]) => mockGenerateTasks(...args),
    getPRD: (...args: unknown[]) => mockGetPRD(...args),
  },
  tasksApi: {
    list: (...args: unknown[]) => mockTasksList(...args),
  },
}));

// Mock WebSocket client
type MessageHandler = (message: Record<string, unknown>) => void;
const mockMessageHandlers: MessageHandler[] = [];
const mockWsClient = {
  onMessage: jest.fn((handler: MessageHandler) => {
    mockMessageHandlers.push(handler);
    return () => {
      const index = mockMessageHandlers.indexOf(handler);
      if (index > -1) mockMessageHandlers.splice(index, 1);
    };
  }),
  connect: jest.fn(),
  disconnect: jest.fn(),
  subscribe: jest.fn(),
};

// Helper to simulate WebSocket messages
const simulateWsMessage = (message: Record<string, unknown>) => {
  mockMessageHandlers.forEach(handler => handler(message));
};

jest.mock('@/lib/websocket', () => ({
  getWebSocketClient: () => mockWsClient,
}));

// Mock the authenticated fetch
jest.mock('@/lib/api-client', () => ({
  authFetch: jest.fn(),
}));

import { authFetch } from '@/lib/api-client';
const mockAuthFetch = authFetch as jest.MockedFunction<typeof authFetch>;

// Mock child components
jest.mock('@/components/ProgressBar', () => {
  return function MockProgressBar({ percentage, label }: { percentage: number; label?: string }) {
    return (
      <div data-testid="mock-progress-bar">
        {label && <span>{label}</span>}
        <span>{percentage}%</span>
      </div>
    );
  };
});

jest.mock('@/components/PhaseIndicator', () => {
  return function MockPhaseIndicator({ phase }: { phase: string }) {
    return <span data-testid="mock-phase-indicator">{phase}</span>;
  };
});

describe('DiscoveryProgress Component', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    jest.useFakeTimers();
    mockAuthFetch.mockReset();
    mockStartProject.mockReset();
    mockRestartDiscovery.mockReset();
    mockRetryPrdGeneration.mockReset();
    mockGenerateTasks.mockReset();
    mockGetPRD.mockReset();
    mockTasksList.mockReset();
    // Clear WebSocket message handlers
    mockMessageHandlers.length = 0;
  });

  afterEach(() => {
    jest.runOnlyPendingTimers();
    jest.useRealTimers();
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
      // This tests the case where backend returns "already running" but discovery started
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

  // ============================================================================
  // Feature: 012-discovery-answer-ui - TDD Tests
  // ============================================================================

  describe('Answer Input (US1)', () => {
    it('should render answer textarea with correct attributes', async () => {
      const mockData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'discovery',
        discovery: {
          state: 'discovering',
          progress_percentage: 10,
          answered_count: 2,
          total_required: 20,
          current_question: {
            id: 'q1',
            category: 'problem',
            question: 'What problem does your project solve?',
          },
        },
      };

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: mockData });

      render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        const textarea = screen.getByPlaceholderText(/type your answer here/i);
        expect(textarea).toBeInTheDocument();
        expect(textarea).toHaveAttribute('maxLength', '5000');
        expect(textarea).toHaveAttribute('rows', '6');
        expect(textarea).toHaveClass('resize-none');
        expect(textarea).toHaveClass('w-full');
      });
    });
  });

  // ============================================================================
  // Feature: 012-discovery-answer-ui - Phase 4: User Story 2 (Character Counter)
  // ============================================================================

  describe('Character Counter (US2)', () => {
    it('should display character counter that updates as user types (T018)', async () => {
      const mockData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'discovery',
        discovery: {
          state: 'discovering',
          progress_percentage: 10,
          answered_count: 2,
          total_required: 20,
          current_question: {
            id: 'q1',
            category: 'problem',
            question: 'What problem does your project solve?',
          },
        },
      };

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: mockData });

      const { rerender: _rerender } = render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        expect(screen.getByPlaceholderText(/type your answer here/i)).toBeInTheDocument();
      });

      // Should show initial counter: 0 / 5000 characters
      expect(screen.getByText(/0 \/ 5000 characters/i)).toBeInTheDocument();

      // Counter should have default color (muted)
      const counter = screen.getByText(/0 \/ 5000 characters/i);
      expect(counter).toHaveClass('text-muted-foreground');
      expect(counter).toHaveClass('text-sm');

      // Type some text in textarea
      const textarea = screen.getByPlaceholderText(/type your answer here/i) as HTMLTextAreaElement;
      const testAnswer = 'This is a test answer';

      // Simulate typing
      fireEvent.change(textarea, { target: { value: testAnswer } });

      // Counter should update to show character count
      expect(screen.getByText(new RegExp(`${testAnswer.length} / 5000 characters`, 'i'))).toBeInTheDocument();

      // Type more to exceed 4500 characters (warning threshold)
      const longAnswer = 'a'.repeat(4501);
      fireEvent.change(textarea, { target: { value: longAnswer } });

      // Counter should turn red when > 4500 characters
      const warningCounter = screen.getByText(/4501 \/ 5000 characters/i);
      expect(warningCounter).toHaveClass('text-destructive');
      expect(warningCounter).not.toHaveClass('text-muted-foreground');
    });
  });

  // ============================================================================
  // Feature: 012-discovery-answer-ui - Phase 5: User Story 3 (Submit Button)
  // ============================================================================

  describe('Submit Button (US3)', () => {
    it('should disable submit button when answer is empty (T023)', async () => {
      const mockData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'discovery',
        discovery: {
          state: 'discovering',
          progress_percentage: 10,
          answered_count: 2,
          total_required: 20,
          current_question: {
            id: 'q1',
            category: 'problem',
            question: 'What problem does your project solve?',
          },
        },
      };

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: mockData });

      render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        expect(screen.getByPlaceholderText(/type your answer here/i)).toBeInTheDocument();
      });

      // Submit button should exist
      const submitButton = screen.getByRole('button', { name: /submit answer/i });
      expect(submitButton).toBeInTheDocument();

      // Should be disabled when answer is empty
      expect(submitButton).toBeDisabled();

      // Type whitespace-only answer
      const textarea = screen.getByPlaceholderText(/type your answer here/i) as HTMLTextAreaElement;
      fireEvent.change(textarea, { target: { value: '   ' } });

      // Should still be disabled (whitespace-only)
      expect(submitButton).toBeDisabled();

      // Type valid answer
      fireEvent.change(textarea, { target: { value: 'Valid answer' } });

      // Should now be enabled
      expect(submitButton).not.toBeDisabled();
    });

    it('should disable submit button during submission (T024)', async () => {
      const mockData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'discovery',
        discovery: {
          state: 'discovering',
          progress_percentage: 10,
          answered_count: 2,
          total_required: 20,
          current_question: {
            id: 'q1',
            category: 'problem',
            question: 'What problem does your project solve?',
          },
        },
      };

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: mockData });

      render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        expect(screen.getByPlaceholderText(/type your answer here/i)).toBeInTheDocument();
      });

      // Type valid answer
      const textarea = screen.getByPlaceholderText(/type your answer here/i) as HTMLTextAreaElement;
      fireEvent.change(textarea, { target: { value: 'Valid answer' } });

      // Get submit button
      const submitButton = screen.getByRole('button', { name: /submit answer/i });
      expect(submitButton).not.toBeDisabled();

      // Note: Full submission flow will be tested when API integration is complete
      // This test verifies the button can be enabled/disabled based on state
    });
  });

  // ============================================================================
  // Feature: 012-discovery-answer-ui - Phase 7: User Story 4 (Keyboard Shortcut)
  // ============================================================================

  describe('Keyboard Shortcut (US4)', () => {
    it('should trigger submit when Ctrl+Enter is pressed (T046)', async () => {
      const mockData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'discovery',
        discovery: {
          state: 'discovering',
          progress_percentage: 10,
          answered_count: 2,
          total_required: 20,
          current_question: {
            id: 'q1',
            category: 'problem',
            question: 'What problem does your project solve?',
          },
        },
      };

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: mockData });

      // Mock authFetch for the submit API call
      mockAuthFetch.mockResolvedValueOnce({
        success: true,
        next_question: 'Next question',
        is_complete: false,
        current_index: 3,
        total_questions: 20,
        progress_percentage: 15.0,
      });

      render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        expect(screen.getByPlaceholderText(/type your answer here/i)).toBeInTheDocument();
      });

      // Type valid answer
      const textarea = screen.getByPlaceholderText(/type your answer here/i) as HTMLTextAreaElement;
      fireEvent.change(textarea, { target: { value: 'Valid answer for keyboard shortcut test' } });

      // Press Ctrl+Enter
      fireEvent.keyDown(textarea, {
        key: 'Enter',
        ctrlKey: true,
        code: 'Enter',
        charCode: 13,
      });

      // Verify authFetch was called (submission triggered)
      await waitFor(() => {
        expect(mockAuthFetch).toHaveBeenCalledWith(
          expect.stringContaining('/api/projects/1/discovery/answer'),
          {
            method: 'POST',
            body: { answer: 'Valid answer for keyboard shortcut test' },
          }
        );
      });

      // Should NOT submit with Enter alone (without Ctrl)
      fireEvent.change(textarea, { target: { value: 'Another answer' } });
      mockAuthFetch.mockClear();

      fireEvent.keyDown(textarea, {
        key: 'Enter',
        ctrlKey: false,
        code: 'Enter',
        charCode: 13,
      });

      // Fetch should NOT be called (no submission)
      expect(mockAuthFetch).not.toHaveBeenCalled();
    });

    it('should not submit with Ctrl+Enter if answer is empty', async () => {
      const mockData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'discovery',
        discovery: {
          state: 'discovering',
          progress_percentage: 10,
          answered_count: 2,
          total_required: 20,
          current_question: {
            id: 'q1',
            category: 'problem',
            question: 'What problem does your project solve?',
          },
        },
      };

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: mockData });

      // No API call expected for this test

      render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        expect(screen.getByPlaceholderText(/type your answer here/i)).toBeInTheDocument();
      });

      const textarea = screen.getByPlaceholderText(/type your answer here/i) as HTMLTextAreaElement;

      // Press Ctrl+Enter without typing anything
      fireEvent.keyDown(textarea, {
        key: 'Enter',
        ctrlKey: true,
        code: 'Enter',
        charCode: 13,
      });

      // Fetch should NOT be called (empty answer)
      expect(mockAuthFetch).not.toHaveBeenCalled();
    });
  });

  // ============================================================================
  // Feature: 012-discovery-answer-ui - Phase 8: User Story 6 (Success Message)
  // ============================================================================

  describe('Success Message (US6)', () => {
    it('should display success message after successful submit (T052)', async () => {
      const mockData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'discovery',
        discovery: {
          state: 'discovering',
          progress_percentage: 10,
          answered_count: 2,
          total_required: 20,
          current_question: {
            id: 'q1',
            category: 'problem',
            question: 'What problem does your project solve?',
          },
        },
      };

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: mockData });

      // Mock successful submit response
      mockAuthFetch.mockResolvedValueOnce({
        success: true,
        next_question: 'What tech stack are you planning to use?',
        is_complete: false,
        current_index: 3,
        total_questions: 20,
        progress_percentage: 15.0,
      });

      render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        expect(screen.getByPlaceholderText(/type your answer here/i)).toBeInTheDocument();
      });

      // Type valid answer
      const textarea = screen.getByPlaceholderText(/type your answer here/i) as HTMLTextAreaElement;
      fireEvent.change(textarea, { target: { value: 'A valid answer' } });

      // Click submit button
      const submitButton = screen.getByRole('button', { name: /submit answer/i });
      fireEvent.click(submitButton);

      // Success message should appear
      await waitFor(() => {
        const successMessage = screen.getByText(/answer submitted.*loading next question/i);
        expect(successMessage).toBeInTheDocument();

        // Verify success message styling (message div has all the classes)
        // Using semantic color tokens: bg-success/10, border-success, text-success
        expect(successMessage).toHaveClass('bg-success/10');
        expect(successMessage).toHaveClass('border-success');
        expect(successMessage).toHaveClass('text-success');
        expect(successMessage).toHaveClass('p-3');
        expect(successMessage).toHaveClass('rounded-lg');
      });

      // Success message should auto-dismiss after 1 second
      jest.advanceTimersByTime(1000);

      await waitFor(() => {
        expect(screen.queryByText(/answer submitted.*loading next question/i)).not.toBeInTheDocument();
      });
    });

    it('should not show success message on API error', async () => {
      const mockData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'discovery',
        discovery: {
          state: 'discovering',
          progress_percentage: 10,
          answered_count: 2,
          total_required: 20,
          current_question: {
            id: 'q1',
            category: 'problem',
            question: 'What problem does your project solve?',
          },
        },
      };

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: mockData });

      // Mock failed submit response
      mockAuthFetch.mockRejectedValueOnce(
        new Error('Request failed: 400 Answer must be between 1 and 5000 characters')
      );

      render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        expect(screen.getByPlaceholderText(/type your answer here/i)).toBeInTheDocument();
      });

      // Type valid answer
      const textarea = screen.getByPlaceholderText(/type your answer here/i) as HTMLTextAreaElement;
      fireEvent.change(textarea, { target: { value: 'A valid answer' } });

      // Click submit button
      const submitButton = screen.getByRole('button', { name: /submit answer/i });
      fireEvent.click(submitButton);

      // Wait for error handling
      await waitFor(() => {
        expect(mockAuthFetch).toHaveBeenCalled();
      });

      // Success message should NOT appear
      expect(screen.queryByText(/answer submitted.*loading next question/i)).not.toBeInTheDocument();

      // Error message should appear instead (will be tested in US7)
    });
  });

  // ============================================================================
  // Feature: 012-discovery-answer-ui - Phase 9: User Story 7 (Error Handling)
  // ============================================================================

  describe('Error Handling (US7)', () => {
    it('should show validation error for empty answer (T057)', async () => {
      const mockData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'discovery',
        discovery: {
          state: 'discovering',
          progress_percentage: 10,
          answered_count: 2,
          total_required: 20,
          current_question: {
            id: 'q1',
            category: 'problem',
            question: 'What problem does your project solve?',
          },
        },
      };

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: mockData });

      render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        expect(screen.getByPlaceholderText(/type your answer here/i)).toBeInTheDocument();
      });

      // Try to submit empty answer
      const submitButton = screen.getByRole('button', { name: /submit answer/i });

      // Button should be disabled, but let's test the validation logic by typing and deleting
      const textarea = screen.getByPlaceholderText(/type your answer here/i) as HTMLTextAreaElement;
      fireEvent.change(textarea, { target: { value: '   ' } }); // Whitespace only

      // Button is still disabled, so we can't click it
      expect(submitButton).toBeDisabled();

      // No error should show yet (validation happens on submit, not on input)
      expect(screen.queryByText(/answer must be between 1 and 5000 characters/i)).not.toBeInTheDocument();
    });

    it('should show validation error for answer > 5000 chars (T058)', async () => {
      const mockData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'discovery',
        discovery: {
          state: 'discovering',
          progress_percentage: 10,
          answered_count: 2,
          total_required: 20,
          current_question: {
            id: 'q1',
            category: 'problem',
            question: 'What problem does your project solve?',
          },
        },
      };

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: mockData });

      render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        expect(screen.getByPlaceholderText(/type your answer here/i)).toBeInTheDocument();
      });

      // Type answer that's too long (textarea has maxLength=5000, so we need to simulate programmatically)
      const textarea = screen.getByPlaceholderText(/type your answer here/i) as HTMLTextAreaElement;
      const longAnswer = 'a'.repeat(5001);

      // Manually set value to bypass maxLength (to test validation logic)
      Object.defineProperty(textarea, 'value', {
        writable: true,
        value: longAnswer,
      });

      // Trigger onChange manually
      fireEvent.change(textarea, { target: { value: longAnswer } });

      // Click submit button (should be enabled because trimmed length > 0)
      const submitButton = screen.getByRole('button', { name: /submit answer/i });
      fireEvent.click(submitButton);

      // Validation error should appear
      await waitFor(() => {
        const errorMessage = screen.getByText(/answer must be between 1 and 5000 characters/i);
        expect(errorMessage).toBeInTheDocument();

        // Verify error message styling
        expect(errorMessage).toHaveClass('bg-destructive/10');
        expect(errorMessage).toHaveClass('border-destructive');
        expect(errorMessage).toHaveClass('text-destructive');
        expect(errorMessage).toHaveClass('p-3');
        expect(errorMessage).toHaveClass('rounded-lg');
      });

      // Textarea should have red border
      expect(textarea).toHaveClass('border-destructive');

      // Answer should be preserved (not cleared)
      expect(textarea.value).toBe(longAnswer);
    });

    it('should show error message on API failure (T059)', async () => {
      const mockData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'discovery',
        discovery: {
          state: 'discovering',
          progress_percentage: 10,
          answered_count: 2,
          total_required: 20,
          current_question: {
            id: 'q1',
            category: 'problem',
            question: 'What problem does your project solve?',
          },
        },
      };

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: mockData });

      // Mock API error response
      mockAuthFetch.mockRejectedValueOnce(
        new Error('Request failed: 400 Project is not in discovery phase')
      );

      render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        expect(screen.getByPlaceholderText(/type your answer here/i)).toBeInTheDocument();
      });

      // Type valid answer
      const textarea = screen.getByPlaceholderText(/type your answer here/i) as HTMLTextAreaElement;
      fireEvent.change(textarea, { target: { value: 'A valid answer' } });

      // Click submit button
      const submitButton = screen.getByRole('button', { name: /submit answer/i });
      fireEvent.click(submitButton);

      // API error message should appear
      await waitFor(() => {
        const errorMessage = screen.getByText(/project is not in discovery phase/i);
        expect(errorMessage).toBeInTheDocument();

        // Verify error message styling
        expect(errorMessage).toHaveClass('bg-destructive/10');
        expect(errorMessage).toHaveClass('border-destructive');
        expect(errorMessage).toHaveClass('text-destructive');
        expect(errorMessage).toHaveClass('p-3');
        expect(errorMessage).toHaveClass('rounded-lg');
      });

      // Textarea should have red border
      expect(textarea).toHaveClass('border-destructive');

      // Answer should be preserved (not cleared)
      expect(textarea.value).toBe('A valid answer');
    });

    it('should show network error message on fetch failure', async () => {
      const mockData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'discovery',
        discovery: {
          state: 'discovering',
          progress_percentage: 10,
          answered_count: 2,
          total_required: 20,
          current_question: {
            id: 'q1',
            category: 'problem',
            question: 'What problem does your project solve?',
          },
        },
      };

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: mockData });

      // Mock network error
      mockAuthFetch.mockRejectedValueOnce(new Error('Network error'));

      render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        expect(screen.getByPlaceholderText(/type your answer here/i)).toBeInTheDocument();
      });

      // Type valid answer
      const textarea = screen.getByPlaceholderText(/type your answer here/i) as HTMLTextAreaElement;
      fireEvent.change(textarea, { target: { value: 'A valid answer' } });

      // Click submit button
      const submitButton = screen.getByRole('button', { name: /submit answer/i });
      fireEvent.click(submitButton);

      // Network error message should appear
      await waitFor(() => {
        const errorMessage = screen.getByText(/network error/i);
        expect(errorMessage).toBeInTheDocument();
      });

      // Answer should be preserved
      expect(textarea.value).toBe('A valid answer');
    });
  });

  // ============================================================================
  // Feature: 012-discovery-answer-ui - Phase 10: User Story 8 (Progress Bar Update)
  // ============================================================================

  describe('Progress Bar Update (US8)', () => {
    it('should update progress bar after successful submit (T066)', async () => {
      // Initial state: 2 of 20 answered (10%)
      const initialData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'discovery',
        discovery: {
          state: 'discovering',
          progress_percentage: 10,
          answered_count: 2,
          total_required: 20,
          current_question: {
            id: 'q1',
            category: 'problem',
            question: 'What problem does your project solve?',
          },
        },
      };

      // Updated state after answer: 3 of 20 answered (15%)
      const updatedData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'discovery',
        discovery: {
          state: 'discovering',
          progress_percentage: 15,
          answered_count: 3,
          total_required: 20,
          current_question: {
            id: 'q2',
            category: 'tech_stack',
            question: 'What tech stack are you planning to use?',
          },
        },
      };

      // Mock initial fetch
      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValueOnce({ data: initialData });

      // Mock successful submit response
      mockAuthFetch.mockResolvedValueOnce({
        success: true,
        next_question: 'What tech stack are you planning to use?',
        is_complete: false,
        current_index: 3,
        total_questions: 20,
        progress_percentage: 15.0,
      });

      render(<DiscoveryProgress projectId={1} />);

      // Wait for initial load
      await waitFor(() => {
        expect(screen.getByText(/answered.*2.*20/i)).toBeInTheDocument();
        expect(screen.getByText('10%')).toBeInTheDocument();
      });

      // Type valid answer
      const textarea = screen.getByPlaceholderText(/type your answer here/i) as HTMLTextAreaElement;
      fireEvent.change(textarea, { target: { value: 'Build a task management system' } });

      // Mock the refresh call after submit to return updated data
      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValueOnce({ data: updatedData });

      // Click submit button
      const submitButton = screen.getByRole('button', { name: /submit answer/i });
      fireEvent.click(submitButton);

      // Wait for success message
      await waitFor(() => {
        expect(screen.getByText(/answer submitted.*loading next question/i)).toBeInTheDocument();
      });

      // Advance timer to trigger state refresh (1 second)
      jest.advanceTimersByTime(1000);

      // Progress bar should update to 15%
      await waitFor(() => {
        expect(screen.getByText('15%')).toBeInTheDocument();
        expect(screen.getByText(/answered.*3.*20/i)).toBeInTheDocument();
      });

      // Next question should be displayed
      expect(screen.getByText(/what tech stack are you planning to use/i)).toBeInTheDocument();

      // Previous question should be gone
      expect(screen.queryByText(/what problem does your project solve/i)).not.toBeInTheDocument();

      // Textarea should be cleared
      expect(textarea.value).toBe('');
    });

    it('should update question counter after submit', async () => {
      // Initial state: Question 5 of 20
      const initialData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'discovery',
        discovery: {
          state: 'discovering',
          progress_percentage: 20,
          answered_count: 4,
          total_required: 20,
          current_question: {
            id: 'q5',
            category: 'problem',
            question: 'Question 5',
          },
        },
      };

      // Updated state: Question 6 of 20
      const updatedData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'discovery',
        discovery: {
          state: 'discovering',
          progress_percentage: 25,
          answered_count: 5,
          total_required: 20,
          current_question: {
            id: 'q6',
            category: 'solution',
            question: 'Question 6',
          },
        },
      };

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValueOnce({ data: initialData });

      mockAuthFetch.mockResolvedValueOnce({
        success: true,
        next_question: 'Question 6',
        is_complete: false,
        current_index: 5,
        total_questions: 20,
        progress_percentage: 25.0,
      });

      render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        expect(screen.getByText(/answered.*4.*20/i)).toBeInTheDocument();
      });

      const textarea = screen.getByPlaceholderText(/type your answer here/i) as HTMLTextAreaElement;
      fireEvent.change(textarea, { target: { value: 'Answer' } });

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValueOnce({ data: updatedData });

      const submitButton = screen.getByRole('button', { name: /submit answer/i });
      fireEvent.click(submitButton);

      await waitFor(() => {
        expect(screen.getByText(/answer submitted/i)).toBeInTheDocument();
      });

      jest.advanceTimersByTime(1000);

      // Counter should increment: 4 → 5
      await waitFor(() => {
        expect(screen.getByText(/answered.*5.*20/i)).toBeInTheDocument();
      });
    });
  });

  // ============================================================================
  // Feature: 012-discovery-answer-ui - Phase 11: User Story 9 (Next Question Display)
  // ============================================================================

  describe('Next Question Display (US9)', () => {
    it('should clear answer after successful submit (T072)', async () => {
      const initialData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'discovery',
        discovery: {
          state: 'discovering',
          progress_percentage: 10,
          answered_count: 2,
          total_required: 20,
          current_question: {
            id: 'q1',
            category: 'problem',
            question: 'What problem does your project solve?',
          },
        },
      };

      const updatedData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'discovery',
        discovery: {
          state: 'discovering',
          progress_percentage: 15,
          answered_count: 3,
          total_required: 20,
          current_question: {
            id: 'q2',
            category: 'tech_stack',
            question: 'What tech stack are you planning to use?',
          },
        },
      };

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValueOnce({ data: initialData });

      mockAuthFetch.mockResolvedValueOnce({
        success: true,
        next_question: 'What tech stack are you planning to use?',
        is_complete: false,
        current_index: 3,
        total_questions: 20,
        progress_percentage: 15.0,
      });

      render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        expect(screen.getByPlaceholderText(/type your answer here/i)).toBeInTheDocument();
      });

      const textarea = screen.getByPlaceholderText(/type your answer here/i) as HTMLTextAreaElement;
      const answerText = 'Build a task management system for remote teams';

      fireEvent.change(textarea, { target: { value: answerText } });

      // Verify answer is in textarea
      expect(textarea.value).toBe(answerText);

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValueOnce({ data: updatedData });

      const submitButton = screen.getByRole('button', { name: /submit answer/i });
      fireEvent.click(submitButton);

      // Wait for success message
      await waitFor(() => {
        expect(screen.getByText(/answer submitted/i)).toBeInTheDocument();
      });

      // Textarea should be cleared immediately
      expect(textarea.value).toBe('');

      // Advance timer
      jest.advanceTimersByTime(1000);

      // Textarea should remain empty
      await waitFor(() => {
        expect(textarea.value).toBe('');
      });
    });

    it('should display next question after submit (T073)', async () => {
      const initialData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'discovery',
        discovery: {
          state: 'discovering',
          progress_percentage: 50,
          answered_count: 10,
          total_required: 20,
          current_question: {
            id: 'q11',
            category: 'problem',
            question: 'Question 11: What is your target market?',
          },
        },
      };

      const updatedData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'discovery',
        discovery: {
          state: 'discovering',
          progress_percentage: 55,
          answered_count: 11,
          total_required: 20,
          current_question: {
            id: 'q12',
            category: 'solution',
            question: 'Question 12: How will you monetize?',
          },
        },
      };

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValueOnce({ data: initialData });

      mockAuthFetch.mockResolvedValueOnce({
        success: true,
        next_question: 'Question 12: How will you monetize?',
        is_complete: false,
        current_index: 11,
        total_questions: 20,
        progress_percentage: 55.0,
      });

      render(<DiscoveryProgress projectId={1} />);

      // Wait for initial question
      await waitFor(() => {
        expect(screen.getByText(/question 11.*what is your target market/i)).toBeInTheDocument();
      });

      const textarea = screen.getByPlaceholderText(/type your answer here/i) as HTMLTextAreaElement;
      fireEvent.change(textarea, { target: { value: 'Small businesses' } });

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValueOnce({ data: updatedData });

      const submitButton = screen.getByRole('button', { name: /submit answer/i });
      fireEvent.click(submitButton);

      // Wait for success message
      await waitFor(() => {
        expect(screen.getByText(/answer submitted/i)).toBeInTheDocument();
      });

      // Advance timer to trigger state refresh
      jest.advanceTimersByTime(1000);

      // Next question should appear
      await waitFor(() => {
        expect(screen.getByText(/question 12.*how will you monetize/i)).toBeInTheDocument();
      });

      // Previous question should be gone
      expect(screen.queryByText(/question 11.*what is your target market/i)).not.toBeInTheDocument();

      // Question number should increment (10 → 11)
      expect(screen.getByText(/answered.*11.*20/i)).toBeInTheDocument();
    });

    it('should handle smooth transition without page refresh', async () => {
      const initialData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'discovery',
        discovery: {
          state: 'discovering',
          progress_percentage: 85,
          answered_count: 17,
          total_required: 20,
          current_question: {
            id: 'q18',
            category: 'timeline',
            question: 'When do you plan to launch?',
          },
        },
      };

      const updatedData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'discovery',
        discovery: {
          state: 'discovering',
          progress_percentage: 90,
          answered_count: 18,
          total_required: 20,
          current_question: {
            id: 'q19',
            category: 'risks',
            question: 'What are the biggest risks?',
          },
        },
      };

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValueOnce({ data: initialData });

      mockAuthFetch.mockResolvedValueOnce({
        success: true,
        next_question: 'What are the biggest risks?',
        is_complete: false,
        current_index: 18,
        total_questions: 20,
        progress_percentage: 90.0,
      });

      render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        expect(screen.getByText(/when do you plan to launch/i)).toBeInTheDocument();
      });

      const textarea = screen.getByPlaceholderText(/type your answer here/i) as HTMLTextAreaElement;
      fireEvent.change(textarea, { target: { value: 'Q2 2025' } });

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValueOnce({ data: updatedData });

      const submitButton = screen.getByRole('button', { name: /submit answer/i });
      fireEvent.click(submitButton);

      await waitFor(() => {
        expect(screen.getByText(/answer submitted/i)).toBeInTheDocument();
      });

      jest.advanceTimersByTime(1000);

      // Verify no page reload occurred (component still rendered)
      await waitFor(() => {
        expect(screen.getByRole('region', { name: /discovery progress/i })).toBeInTheDocument();
        expect(screen.getByText(/what are the biggest risks/i)).toBeInTheDocument();
      });

      // Progress should update smoothly
      expect(screen.getByText('90%')).toBeInTheDocument();
    });
  });

  // ============================================================================
  // Feature: 012-discovery-answer-ui - Phase 12: User Story 10 (Discovery Completion)
  // ============================================================================

  describe('Discovery Completion (US10)', () => {
    it('should display completion state when discovery complete (T079)', async () => {
      // Initial state: Last question (19 of 20 answered, 95%)
      const initialData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'discovery',
        discovery: {
          state: 'discovering',
          progress_percentage: 95,
          answered_count: 19,
          total_required: 20,
          current_question: {
            id: 'q20',
            category: 'final',
            question: 'Any final thoughts or concerns?',
          },
        },
      };

      // After final answer: Discovery complete
      const completedData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'planning', // Phase transitions to planning
        discovery: {
          state: 'completed',
          progress_percentage: 100,
          answered_count: 20,
          total_required: 20,
        },
      };

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValueOnce({ data: initialData });

      mockAuthFetch.mockResolvedValueOnce({
        success: true,
        next_question: null, // No more questions
        is_complete: true,
        current_index: 20,
        total_questions: 20,
        progress_percentage: 100.0,
      });

      render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        expect(screen.getByText(/any final thoughts or concerns/i)).toBeInTheDocument();
      });

      const textarea = screen.getByPlaceholderText(/type your answer here/i) as HTMLTextAreaElement;
      fireEvent.change(textarea, { target: { value: 'Excited to get started!' } });

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValueOnce({ data: completedData });

      const submitButton = screen.getByRole('button', { name: /submit answer/i });
      fireEvent.click(submitButton);

      await waitFor(() => {
        expect(screen.getByText(/answer submitted/i)).toBeInTheDocument();
      });

      jest.advanceTimersByTime(1000);

      // Completion state should be displayed
      await waitFor(() => {
        expect(screen.getByText(/discovery complete/i)).toBeInTheDocument();
      });

      // Answer UI should be hidden (no textarea)
      expect(screen.queryByPlaceholderText(/type your answer here/i)).not.toBeInTheDocument();

      // Submit button should be hidden
      expect(screen.queryByRole('button', { name: /submit answer/i })).not.toBeInTheDocument();
    });

    it('should show 100% progress when complete', async () => {
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
        expect(screen.getByText(/discovery complete/i)).toBeInTheDocument();
      });

      // Note: Progress bar is not shown when completed (from existing tests)
      // Just verify completion message is present
      expect(screen.getByText(/discovery complete/i)).toBeInTheDocument();
    });
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
  // Duplicate Submission Prevention Tests
  // ============================================================================

  describe('Duplicate Submission Prevention', () => {
    it('should prevent duplicate submissions while already submitting', async () => {
      const mockData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'discovery',
        discovery: {
          state: 'discovering',
          progress_percentage: 10,
          answered_count: 2,
          total_required: 20,
          current_question: {
            id: 'q1',
            category: 'problem',
            question: 'What problem does your project solve?',
          },
        },
      };

      (projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({ data: mockData });

      // Make authFetch take a long time
      mockAuthFetch.mockImplementation(() => new Promise(() => {}));

      render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        expect(screen.getByPlaceholderText(/type your answer here/i)).toBeInTheDocument();
      });

      const textarea = screen.getByPlaceholderText(/type your answer here/i) as HTMLTextAreaElement;
      fireEvent.change(textarea, { target: { value: 'Valid answer' } });

      const submitButton = screen.getByRole('button', { name: /submit answer/i });

      // Click submit multiple times rapidly
      fireEvent.click(submitButton);
      fireEvent.click(submitButton);
      fireEvent.click(submitButton);

      // Should only call once
      await waitFor(() => {
        expect(mockAuthFetch).toHaveBeenCalledTimes(1);
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
      /**
       * Tests for initializing task state when tasks already exist.
       * This addresses the UX issue where users who join late (after tasks
       * were generated) see the "Generate Task Breakdown" button even though
       * tasks already exist.
       */

      const mockPlanningPhaseData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'planning',
        discovery: {
          state: 'completed',
          progress_percentage: 100,
          answered_count: 10,
          total_required: 10,
        },
      };

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
      /**
       * Tests for handling the idempotent backend response when tasks already exist.
       * When the user clicks "Generate Task Breakdown" and tasks already exist,
       * the backend returns {success: true, tasks_already_exist: true} instead of 400.
       */

      const mockPlanningPhaseData: DiscoveryProgressResponse = {
        project_id: 1,
        phase: 'planning',
        discovery: {
          state: 'completed',
          progress_percentage: 100,
          answered_count: 10,
          total_required: 10,
        },
      };

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
