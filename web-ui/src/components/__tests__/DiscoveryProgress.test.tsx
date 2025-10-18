/**
 * Tests for DiscoveryProgress Component (cf-17.2)
 * TDD RED Phase - Write tests first
 */

import { render, screen, waitFor } from '@testing-library/react';
import DiscoveryProgress from '../DiscoveryProgress';
import { projectsApi } from '@/lib/api';
import type { DiscoveryProgressResponse } from '@/types/api';

// Mock the API
jest.mock('@/lib/api', () => ({
  projectsApi: {
    getDiscoveryProgress: jest.fn(),
  },
}));

// Mock child components
jest.mock('../ProgressBar', () => {
  return function MockProgressBar({ percentage, label }: { percentage: number; label?: string }) {
    return (
      <div data-testid="mock-progress-bar">
        {label && <span>{label}</span>}
        <span>{percentage}%</span>
      </div>
    );
  };
});

jest.mock('../PhaseIndicator', () => {
  return function MockPhaseIndicator({ phase }: { phase: string }) {
    return <span data-testid="mock-phase-indicator">{phase}</span>;
  };
});

describe('DiscoveryProgress Component', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    jest.useFakeTimers();
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

      // Initial fetch
      await waitFor(() => {
        expect(projectsApi.getDiscoveryProgress).toHaveBeenCalledTimes(1);
      });

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
