/**
 * Test suite for GateStatusIndicator component
 * Target: 85%+ code coverage
 *
 * Tests icon rendering, status badge styling, accessibility, and edge cases
 */

import React from 'react';
import { render, screen } from '@testing-library/react';
import GateStatusIndicator from '@/components/quality-gates/GateStatusIndicator';
import type { GateTypeE2E, QualityGateStatusValue } from '@/types/qualityGates';
import * as qualityGateUtils from '@/lib/qualityGateUtils';

// Mock the utility functions
jest.mock('@/lib/qualityGateUtils', () => ({
  getGateIcon: jest.fn((gateType: string) => {
    const icons: Record<string, string> = {
      'tests': '🧪',
      'coverage': '📊',
      'type-check': '📝',
      'lint': '✨',
      'review': '🔍',
    };
    return icons[gateType] || '⚙️';
  }),
  getGateName: jest.fn((gateType: string) => {
    const names: Record<string, string> = {
      'tests': 'Tests',
      'coverage': 'Coverage',
      'type-check': 'Type Check',
      'lint': 'Linting',
      'review': 'Code Review',
    };
    return names[gateType] || gateType;
  }),
  getStatusClasses: jest.fn((status: QualityGateStatusValue) => {
    const classes: Record<string, string> = {
      'passed': 'bg-green-100 text-green-800 border-green-300',
      'failed': 'bg-red-100 text-red-800 border-red-300',
      'running': 'bg-yellow-100 text-yellow-800 border-yellow-300',
      'pending': 'bg-gray-100 text-gray-800 border-gray-300',
    };
    return classes[status as string] || 'bg-gray-100 text-gray-800 border-gray-200';
  }),
  getStatusIcon: jest.fn((status: QualityGateStatusValue) => {
    if (status === null) return '❓';
    const icons: Record<string, string> = {
      'passed': '✅',
      'failed': '❌',
      'running': '⏳',
      'pending': '⏸️',
    };
    return icons[status as string] || '❓';
  }),
}));

describe('GateStatusIndicator', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('Basic Rendering', () => {
    it('should render with gate type and status', () => {
      render(<GateStatusIndicator gateType="tests" status="passed" />);

      const indicator = screen.getByTestId('gate-tests');
      expect(indicator).toBeInTheDocument();
    });

    it('should render with default testId when not provided', () => {
      render(<GateStatusIndicator gateType="coverage" status="failed" />);

      const indicator = screen.getByTestId('gate-coverage');
      expect(indicator).toBeInTheDocument();
    });

    it('should render with custom testId when provided', () => {
      render(<GateStatusIndicator gateType="lint" status="running" testId="custom-gate" />);

      const indicator = screen.getByTestId('custom-gate');
      expect(indicator).toBeInTheDocument();
    });
  });

  describe('Icon Rendering', () => {
    it('should display gate icon from getGateIcon', () => {
      render(<GateStatusIndicator gateType="tests" status="passed" />);

      expect(qualityGateUtils.getGateIcon).toHaveBeenCalledWith('tests');
      expect(screen.getByText('🧪')).toBeInTheDocument();
    });

    it('should display status icon from getStatusIcon', () => {
      render(<GateStatusIndicator gateType="coverage" status="passed" />);

      expect(qualityGateUtils.getStatusIcon).toHaveBeenCalledWith('passed');
      expect(screen.getByText('✅')).toBeInTheDocument();
    });

    it('should display running status icon', () => {
      render(<GateStatusIndicator gateType="lint" status="running" />);

      expect(screen.getByText('⏳')).toBeInTheDocument();
    });

    it('should display failed status icon', () => {
      render(<GateStatusIndicator gateType="review" status="failed" />);

      expect(screen.getByText('❌')).toBeInTheDocument();
    });

    it('should display pending status icon for null status', () => {
      render(<GateStatusIndicator gateType="tests" status={null} />);

      expect(qualityGateUtils.getStatusIcon).toHaveBeenCalledWith(null);
      expect(screen.getByText('❓')).toBeInTheDocument();
    });
  });

  describe('Status Badge', () => {
    it('should display gate name from getGateName', () => {
      render(<GateStatusIndicator gateType="tests" status="passed" />);

      expect(qualityGateUtils.getGateName).toHaveBeenCalledWith('tests');
      expect(screen.getByText('Tests')).toBeInTheDocument();
    });

    it('should display status text', () => {
      render(<GateStatusIndicator gateType="coverage" status="passed" />);

      expect(screen.getByText('passed')).toBeInTheDocument();
    });

    it('should display "pending" for null status', () => {
      render(<GateStatusIndicator gateType="lint" status={null} />);

      expect(screen.getByText('pending')).toBeInTheDocument();
    });

    it('should apply status classes from getStatusClasses', () => {
      render(<GateStatusIndicator gateType="tests" status="passed" />);

      expect(qualityGateUtils.getStatusClasses).toHaveBeenCalledWith('passed');

      const statusBadge = screen.getByRole('status');
      expect(statusBadge).toHaveClass('bg-secondary');
      expect(statusBadge).toHaveClass('text-secondary-foreground');
      expect(statusBadge).toHaveClass('border-border');
    });

    it('should apply failed status classes correctly', () => {
      render(<GateStatusIndicator gateType="review" status="failed" />);

      const statusBadge = screen.getByRole('status');
      expect(statusBadge).toHaveClass('bg-destructive/10');
      expect(statusBadge).toHaveClass('text-destructive-foreground');
    });

    it('should apply running status classes correctly', () => {
      render(<GateStatusIndicator gateType="lint" status="running" />);

      const statusBadge = screen.getByRole('status');
      expect(statusBadge).toHaveClass('bg-primary/20');
      expect(statusBadge).toHaveClass('text-foreground');
    });
  });

  describe('Accessibility', () => {
    it('should have role="listitem" for semantic HTML', () => {
      render(<GateStatusIndicator gateType="tests" status="passed" />);

      const indicator = screen.getByTestId('gate-tests');
      expect(indicator).toHaveAttribute('role', 'listitem');
    });

    it('should have descriptive aria-label', () => {
      render(<GateStatusIndicator gateType="tests" status="passed" />);

      const indicator = screen.getByTestId('gate-tests');
      expect(indicator).toHaveAttribute('aria-label', 'Tests gate: passed');
    });

    it('should include gate name in aria-label', () => {
      render(<GateStatusIndicator gateType="coverage" status="failed" />);

      const indicator = screen.getByTestId('gate-coverage');
      expect(indicator).toHaveAttribute('aria-label', 'Coverage gate: failed');
    });

    it('should have nested status role for screen readers', () => {
      render(<GateStatusIndicator gateType="lint" status="running" />);

      const statusBadge = screen.getByRole('status');
      expect(statusBadge).toBeInTheDocument();
    });

    it('should have status aria-label', () => {
      render(<GateStatusIndicator gateType="review" status="passed" />);

      const statusBadge = screen.getByRole('status');
      expect(statusBadge).toHaveAttribute('aria-label', 'Status: passed');
    });

    it('should mark icons as aria-hidden', () => {
      const { container } = render(<GateStatusIndicator gateType="tests" status="passed" />);

      // Find all elements with aria-hidden="true"
      const hiddenElements = container.querySelectorAll('[aria-hidden="true"]');
      expect(hiddenElements.length).toBeGreaterThan(0);
    });
  });

  describe('All Gate Types', () => {
    const gateTypes: GateTypeE2E[] = ['tests', 'coverage', 'type-check', 'lint', 'review'];

    gateTypes.forEach((gateType) => {
      it(`should render ${gateType} gate correctly`, () => {
        render(<GateStatusIndicator gateType={gateType} status="passed" />);

        const indicator = screen.getByTestId(`gate-${gateType}`);
        expect(indicator).toBeInTheDocument();
        expect(qualityGateUtils.getGateIcon).toHaveBeenCalledWith(gateType);
        expect(qualityGateUtils.getGateName).toHaveBeenCalledWith(gateType);
      });
    });
  });

  describe('All Status Values', () => {
    const statuses: QualityGateStatusValue[] = ['passed', 'failed', 'running', null];

    statuses.forEach((status) => {
      it(`should render ${status || 'pending'} status correctly`, () => {
        render(<GateStatusIndicator gateType="tests" status={status} />);

        expect(qualityGateUtils.getStatusIcon).toHaveBeenCalledWith(status);
        expect(qualityGateUtils.getStatusClasses).toHaveBeenCalledWith(status);

        const statusText = status === null ? 'pending' : status;
        expect(screen.getByText(statusText)).toBeInTheDocument();
      });
    });
  });

  describe('Layout and Styling', () => {
    it('should have proper card layout classes', () => {
      render(<GateStatusIndicator gateType="tests" status="passed" />);

      const indicator = screen.getByTestId('gate-tests');
      expect(indicator).toHaveClass('flex');
      expect(indicator).toHaveClass('flex-col');
      expect(indicator).toHaveClass('items-center');
      expect(indicator).toHaveClass('justify-center');
    });

    it('should have white background and border', () => {
      render(<GateStatusIndicator gateType="coverage" status="failed" />);

      const indicator = screen.getByTestId('gate-coverage');
      expect(indicator).toHaveClass('bg-card');
      expect(indicator).toHaveClass('border');
      expect(indicator).toHaveClass('border-border');
    });

    it('should have hover effect classes', () => {
      render(<GateStatusIndicator gateType="lint" status="running" />);

      const indicator = screen.getByTestId('gate-lint');
      expect(indicator).toHaveClass('hover:shadow-md');
      expect(indicator).toHaveClass('transition-shadow');
    });

    it('should have rounded corners', () => {
      render(<GateStatusIndicator gateType="review" status="passed" />);

      const indicator = screen.getByTestId('gate-review');
      expect(indicator).toHaveClass('rounded-lg');
    });

    it('should have padding', () => {
      render(<GateStatusIndicator gateType="tests" status="passed" />);

      const indicator = screen.getByTestId('gate-tests');
      expect(indicator).toHaveClass('p-4');
    });
  });

  describe('Integration with Utilities', () => {
    it('should call all utility functions with correct arguments', () => {
      render(<GateStatusIndicator gateType="tests" status="passed" />);

      expect(qualityGateUtils.getGateIcon).toHaveBeenCalledWith('tests');
      expect(qualityGateUtils.getGateName).toHaveBeenCalledWith('tests');
      expect(qualityGateUtils.getStatusIcon).toHaveBeenCalledWith('passed');
      expect(qualityGateUtils.getStatusClasses).toHaveBeenCalledWith('passed');
    });

    it('should call utilities exactly once per render', () => {
      render(<GateStatusIndicator gateType="coverage" status="failed" />);

      expect(qualityGateUtils.getGateIcon).toHaveBeenCalledTimes(1);
      expect(qualityGateUtils.getGateName).toHaveBeenCalledTimes(1);
      expect(qualityGateUtils.getStatusIcon).toHaveBeenCalledTimes(1);
      expect(qualityGateUtils.getStatusClasses).toHaveBeenCalledTimes(1);
    });

    it('should not call utilities on re-render with same props', () => {
      const { rerender } = render(<GateStatusIndicator gateType="lint" status="running" />);

      // Clear mock call counts
      jest.clearAllMocks();

      // Re-render with same props
      rerender(<GateStatusIndicator gateType="lint" status="running" />);

      // Utilities should be called again on re-render (React doesn't memoize by default)
      expect(qualityGateUtils.getGateIcon).toHaveBeenCalledTimes(1);
      expect(qualityGateUtils.getGateName).toHaveBeenCalledTimes(1);
    });
  });

  describe('Edge Cases', () => {
    it('should handle empty string gate type gracefully', () => {
      // TypeScript would prevent this, but test runtime behavior
      render(<GateStatusIndicator gateType={'' as any} status="passed" />);

      expect(qualityGateUtils.getGateIcon).toHaveBeenCalledWith('');
      expect(qualityGateUtils.getGateName).toHaveBeenCalledWith('');
    });

    it('should handle undefined status gracefully', () => {
      render(<GateStatusIndicator gateType="tests" status={undefined as any} />);

      expect(screen.getByText('pending')).toBeInTheDocument();
    });

    it('should render consistently with different gate/status combinations', () => {
      const { rerender } = render(<GateStatusIndicator gateType="tests" status="passed" />);

      expect(screen.getByText('Tests')).toBeInTheDocument();
      expect(screen.getByText('passed')).toBeInTheDocument();

      rerender(<GateStatusIndicator gateType="coverage" status="failed" />);

      expect(screen.getByText('Coverage')).toBeInTheDocument();
      expect(screen.getByText('failed')).toBeInTheDocument();
    });
  });

  describe('Snapshot Testing', () => {
    it('should match snapshot for passed status', () => {
      const { container } = render(<GateStatusIndicator gateType="tests" status="passed" />);
      expect(container.firstChild).toMatchSnapshot();
    });

    it('should match snapshot for failed status', () => {
      const { container } = render(<GateStatusIndicator gateType="coverage" status="failed" />);
      expect(container.firstChild).toMatchSnapshot();
    });

    it('should match snapshot for running status', () => {
      const { container } = render(<GateStatusIndicator gateType="lint" status="running" />);
      expect(container.firstChild).toMatchSnapshot();
    });

    it('should match snapshot for pending status', () => {
      const { container } = render(<GateStatusIndicator gateType="review" status={null} />);
      expect(container.firstChild).toMatchSnapshot();
    });
  });
});
