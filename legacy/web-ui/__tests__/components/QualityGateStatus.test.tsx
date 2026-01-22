/**
 * Tests for QualityGateStatus Component (T068)
 * Sprint 10 Phase 3 - Quality Gates Frontend
 * Updated for emoji-to-Hugeicons migration: icons now use Hugeicons components
 */

import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import QualityGateStatus from '@/components/quality-gates/QualityGateStatus';
import * as qualityGatesApi from '@/api/qualityGates';
import type { QualityGateStatus as QualityGateStatusType } from '@/types/qualityGates';

// Mock Hugeicons
jest.mock('@hugeicons/react', () => {
  const React = require('react');
  const createMockIcon = (name: string) => {
    const Icon = ({ className }: { className?: string }) => (
      <svg data-testid={name} className={className} aria-hidden="true" />
    );
    Icon.displayName = name;
    return Icon;
  };
  return {
    Alert02Icon: createMockIcon('Alert02Icon'),
    CheckmarkCircle01Icon: createMockIcon('CheckmarkCircle01Icon'),
    Cancel01Icon: createMockIcon('Cancel01Icon'),
    Loading03Icon: createMockIcon('Loading03Icon'),
    PauseIcon: createMockIcon('PauseIcon'),
    HelpCircleIcon: createMockIcon('HelpCircleIcon'),
    TestTube01Icon: createMockIcon('TestTube01Icon'),
    ChartBarLineIcon: createMockIcon('ChartBarLineIcon'),
    FileEditIcon: createMockIcon('FileEditIcon'),
    SparklesIcon: createMockIcon('SparklesIcon'),
    Search01Icon: createMockIcon('Search01Icon'),
    Settings01Icon: createMockIcon('Settings01Icon'),
    RefreshIcon: createMockIcon('RefreshIcon'),
    InformationCircleIcon: createMockIcon('InformationCircleIcon'),
    UserIcon: createMockIcon('UserIcon'),
  };
});

// Mock the API module
jest.mock('@/api/qualityGates');

const mockFetchQualityGateStatus = qualityGatesApi.fetchQualityGateStatus as jest.MockedFunction<
  typeof qualityGatesApi.fetchQualityGateStatus
>;
const mockTriggerQualityGates = qualityGatesApi.triggerQualityGates as jest.MockedFunction<
  typeof qualityGatesApi.triggerQualityGates
>;

describe('QualityGateStatus Component', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('Loading State', () => {
    it('should display loading state initially', () => {
      mockFetchQualityGateStatus.mockImplementation(
        () => new Promise(() => {}) // Never resolves
      );

      render(<QualityGateStatus taskId={1} />);

      expect(screen.getByText(/Loading quality gate status.../i)).toBeInTheDocument();
    });

    it('should show spinner during loading', () => {
      mockFetchQualityGateStatus.mockImplementation(
        () => new Promise(() => {}) // Never resolves
      );

      const { container } = render(<QualityGateStatus taskId={1} />);

      const spinner = container.querySelector('.animate-spin');
      expect(spinner).toBeInTheDocument();
    });
  });

  describe('Error State', () => {
    it('should display error message when fetch fails', async () => {
      const errorMessage = 'Network error';
      mockFetchQualityGateStatus.mockRejectedValue(new Error(errorMessage));

      render(<QualityGateStatus taskId={1} />);

      await waitFor(() => {
        expect(screen.getByText(/Error Loading Quality Gates/i)).toBeInTheDocument();
      });

      expect(screen.getByText(errorMessage)).toBeInTheDocument();
    });

    it('should display Alert02Icon on error', async () => {
      mockFetchQualityGateStatus.mockRejectedValue(new Error('Failed'));

      render(<QualityGateStatus taskId={1} />);

      await waitFor(() => {
        expect(screen.getByTestId('Alert02Icon')).toBeInTheDocument();
      });
    });
  });

  describe('No Status State', () => {
    it('should display no status message when status is null', async () => {
      mockFetchQualityGateStatus.mockResolvedValue(null);

      render(<QualityGateStatus taskId={1} />);

      await waitFor(() => {
        expect(screen.getByText(/No quality gate results yet/i)).toBeInTheDocument();
      });
    });

    it('should show run button when no status available', async () => {
      mockFetchQualityGateStatus.mockResolvedValue(null);

      render(<QualityGateStatus taskId={1} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /Run Quality Gates/i })).toBeInTheDocument();
      });
    });
  });

  describe('Passed Status', () => {
    it('should display passed status correctly', async () => {
      const mockStatus: QualityGateStatusType = {
        task_id: 1,
        status: 'passed',
        failures: [],
        requires_human_approval: false,
        timestamp: new Date().toISOString(),
      };

      mockFetchQualityGateStatus.mockResolvedValue(mockStatus);

      render(<QualityGateStatus taskId={1} />);

      await waitFor(() => {
        expect(screen.getByText('passed')).toBeInTheDocument();
      });
    });

    it('should show success message for passed status with no failures', async () => {
      const mockStatus: QualityGateStatusType = {
        task_id: 1,
        status: 'passed',
        failures: [],
        requires_human_approval: false,
        timestamp: new Date().toISOString(),
      };

      mockFetchQualityGateStatus.mockResolvedValue(mockStatus);

      render(<QualityGateStatus taskId={1} />);

      await waitFor(() => {
        expect(screen.getByText(/All quality gates passed!/i)).toBeInTheDocument();
      });
    });

    it('should show green status badge for passed', async () => {
      const mockStatus: QualityGateStatusType = {
        task_id: 1,
        status: 'passed',
        failures: [],
        requires_human_approval: false,
        timestamp: new Date().toISOString(),
      };

      mockFetchQualityGateStatus.mockResolvedValue(mockStatus);

      const { container } = render(<QualityGateStatus taskId={1} />);

      await waitFor(() => {
        const badge = screen.getByText('passed');
        expect(badge).toHaveClass('bg-secondary');
        expect(badge).toHaveClass('text-secondary-foreground');
      });
    });
  });

  describe('Failed Status', () => {
    it('should display failed status correctly', async () => {
      const mockStatus: QualityGateStatusType = {
        task_id: 1,
        status: 'failed',
        failures: [
          {
            gate: 'tests',
            reason: 'Test suite failed',
            severity: 'critical',
          },
        ],
        requires_human_approval: false,
        timestamp: new Date().toISOString(),
      };

      mockFetchQualityGateStatus.mockResolvedValue(mockStatus);

      render(<QualityGateStatus taskId={1} />);

      await waitFor(() => {
        expect(screen.getByText('failed')).toBeInTheDocument();
      });
    });

    it('should show red status badge for failed', async () => {
      const mockStatus: QualityGateStatusType = {
        task_id: 1,
        status: 'failed',
        failures: [
          {
            gate: 'tests',
            reason: 'Test suite failed',
            severity: 'critical',
          },
        ],
        requires_human_approval: false,
        timestamp: new Date().toISOString(),
      };

      mockFetchQualityGateStatus.mockResolvedValue(mockStatus);

      render(<QualityGateStatus taskId={1} />);

      await waitFor(() => {
        const badge = screen.getByText('failed');
        expect(badge).toHaveClass('bg-destructive');
        expect(badge).toHaveClass('text-destructive-foreground');
        expect(badge).toHaveClass('border-destructive');
      });
    });

    it('should display failure list section when failures exist', async () => {
      const mockStatus: QualityGateStatusType = {
        task_id: 1,
        status: 'failed',
        failures: [
          {
            gate: 'tests',
            reason: 'Test suite failed',
            severity: 'critical',
          },
          {
            gate: 'coverage',
            reason: 'Coverage below 85%',
            severity: 'high',
          },
        ],
        requires_human_approval: false,
        timestamp: new Date().toISOString(),
      };

      mockFetchQualityGateStatus.mockResolvedValue(mockStatus);

      render(<QualityGateStatus taskId={1} />);

      await waitFor(() => {
        expect(screen.getByText(/Quality Gate Failures \(2\)/i)).toBeInTheDocument();
      });
    });

    it('should display each failure with gate type and reason', async () => {
      const mockStatus: QualityGateStatusType = {
        task_id: 1,
        status: 'failed',
        failures: [
          {
            gate: 'tests',
            reason: 'Test suite failed',
            severity: 'critical',
          },
        ],
        requires_human_approval: false,
        timestamp: new Date().toISOString(),
      };

      mockFetchQualityGateStatus.mockResolvedValue(mockStatus);

      render(<QualityGateStatus taskId={1} />);

      await waitFor(() => {
        expect(screen.getByText('tests')).toBeInTheDocument();
        expect(screen.getByText('Test suite failed')).toBeInTheDocument();
      });
    });

    it('should display failure details if provided', async () => {
      const mockStatus: QualityGateStatusType = {
        task_id: 1,
        status: 'failed',
        failures: [
          {
            gate: 'tests',
            reason: 'Test suite failed',
            details: 'TypeError: Cannot read property "foo" of undefined',
            severity: 'critical',
          },
        ],
        requires_human_approval: false,
        timestamp: new Date().toISOString(),
      };

      mockFetchQualityGateStatus.mockResolvedValue(mockStatus);

      render(<QualityGateStatus taskId={1} />);

      await waitFor(() => {
        expect(screen.getByText(/TypeError: Cannot read property "foo"/i)).toBeInTheDocument();
      });
    });

    it('should display severity badges for failures', async () => {
      const mockStatus: QualityGateStatusType = {
        task_id: 1,
        status: 'failed',
        failures: [
          {
            gate: 'tests',
            reason: 'Critical failure',
            severity: 'critical',
          },
          {
            gate: 'coverage',
            reason: 'High severity',
            severity: 'high',
          },
          {
            gate: 'linting',
            reason: 'Medium severity',
            severity: 'medium',
          },
          {
            gate: 'type_check',
            reason: 'Low severity',
            severity: 'low',
          },
        ],
        requires_human_approval: false,
        timestamp: new Date().toISOString(),
      };

      mockFetchQualityGateStatus.mockResolvedValue(mockStatus);

      render(<QualityGateStatus taskId={1} />);

      await waitFor(() => {
        expect(screen.getByText('critical')).toBeInTheDocument();
        expect(screen.getByText('high')).toBeInTheDocument();
        expect(screen.getByText('medium')).toBeInTheDocument();
        expect(screen.getByText('low')).toBeInTheDocument();
      });
    });
  });

  describe('Running Status', () => {
    it('should display running status correctly', async () => {
      const mockStatus: QualityGateStatusType = {
        task_id: 1,
        status: 'running',
        failures: [],
        requires_human_approval: false,
        timestamp: new Date().toISOString(),
      };

      mockFetchQualityGateStatus.mockResolvedValue(mockStatus);

      render(<QualityGateStatus taskId={1} />);

      await waitFor(() => {
        expect(screen.getByText('running')).toBeInTheDocument();
      });
    });

    it('should show yellow status badge for running', async () => {
      const mockStatus: QualityGateStatusType = {
        task_id: 1,
        status: 'running',
        failures: [],
        requires_human_approval: false,
        timestamp: new Date().toISOString(),
      };

      mockFetchQualityGateStatus.mockResolvedValue(mockStatus);

      render(<QualityGateStatus taskId={1} />);

      await waitFor(() => {
        const badge = screen.getByText('running');
        expect(badge).toHaveClass('bg-primary/20');
        expect(badge).toHaveClass('text-foreground');
      });
    });

    it('should display progress indicator when running', async () => {
      const mockStatus: QualityGateStatusType = {
        task_id: 1,
        status: 'running',
        failures: [],
        requires_human_approval: false,
        timestamp: new Date().toISOString(),
      };

      mockFetchQualityGateStatus.mockResolvedValue(mockStatus);

      render(<QualityGateStatus taskId={1} />);

      await waitFor(() => {
        expect(screen.getByText(/Quality gates are running.../i)).toBeInTheDocument();
      });
    });

    it('should disable re-run button when running', async () => {
      const mockStatus: QualityGateStatusType = {
        task_id: 1,
        status: 'running',
        failures: [],
        requires_human_approval: false,
        timestamp: new Date().toISOString(),
      };

      mockFetchQualityGateStatus.mockResolvedValue(mockStatus);

      render(<QualityGateStatus taskId={1} />);

      await waitFor(() => {
        const button = screen.getByRole('button', { name: /Re-run/i });
        expect(button).toBeDisabled();
      });
    });
  });

  describe('Pending Status', () => {
    it('should display pending status correctly', async () => {
      const mockStatus: QualityGateStatusType = {
        task_id: 1,
        status: 'pending',
        failures: [],
        requires_human_approval: false,
        timestamp: new Date().toISOString(),
      };

      mockFetchQualityGateStatus.mockResolvedValue(mockStatus);

      render(<QualityGateStatus taskId={1} />);

      await waitFor(() => {
        expect(screen.getByText('pending')).toBeInTheDocument();
      });
    });

    it('should show gray status badge for pending', async () => {
      const mockStatus: QualityGateStatusType = {
        task_id: 1,
        status: 'pending',
        failures: [],
        requires_human_approval: false,
        timestamp: new Date().toISOString(),
      };

      mockFetchQualityGateStatus.mockResolvedValue(mockStatus);

      render(<QualityGateStatus taskId={1} />);

      await waitFor(() => {
        const badge = screen.getByText('pending');
        expect(badge).toHaveClass('bg-muted');
        expect(badge).toHaveClass('text-muted-foreground');
        expect(badge).toHaveClass('border-border');
      });
    });
  });

  describe('Human Approval Badge', () => {
    it('should display human approval badge when required', async () => {
      const mockStatus: QualityGateStatusType = {
        task_id: 1,
        status: 'passed',
        failures: [],
        requires_human_approval: true,
        timestamp: new Date().toISOString(),
      };

      mockFetchQualityGateStatus.mockResolvedValue(mockStatus);

      render(<QualityGateStatus taskId={1} />);

      await waitFor(() => {
        expect(screen.getByText(/Requires Approval/i)).toBeInTheDocument();
      });
    });

    it('should not display human approval badge when not required', async () => {
      const mockStatus: QualityGateStatusType = {
        task_id: 1,
        status: 'passed',
        failures: [],
        requires_human_approval: false,
        timestamp: new Date().toISOString(),
      };

      mockFetchQualityGateStatus.mockResolvedValue(mockStatus);

      render(<QualityGateStatus taskId={1} />);

      await waitFor(() => {
        expect(screen.queryByText(/Requires Approval/i)).not.toBeInTheDocument();
      });
    });
  });

  describe('Manual Trigger Button', () => {
    it('should call trigger API when re-run button clicked', async () => {
      const mockStatus: QualityGateStatusType = {
        task_id: 1,
        status: 'passed',
        failures: [],
        requires_human_approval: false,
        timestamp: new Date().toISOString(),
      };

      mockFetchQualityGateStatus.mockResolvedValue(mockStatus);
      mockTriggerQualityGates.mockResolvedValue({
        task_id: 1,
        status: 'running',
        message: 'Quality gates triggered',
      });

      render(<QualityGateStatus taskId={1} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /Re-run/i })).toBeInTheDocument();
      });

      const button = screen.getByRole('button', { name: /Re-run/i });
      fireEvent.click(button);

      await waitFor(() => {
        expect(mockTriggerQualityGates).toHaveBeenCalledWith({ task_id: 1 });
      });
    });

    it('should refresh status after triggering', async () => {
      const mockStatus: QualityGateStatusType = {
        task_id: 1,
        status: 'passed',
        failures: [],
        requires_human_approval: false,
        timestamp: new Date().toISOString(),
      };

      mockFetchQualityGateStatus.mockResolvedValue(mockStatus);
      mockTriggerQualityGates.mockResolvedValue({
        task_id: 1,
        status: 'running',
        message: 'Quality gates triggered',
      });

      render(<QualityGateStatus taskId={1} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /Re-run/i })).toBeInTheDocument();
      });

      const button = screen.getByRole('button', { name: /Re-run/i });
      fireEvent.click(button);

      await waitFor(() => {
        // Should call fetch twice: once on mount, once after trigger
        expect(mockFetchQualityGateStatus).toHaveBeenCalledTimes(2);
      });
    });

    it('should disable button while triggering', async () => {
      const mockStatus: QualityGateStatusType = {
        task_id: 1,
        status: 'passed',
        failures: [],
        requires_human_approval: false,
        timestamp: new Date().toISOString(),
      };

      mockFetchQualityGateStatus.mockResolvedValue(mockStatus);
      mockTriggerQualityGates.mockImplementation(
        () => new Promise((resolve) => setTimeout(resolve, 100))
      );

      render(<QualityGateStatus taskId={1} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /Re-run/i })).toBeInTheDocument();
      });

      const button = screen.getByRole('button', { name: /Re-run/i });
      fireEvent.click(button);

      // Button should be disabled immediately
      expect(button).toBeDisabled();
    });

    it('should handle trigger error gracefully', async () => {
      const mockStatus: QualityGateStatusType = {
        task_id: 1,
        status: 'passed',
        failures: [],
        requires_human_approval: false,
        timestamp: new Date().toISOString(),
      };

      mockFetchQualityGateStatus.mockResolvedValue(mockStatus);
      mockTriggerQualityGates.mockRejectedValue(new Error('Trigger failed'));

      render(<QualityGateStatus taskId={1} />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /Re-run/i })).toBeInTheDocument();
      });

      const button = screen.getByRole('button', { name: /Re-run/i });
      fireEvent.click(button);

      await waitFor(() => {
        expect(screen.getByText(/Trigger failed/i)).toBeInTheDocument();
      });
    });
  });

  describe('Timestamp Display', () => {
    it('should display last updated timestamp', async () => {
      const timestamp = new Date('2025-11-23T10:00:00Z');
      const mockStatus: QualityGateStatusType = {
        task_id: 1,
        status: 'passed',
        failures: [],
        requires_human_approval: false,
        timestamp: timestamp.toISOString(),
      };

      mockFetchQualityGateStatus.mockResolvedValue(mockStatus);

      render(<QualityGateStatus taskId={1} />);

      await waitFor(() => {
        expect(screen.getByText(/Last updated:/i)).toBeInTheDocument();
      });
    });
  });

  describe('Warning Banner', () => {
    beforeEach(() => {
      // Clear localStorage before each test
      localStorage.clear();
    });

    it('should display warning banner when status is passed with no failures', async () => {
      const mockStatus: QualityGateStatusType = {
        task_id: 123,
        status: 'passed',
        failures: [],
        requires_human_approval: false,
        timestamp: new Date().toISOString(),
      };

      mockFetchQualityGateStatus.mockResolvedValue(mockStatus);

      render(<QualityGateStatus taskId={123} />);

      await waitFor(() => {
        expect(screen.getByText(/Summary Status Only/i)).toBeInTheDocument();
      });

      expect(screen.getByText(/This shows overall status. Individual gates may not have been evaluated yet./i)).toBeInTheDocument();
    });

    it('should not display warning banner when status is failed', async () => {
      const mockStatus: QualityGateStatusType = {
        task_id: 1,
        status: 'failed',
        failures: [
          {
            gate: 'tests',
            reason: 'Test suite failed',
            severity: 'critical',
          },
        ],
        requires_human_approval: false,
        timestamp: new Date().toISOString(),
      };

      mockFetchQualityGateStatus.mockResolvedValue(mockStatus);

      render(<QualityGateStatus taskId={1} />);

      await waitFor(() => {
        expect(screen.getByText('failed')).toBeInTheDocument();
      });

      expect(screen.queryByText(/Summary Status Only/i)).not.toBeInTheDocument();
    });

    it('should not display warning banner when status is running', async () => {
      const mockStatus: QualityGateStatusType = {
        task_id: 1,
        status: 'running',
        failures: [],
        requires_human_approval: false,
        timestamp: new Date().toISOString(),
      };

      mockFetchQualityGateStatus.mockResolvedValue(mockStatus);

      render(<QualityGateStatus taskId={1} />);

      await waitFor(() => {
        expect(screen.getByText('running')).toBeInTheDocument();
      });

      expect(screen.queryByText(/Summary Status Only/i)).not.toBeInTheDocument();
    });

    it('should dismiss warning banner when close button clicked', async () => {
      const mockStatus: QualityGateStatusType = {
        task_id: 123,
        status: 'passed',
        failures: [],
        requires_human_approval: false,
        timestamp: new Date().toISOString(),
      };

      mockFetchQualityGateStatus.mockResolvedValue(mockStatus);

      render(<QualityGateStatus taskId={123} />);

      // Wait for warning banner to appear
      await waitFor(() => {
        expect(screen.getByText(/Summary Status Only/i)).toBeInTheDocument();
      });

      // Find and click dismiss button
      const dismissButton = screen.getByLabelText('Dismiss warning');
      fireEvent.click(dismissButton);

      // Warning banner should be removed
      await waitFor(() => {
        expect(screen.queryByText(/Summary Status Only/i)).not.toBeInTheDocument();
      });
    });

    it('should not show warning banner if previously dismissed', async () => {
      const taskId = 123;
      const mockStatus: QualityGateStatusType = {
        task_id: taskId,
        status: 'passed',
        failures: [],
        requires_human_approval: false,
        timestamp: new Date().toISOString(),
      };

      // Set localStorage to indicate warning was dismissed
      localStorage.setItem(`qualityGates_warning_dismissed_${taskId}`, JSON.stringify(true));

      mockFetchQualityGateStatus.mockResolvedValue(mockStatus);

      render(<QualityGateStatus taskId={taskId} />);

      await waitFor(() => {
        expect(screen.getByText('passed')).toBeInTheDocument();
      });

      // Warning banner should not appear
      expect(screen.queryByText(/Summary Status Only/i)).not.toBeInTheDocument();
    });

    it('should use task-specific localStorage key', async () => {
      const taskId = 456;
      const mockStatus: QualityGateStatusType = {
        task_id: taskId,
        status: 'passed',
        failures: [],
        requires_human_approval: false,
        timestamp: new Date().toISOString(),
      };

      mockFetchQualityGateStatus.mockResolvedValue(mockStatus);

      const setItemSpy = jest.spyOn(Storage.prototype, 'setItem');

      render(<QualityGateStatus taskId={taskId} />);

      // Wait for warning banner to appear
      await waitFor(() => {
        expect(screen.getByText(/Summary Status Only/i)).toBeInTheDocument();
      });

      // Click dismiss button
      const dismissButton = screen.getByLabelText('Dismiss warning');
      fireEvent.click(dismissButton);

      // Verify localStorage key includes task ID
      await waitFor(() => {
        expect(setItemSpy).toHaveBeenCalledWith(
          `qualityGates_warning_dismissed_${taskId}`,
          JSON.stringify(true)
        );
      });

      setItemSpy.mockRestore();
    });

    it('should reset warning dismissal state when switching to a task with no stored value', async () => {
      const taskId1 = 100;
      const taskId2 = 200;

      const mockStatus: QualityGateStatusType = {
        task_id: taskId1,
        status: 'passed',
        failures: [],
        requires_human_approval: false,
        timestamp: new Date().toISOString(),
      };

      // Set dismissal for task 100
      localStorage.setItem(`qualityGates_warning_dismissed_${taskId1}`, JSON.stringify(true));

      mockFetchQualityGateStatus.mockResolvedValue(mockStatus);

      const { rerender } = render(<QualityGateStatus taskId={taskId1} />);

      // Verify warning is not shown for task 100 (dismissed)
      await waitFor(() => {
        expect(screen.getByText('passed')).toBeInTheDocument();
      });
      expect(screen.queryByText(/Summary Status Only/i)).not.toBeInTheDocument();

      // Switch to task 200 (no stored dismissal)
      const mockStatus2: QualityGateStatusType = {
        task_id: taskId2,
        status: 'passed',
        failures: [],
        requires_human_approval: false,
        timestamp: new Date().toISOString(),
      };
      mockFetchQualityGateStatus.mockResolvedValue(mockStatus2);

      rerender(<QualityGateStatus taskId={taskId2} />);

      // Warning should now appear for task 200
      await waitFor(() => {
        expect(screen.getByText(/Summary Status Only/i)).toBeInTheDocument();
      });
    });
  });
});
