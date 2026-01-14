/**
 * Test suite for quality gate utility functions
 * Updated for emoji-to-Hugeicons migration: functions now return JSX elements
 */

import { render, screen } from '@testing-library/react';
import {
  getGateIcon,
  getGateName,
  getStatusClasses,
  getStatusIcon,
  getSeverityClasses,
} from '@/lib/qualityGateUtils';
import type { GateTypeE2E, QualityGateStatusValue } from '@/types/qualityGates';

describe('qualityGateUtils', () => {
  describe('getGateIcon', () => {
    it('should return TestTube01Icon for "tests" gate', () => {
      render(<div data-testid="icon-container">{getGateIcon('tests')}</div>);
      expect(screen.getByTestId('TestTube01Icon')).toBeInTheDocument();
    });

    it('should return ChartBarLineIcon for "coverage" gate', () => {
      render(<div data-testid="icon-container">{getGateIcon('coverage')}</div>);
      expect(screen.getByTestId('ChartBarLineIcon')).toBeInTheDocument();
    });

    it('should return FileEditIcon for "type_check" gate (backend naming)', () => {
      render(<div data-testid="icon-container">{getGateIcon('type_check')}</div>);
      expect(screen.getByTestId('FileEditIcon')).toBeInTheDocument();
    });

    it('should return FileEditIcon for "type-check" gate (E2E naming)', () => {
      render(<div data-testid="icon-container">{getGateIcon('type-check')}</div>);
      expect(screen.getByTestId('FileEditIcon')).toBeInTheDocument();
    });

    it('should return SparklesIcon for "linting" gate (backend naming)', () => {
      render(<div data-testid="icon-container">{getGateIcon('linting')}</div>);
      expect(screen.getByTestId('SparklesIcon')).toBeInTheDocument();
    });

    it('should return SparklesIcon for "lint" gate (E2E naming)', () => {
      render(<div data-testid="icon-container">{getGateIcon('lint')}</div>);
      expect(screen.getByTestId('SparklesIcon')).toBeInTheDocument();
    });

    it('should return Search01Icon for "code_review" gate (backend naming)', () => {
      render(<div data-testid="icon-container">{getGateIcon('code_review')}</div>);
      expect(screen.getByTestId('Search01Icon')).toBeInTheDocument();
    });

    it('should return Search01Icon for "review" gate (E2E naming)', () => {
      render(<div data-testid="icon-container">{getGateIcon('review')}</div>);
      expect(screen.getByTestId('Search01Icon')).toBeInTheDocument();
    });

    it('should return default Settings01Icon for unknown gate type', () => {
      render(<div data-testid="icon-container">{getGateIcon('unknown_gate')}</div>);
      expect(screen.getByTestId('Settings01Icon')).toBeInTheDocument();
    });

    it('should return default Settings01Icon for empty string', () => {
      render(<div data-testid="icon-container">{getGateIcon('')}</div>);
      expect(screen.getByTestId('Settings01Icon')).toBeInTheDocument();
    });
  });

  describe('getGateName', () => {
    it('should return "Tests" for "tests" gate', () => {
      expect(getGateName('tests')).toBe('Tests');
    });

    it('should return "Coverage" for "coverage" gate', () => {
      expect(getGateName('coverage')).toBe('Coverage');
    });

    it('should return "Type Check" for "type_check" gate (backend naming)', () => {
      expect(getGateName('type_check')).toBe('Type Check');
    });

    it('should return "Type Check" for "type-check" gate (E2E naming)', () => {
      expect(getGateName('type-check')).toBe('Type Check');
    });

    it('should return "Linting" for "linting" gate (backend naming)', () => {
      expect(getGateName('linting')).toBe('Linting');
    });

    it('should return "Linting" for "lint" gate (E2E naming)', () => {
      expect(getGateName('lint')).toBe('Linting');
    });

    it('should return "Code Review" for "code_review" gate (backend naming)', () => {
      expect(getGateName('code_review')).toBe('Code Review');
    });

    it('should return "Code Review" for "review" gate (E2E naming)', () => {
      expect(getGateName('review')).toBe('Code Review');
    });

    it('should return original string for unknown gate type', () => {
      expect(getGateName('custom_gate')).toBe('custom_gate');
    });

    it('should return empty string for empty input', () => {
      expect(getGateName('')).toBe('');
    });
  });

  describe('getStatusClasses', () => {
    it('should return secondary classes for "passed" status', () => {
      const classes = getStatusClasses('passed');
      expect(classes).toContain('bg-secondary');
      expect(classes).toContain('text-secondary-foreground');
      expect(classes).toContain('border-border');
    });

    it('should return destructive classes for "failed" status', () => {
      const classes = getStatusClasses('failed');
      expect(classes).toContain('bg-destructive');
      expect(classes).toContain('text-destructive-foreground');
      expect(classes).toContain('border-destructive');
    });

    it('should return primary classes for "running" status', () => {
      const classes = getStatusClasses('running');
      expect(classes).toContain('bg-primary/20');
      expect(classes).toContain('text-foreground');
      expect(classes).toContain('border-border');
    });

    it('should return muted classes for "pending" status', () => {
      const classes = getStatusClasses('pending');
      expect(classes).toContain('bg-muted');
      expect(classes).toContain('text-muted-foreground');
      expect(classes).toContain('border-border');
    });

    it('should return default muted classes for null status', () => {
      const classes = getStatusClasses(null);
      expect(classes).toContain('bg-muted');
      expect(classes).toContain('text-muted-foreground');
      expect(classes).toContain('border-border');
    });

    it('should return default muted classes for undefined status', () => {
      const classes = getStatusClasses(undefined as any);
      expect(classes).toContain('bg-muted');
      expect(classes).toContain('text-muted-foreground');
      expect(classes).toContain('border-border');
    });
  });

  describe('getStatusIcon', () => {
    it('should return CheckmarkCircle01Icon for "passed" status', () => {
      render(<div data-testid="icon-container">{getStatusIcon('passed')}</div>);
      expect(screen.getByTestId('CheckmarkCircle01Icon')).toBeInTheDocument();
    });

    it('should return Cancel01Icon for "failed" status', () => {
      render(<div data-testid="icon-container">{getStatusIcon('failed')}</div>);
      expect(screen.getByTestId('Cancel01Icon')).toBeInTheDocument();
    });

    it('should return Loading03Icon for "running" status', () => {
      render(<div data-testid="icon-container">{getStatusIcon('running')}</div>);
      expect(screen.getByTestId('Loading03Icon')).toBeInTheDocument();
    });

    it('should return PauseIcon for "pending" status', () => {
      render(<div data-testid="icon-container">{getStatusIcon('pending')}</div>);
      expect(screen.getByTestId('PauseIcon')).toBeInTheDocument();
    });

    it('should return HelpCircleIcon for null status', () => {
      render(<div data-testid="icon-container">{getStatusIcon(null)}</div>);
      expect(screen.getByTestId('HelpCircleIcon')).toBeInTheDocument();
    });

    it('should return HelpCircleIcon for undefined status', () => {
      render(<div data-testid="icon-container">{getStatusIcon(undefined as any)}</div>);
      expect(screen.getByTestId('HelpCircleIcon')).toBeInTheDocument();
    });

    it('should return HelpCircleIcon for unknown status', () => {
      render(<div data-testid="icon-container">{getStatusIcon('unknown' as any)}</div>);
      expect(screen.getByTestId('HelpCircleIcon')).toBeInTheDocument();
    });
  });

  describe('getSeverityClasses', () => {
    it('should return destructive classes for "critical" severity', () => {
      const classes = getSeverityClasses('critical');
      expect(classes).toContain('bg-destructive');
      expect(classes).toContain('text-destructive-foreground');
      expect(classes).toContain('border-destructive');
    });

    it('should return destructive/80 classes for "high" severity', () => {
      const classes = getSeverityClasses('high');
      expect(classes).toContain('bg-destructive/80');
      expect(classes).toContain('text-destructive-foreground');
      expect(classes).toContain('border-destructive');
    });

    it('should return muted classes for "medium" severity', () => {
      const classes = getSeverityClasses('medium');
      expect(classes).toContain('bg-muted');
      expect(classes).toContain('text-foreground');
      expect(classes).toContain('border-border');
    });

    it('should return secondary classes for "low" severity', () => {
      const classes = getSeverityClasses('low');
      expect(classes).toContain('bg-secondary');
      expect(classes).toContain('text-secondary-foreground');
      expect(classes).toContain('border-border');
    });

    it('should return default muted classes for unknown severity', () => {
      const classes = getSeverityClasses('unknown');
      expect(classes).toContain('bg-muted');
      expect(classes).toContain('text-muted-foreground');
      expect(classes).toContain('border-border');
    });

    it('should return default muted classes for empty string', () => {
      const classes = getSeverityClasses('');
      expect(classes).toContain('bg-muted');
      expect(classes).toContain('text-muted-foreground');
      expect(classes).toContain('border-border');
    });
  });

  describe('Type Safety', () => {
    it('should accept all valid gate types without throwing', () => {
      const validTypes: GateTypeE2E[] = ['tests', 'coverage', 'type-check', 'lint', 'review'];
      validTypes.forEach((type) => {
        expect(() => getGateIcon(type)).not.toThrow();
        expect(() => getGateName(type)).not.toThrow();
      });
    });

    it('should accept all valid status values without throwing', () => {
      const validStatuses: QualityGateStatusValue[] = ['passed', 'failed', 'running', 'pending', null];
      validStatuses.forEach((status) => {
        expect(() => getStatusIcon(status)).not.toThrow();
        expect(() => getStatusClasses(status)).not.toThrow();
      });
    });

    it('should handle string inputs gracefully', () => {
      expect(() => getGateIcon('any-string')).not.toThrow();
      expect(() => getGateName('any-string')).not.toThrow();
      expect(() => getSeverityClasses('any-string')).not.toThrow();
    });
  });

  describe('Consistency', () => {
    it('should return consistent class strings for the same input', () => {
      expect(getGateName('coverage')).toBe(getGateName('coverage'));
      expect(getStatusClasses('passed')).toBe(getStatusClasses('passed'));
      expect(getSeverityClasses('critical')).toBe(getSeverityClasses('critical'));
    });

    it('should handle both naming conventions for gates', () => {
      expect(getGateName('type_check')).toBe(getGateName('type-check'));
      expect(getGateName('linting')).toBe(getGateName('lint'));
      expect(getGateName('code_review')).toBe(getGateName('review'));
    });
  });

  describe('Edge Cases', () => {
    it('should handle special characters in gate names', () => {
      expect(() => getGateIcon('test@#$%')).not.toThrow();
      expect(() => getGateName('test@#$%')).not.toThrow();
    });

    it('should handle very long gate names', () => {
      const longName = 'a'.repeat(1000);
      expect(() => getGateIcon(longName)).not.toThrow();
      expect(() => getGateName(longName)).not.toThrow();
    });

    it('should handle whitespace in inputs', () => {
      render(<div data-testid="icon-container">{getGateIcon('  tests  ')}</div>);
      expect(screen.getByTestId('Settings01Icon')).toBeInTheDocument();
      expect(getGateName('  tests  ')).toBe('  tests  ');
    });

    it('should handle unicode characters', () => {
      expect(() => getGateIcon('测试')).not.toThrow();
      expect(() => getGateName('测试')).not.toThrow();
    });
  });
});
