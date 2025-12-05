/**
 * Test suite for QualityGatesPanel component
 * Target: 85%+ code coverage, 100% for getGateStatus function
 *
 * Tests task auto-selection, gate status determination, loading/error states,
 * and integration with child components
 */

import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import QualityGatesPanel from '@/components/quality-gates/QualityGatesPanel';
import * as qualityGatesAPI from '@/api/qualityGates';
import type { Task } from '@/types/agentState';
import type { QualityGateStatus, QualityGateFailure } from '@/types/qualityGates';

// Mock child components
jest.mock('@/components/quality-gates/QualityGateStatus', () => {
  return function MockQualityGateStatus({ taskId }: { taskId: number }) {
    return <div data-testid="quality-gate-status">QualityGateStatus for task {taskId}</div>;
  };
});

jest.mock('@/components/quality-gates/GateStatusIndicator', () => {
  return function MockGateStatusIndicator({
    gateType,
    status,
    testId,
  }: {
    gateType: string;
    status: string | null;
    testId?: string;
  }) {
    return (
      <div data-testid={testId || `gate-${gateType}`}>
        {gateType}: {status || 'pending'}
      </div>
    );
  };
});

// Mock API functions
jest.mock('@/api/qualityGates');

describe('QualityGatesPanel', () => {
  const mockFetchQualityGateStatus = qualityGatesAPI.fetchQualityGateStatus as jest.MockedFunction<
    typeof qualityGatesAPI.fetchQualityGateStatus
  >;

  // Sample tasks for testing
  const completedTask: Task = {
    id: 1,
    title: 'Implement authentication',
    description: 'Add JWT auth',
    status: 'completed',
    priority: 'high',
    created_at: '2025-01-01T00:00:00Z',
    updated_at: '2025-01-01T00:00:00Z',
  };

  const inProgressTask: Task = {
    id: 2,
    title: 'Add tests',
    description: 'Write unit tests',
    status: 'in_progress',
    priority: 'medium',
    created_at: '2025-01-01T00:00:00Z',
    updated_at: '2025-01-01T00:00:00Z',
  };

  const pendingTask: Task = {
    id: 3,
    title: 'Update docs',
    description: 'Update README',
    status: 'pending',
    priority: 'low',
    created_at: '2025-01-01T00:00:00Z',
    updated_at: '2025-01-01T00:00:00Z',
  };

  const mockPassedStatus: QualityGateStatus = {
    task_id: 1,
    status: 'passed',
    failures: [],
    requires_human_approval: false,
    timestamp: '2025-01-01T00:00:00Z',
  };

  const mockFailedStatus: QualityGateStatus = {
    task_id: 1,
    status: 'failed',
    failures: [
      {
        gate: 'tests',
        reason: '3 tests failed',
        severity: 'critical',
        details: 'test_auth.py::test_login FAILED',
      },
    ],
    requires_human_approval: false,
    timestamp: '2025-01-01T00:00:00Z',
  };

  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('Empty State', () => {
    it('should display empty state when no tasks provided', () => {
      render(<QualityGatesPanel projectId={1} tasks={[]} />);

      expect(
        screen.getByText(/no tasks available for quality gate evaluation/i)
      ).toBeInTheDocument();
    });

    it('should display empty state when only pending tasks exist', () => {
      render(<QualityGatesPanel projectId={1} tasks={[pendingTask]} />);

      expect(
        screen.getByText(/no tasks available for quality gate evaluation/i)
      ).toBeInTheDocument();
    });

    it('should have proper accessibility for empty state', () => {
      render(<QualityGatesPanel projectId={1} tasks={[]} />);

      const emptyState = screen.getByRole('status');
      expect(emptyState).toHaveAttribute('aria-label', 'No tasks available');
    });
  });

  describe('Task Auto-Selection', () => {
    it('should auto-select first eligible task (completed)', async () => {
      mockFetchQualityGateStatus.mockResolvedValue(mockPassedStatus);

      render(<QualityGatesPanel projectId={1} tasks={[completedTask]} />);

      await waitFor(() => {
        expect(screen.getByRole('combobox')).toHaveValue('1');
      });

      expect(mockFetchQualityGateStatus).toHaveBeenCalledWith(1, 1);
    });

    it('should auto-select first eligible task (in_progress)', async () => {
      mockFetchQualityGateStatus.mockResolvedValue(mockPassedStatus);

      render(<QualityGatesPanel projectId={1} tasks={[inProgressTask]} />);

      await waitFor(() => {
        expect(screen.getByRole('combobox')).toHaveValue('2');
      });

      expect(mockFetchQualityGateStatus).toHaveBeenCalledWith(2, 1);
    });

    it('should auto-select first eligible task when mixed with pending', async () => {
      mockFetchQualityGateStatus.mockResolvedValue(mockPassedStatus);

      render(
        <QualityGatesPanel projectId={1} tasks={[pendingTask, completedTask, inProgressTask]} />
      );

      // Should select completedTask (id=1) as it's the first eligible
      await waitFor(() => {
        expect(screen.getByRole('combobox')).toHaveValue('1');
      });
    });

    it('should only auto-select once on mount', async () => {
      mockFetchQualityGateStatus.mockResolvedValue(mockPassedStatus);

      const { rerender } = render(<QualityGatesPanel projectId={1} tasks={[completedTask]} />);

      await waitFor(() => {
        expect(mockFetchQualityGateStatus).toHaveBeenCalledTimes(1);
      });

      // Re-render with same tasks
      rerender(<QualityGatesPanel projectId={1} tasks={[completedTask]} />);

      // Should not fetch again
      await waitFor(() => {
        expect(mockFetchQualityGateStatus).toHaveBeenCalledTimes(1);
      });
    });

    it('should reset auto-selection flag when no eligible tasks remain', async () => {
      mockFetchQualityGateStatus.mockResolvedValue(mockPassedStatus);

      const { rerender } = render(<QualityGatesPanel projectId={1} tasks={[completedTask]} />);

      await waitFor(() => {
        expect(mockFetchQualityGateStatus).toHaveBeenCalledTimes(1);
      });

      // Remove all eligible tasks (flag should reset)
      rerender(<QualityGatesPanel projectId={1} tasks={[]} />);

      await waitFor(() => {
        // Verify empty state is shown
        expect(
          screen.getByText(/no tasks available for quality gate evaluation/i)
        ).toBeInTheDocument();
      });

      // Verify the auto-selection flag was reset by checking the ref behavior
      // Note: Direct ref testing not possible, so we verify the observable behavior
      // (empty state correctly displayed)
      expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
    });
  });

  describe('Task Selection UI', () => {
    it('should display task selector dropdown', async () => {
      mockFetchQualityGateStatus.mockResolvedValue(mockPassedStatus);

      render(<QualityGatesPanel projectId={1} tasks={[completedTask]} />);

      await waitFor(() => {
        expect(screen.getByLabelText(/select task for quality gate status/i)).toBeInTheDocument();
      });
    });

    it('should list all eligible tasks in dropdown', async () => {
      mockFetchQualityGateStatus.mockResolvedValue(mockPassedStatus);

      render(<QualityGatesPanel projectId={1} tasks={[completedTask, inProgressTask]} />);

      await waitFor(() => {
        expect(screen.getByText('Task #1: Implement authentication')).toBeInTheDocument();
        expect(screen.getByText('Task #2: Add tests')).toBeInTheDocument();
      });
    });

    it('should not list pending tasks in dropdown', async () => {
      mockFetchQualityGateStatus.mockResolvedValue(mockPassedStatus);

      render(
        <QualityGatesPanel projectId={1} tasks={[pendingTask, completedTask, inProgressTask]} />
      );

      await waitFor(() => {
        expect(screen.getByText('Task #1: Implement authentication')).toBeInTheDocument();
        expect(screen.getByText('Task #2: Add tests')).toBeInTheDocument();
        expect(screen.queryByText('Task #3: Update docs')).not.toBeInTheDocument();
      });
    });

    it('should change selected task on dropdown change', async () => {
      mockFetchQualityGateStatus.mockResolvedValue(mockPassedStatus);

      render(<QualityGatesPanel projectId={1} tasks={[completedTask, inProgressTask]} />);

      await waitFor(() => {
        expect(mockFetchQualityGateStatus).toHaveBeenCalledWith(1, 1);
      });

      const dropdown = screen.getByRole('combobox');
      fireEvent.change(dropdown, { target: { value: '2' } });

      await waitFor(() => {
        expect(mockFetchQualityGateStatus).toHaveBeenCalledWith(2, 1);
      });
    });
  });

  describe('Loading State', () => {
    it('should display loading indicator while fetching', async () => {
      mockFetchQualityGateStatus.mockImplementation(
        () => new Promise((resolve) => setTimeout(() => resolve(mockPassedStatus), 100))
      );

      render(<QualityGatesPanel projectId={1} tasks={[completedTask]} />);

      expect(await screen.findByText(/loading quality gates/i)).toBeInTheDocument();
      expect(screen.getByRole('status', { name: /loading quality gates/i })).toBeInTheDocument();
    });

    it('should hide loading indicator after data loads', async () => {
      mockFetchQualityGateStatus.mockResolvedValue(mockPassedStatus);

      render(<QualityGatesPanel projectId={1} tasks={[completedTask]} />);

      await waitFor(() => {
        expect(screen.queryByText(/loading quality gates/i)).not.toBeInTheDocument();
      });
    });
  });

  describe('Error Handling', () => {
    it('should display error message on API failure', async () => {
      mockFetchQualityGateStatus.mockRejectedValue(new Error('Network error'));

      render(<QualityGatesPanel projectId={1} tasks={[completedTask]} />);

      await waitFor(() => {
        expect(screen.getByText(/error loading quality gates/i)).toBeInTheDocument();
        expect(screen.getByText(/network error/i)).toBeInTheDocument();
      });
    });

    it('should display specific error for 404 response', async () => {
      mockFetchQualityGateStatus.mockRejectedValue(
        new Error('Failed to fetch quality gate status: 404 Not Found')
      );

      render(<QualityGatesPanel projectId={1} tasks={[completedTask]} />);

      await waitFor(() => {
        expect(screen.getByText(/no quality gate data found for this task/i)).toBeInTheDocument();
      });
    });

    it('should display network error message for network failures', async () => {
      mockFetchQualityGateStatus.mockRejectedValue(new Error('fetch failed: Network error'));

      render(<QualityGatesPanel projectId={1} tasks={[completedTask]} />);

      await waitFor(() => {
        expect(screen.getByText(/network error\. please check your connection/i)).toBeInTheDocument();
      });
    });

    it('should have proper ARIA attributes for errors', async () => {
      mockFetchQualityGateStatus.mockRejectedValue(new Error('API error'));

      render(<QualityGatesPanel projectId={1} tasks={[completedTask]} />);

      await waitFor(() => {
        const errorElement = screen.getByRole('alert');
        expect(errorElement).toHaveAttribute('aria-live', 'polite');
      });
    });

    it('should not display gate indicators on error', async () => {
      mockFetchQualityGateStatus.mockRejectedValue(new Error('API error'));

      render(<QualityGatesPanel projectId={1} tasks={[completedTask]} />);

      await waitFor(() => {
        expect(screen.getByText(/error loading quality gates/i)).toBeInTheDocument();
      });

      expect(screen.queryByTestId('gate-tests')).not.toBeInTheDocument();
      expect(screen.queryByTestId('gate-coverage')).not.toBeInTheDocument();
    });
  });

  describe('Gate Status Indicators', () => {
    it('should render all 5 gate type indicators', async () => {
      mockFetchQualityGateStatus.mockResolvedValue(mockPassedStatus);

      render(<QualityGatesPanel projectId={1} tasks={[completedTask]} />);

      await waitFor(() => {
        expect(screen.getByTestId('gate-tests')).toBeInTheDocument();
        expect(screen.getByTestId('gate-coverage')).toBeInTheDocument();
        expect(screen.getByTestId('gate-type-check')).toBeInTheDocument();
        expect(screen.getByTestId('gate-lint')).toBeInTheDocument();
        expect(screen.getByTestId('gate-review')).toBeInTheDocument();
      });
    });

    it('should have list role for accessibility', async () => {
      mockFetchQualityGateStatus.mockResolvedValue(mockPassedStatus);

      render(<QualityGatesPanel projectId={1} tasks={[completedTask]} />);

      await waitFor(() => {
        const gateList = screen.getByRole('list');
        expect(gateList).toHaveAttribute('aria-label', 'Quality gate status indicators');
      });
    });
  });

  describe('Integration with QualityGateStatus', () => {
    it('should render detailed status view with selected task ID', async () => {
      mockFetchQualityGateStatus.mockResolvedValue(mockPassedStatus);

      render(<QualityGatesPanel projectId={1} tasks={[completedTask]} />);

      await waitFor(() => {
        expect(screen.getByTestId('quality-gate-status')).toBeInTheDocument();
        expect(screen.getByText(/qualitygateStatus for task 1/i)).toBeInTheDocument();
      });
    });

    it('should update detailed status when task changes', async () => {
      mockFetchQualityGateStatus.mockResolvedValue(mockPassedStatus);

      render(<QualityGatesPanel projectId={1} tasks={[completedTask, inProgressTask]} />);

      await waitFor(() => {
        expect(screen.getByText(/qualitygateStatus for task 1/i)).toBeInTheDocument();
      });

      const dropdown = screen.getByRole('combobox');
      fireEvent.change(dropdown, { target: { value: '2' } });

      await waitFor(() => {
        expect(screen.getByText(/qualitygateStatus for task 2/i)).toBeInTheDocument();
      });
    });
  });

  describe('Request Cancellation', () => {
    it('should cancel in-flight requests on task change', async () => {
      let resolveFirst: () => void;
      const firstPromise = new Promise<QualityGateStatus>((resolve) => {
        resolveFirst = () => resolve(mockPassedStatus);
      });

      mockFetchQualityGateStatus.mockReturnValueOnce(firstPromise);

      render(<QualityGatesPanel projectId={1} tasks={[completedTask, inProgressTask]} />);

      await waitFor(() => {
        expect(mockFetchQualityGateStatus).toHaveBeenCalledWith(1, 1);
      });

      // Change task before first request resolves
      mockFetchQualityGateStatus.mockResolvedValue(mockPassedStatus);
      const dropdown = screen.getByRole('combobox');
      fireEvent.change(dropdown, { target: { value: '2' } });

      // Resolve first request (should be ignored)
      resolveFirst!();

      await waitFor(() => {
        expect(mockFetchQualityGateStatus).toHaveBeenCalledWith(2, 1);
      });
    });

    it('should cancel in-flight requests on unmount', async () => {
      mockFetchQualityGateStatus.mockImplementation(
        () => new Promise((resolve) => setTimeout(() => resolve(mockPassedStatus), 100))
      );

      const { unmount } = render(<QualityGatesPanel projectId={1} tasks={[completedTask]} />);

      await waitFor(() => {
        expect(mockFetchQualityGateStatus).toHaveBeenCalled();
      });

      // Unmount before request completes
      unmount();

      // Wait to ensure no errors thrown
      await new Promise((resolve) => setTimeout(resolve, 150));
    });
  });

  describe('getGateStatus Function', () => {
    it('should return "failed" for gate with explicit failure', async () => {
      const statusWithTestFailure: QualityGateStatus = {
        task_id: 1,
        status: 'failed',
        failures: [
          { gate: 'tests', reason: 'Tests failed', severity: 'critical' },
        ],
        requires_human_approval: false,
        timestamp: '2025-01-01T00:00:00Z',
      };

      mockFetchQualityGateStatus.mockResolvedValue(statusWithTestFailure);

      render(<QualityGatesPanel projectId={1} tasks={[completedTask]} />);

      await waitFor(() => {
        expect(screen.getByText('tests: failed')).toBeInTheDocument();
      });
    });

    it('should return "passed" for gate when overall status is passed', async () => {
      mockFetchQualityGateStatus.mockResolvedValue(mockPassedStatus);

      render(<QualityGatesPanel projectId={1} tasks={[completedTask]} />);

      await waitFor(() => {
        expect(screen.getByText('tests: passed')).toBeInTheDocument();
        expect(screen.getByText('coverage: passed')).toBeInTheDocument();
      });
    });

    it('should return "running" when overall status is running', async () => {
      const runningStatus: QualityGateStatus = {
        task_id: 1,
        status: 'running',
        failures: [],
        requires_human_approval: false,
        timestamp: '2025-01-01T00:00:00Z',
      };

      mockFetchQualityGateStatus.mockResolvedValue(runningStatus);

      render(<QualityGatesPanel projectId={1} tasks={[completedTask]} />);

      await waitFor(() => {
        expect(screen.getByText('tests: running')).toBeInTheDocument();
        expect(screen.getByText('coverage: running')).toBeInTheDocument();
      });
    });

    it('should return "pending" (null) when no status available', async () => {
      mockFetchQualityGateStatus.mockResolvedValue(null);

      render(<QualityGatesPanel projectId={1} tasks={[completedTask]} />);

      await waitFor(() => {
        expect(screen.getByText('tests: pending')).toBeInTheDocument();
        expect(screen.getByText('coverage: pending')).toBeInTheDocument();
      });
    });

    it('should handle multiple gate failures correctly', async () => {
      const multipleFailures: QualityGateStatus = {
        task_id: 1,
        status: 'failed',
        failures: [
          { gate: 'tests', reason: 'Tests failed', severity: 'critical' },
          { gate: 'coverage', reason: 'Coverage too low', severity: 'high' },
          { gate: 'linting', reason: 'Lint errors', severity: 'medium' },
        ],
        requires_human_approval: false,
        timestamp: '2025-01-01T00:00:00Z',
      };

      mockFetchQualityGateStatus.mockResolvedValue(multipleFailures);

      render(<QualityGatesPanel projectId={1} tasks={[completedTask]} />);

      await waitFor(() => {
        expect(screen.getByText('tests: failed')).toBeInTheDocument();
        expect(screen.getByText('coverage: failed')).toBeInTheDocument();
        expect(screen.getByText('lint: failed')).toBeInTheDocument();
        // Gates without explicit failures show pending (conservative approach)
        expect(screen.getByText('type-check: pending')).toBeInTheDocument();
        expect(screen.getByText('review: pending')).toBeInTheDocument();
      });
    });

    it('should handle E2E to backend gate type mapping', async () => {
      const backendNamedFailure: QualityGateStatus = {
        task_id: 1,
        status: 'failed',
        failures: [
          { gate: 'type_check', reason: 'Type errors', severity: 'high' }, // Backend naming
          { gate: 'code_review', reason: 'Review failed', severity: 'critical' }, // Backend naming
        ],
        requires_human_approval: false,
        timestamp: '2025-01-01T00:00:00Z',
      };

      mockFetchQualityGateStatus.mockResolvedValue(backendNamedFailure);

      render(<QualityGatesPanel projectId={1} tasks={[completedTask]} />);

      await waitFor(() => {
        expect(screen.getByText('type-check: failed')).toBeInTheDocument(); // E2E naming in UI
        expect(screen.getByText('review: failed')).toBeInTheDocument(); // E2E naming in UI
      });
    });
  });

  describe('Project ID Scoping', () => {
    it('should pass projectId to API call', async () => {
      mockFetchQualityGateStatus.mockResolvedValue(mockPassedStatus);

      render(<QualityGatesPanel projectId={42} tasks={[completedTask]} />);

      await waitFor(() => {
        expect(mockFetchQualityGateStatus).toHaveBeenCalledWith(1, 42);
      });
    });

    it('should update API calls when projectId changes', async () => {
      mockFetchQualityGateStatus.mockResolvedValue(mockPassedStatus);

      const { rerender } = render(<QualityGatesPanel projectId={1} tasks={[completedTask]} />);

      await waitFor(() => {
        expect(mockFetchQualityGateStatus).toHaveBeenCalledWith(1, 1);
      });

      rerender(<QualityGatesPanel projectId={2} tasks={[completedTask]} />);

      await waitFor(() => {
        expect(mockFetchQualityGateStatus).toHaveBeenCalledWith(1, 2);
      });
    });
  });
});
