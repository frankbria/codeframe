/**
 * Test suite for quality gate utility functions
 * Target: 100% coverage for pure utility functions
 */

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
    it('should return correct icon for "tests" gate', () => {
      expect(getGateIcon('tests')).toBe('🧪');
    });

    it('should return correct icon for "coverage" gate', () => {
      expect(getGateIcon('coverage')).toBe('📊');
    });

    it('should return correct icon for "type_check" gate (backend naming)', () => {
      expect(getGateIcon('type_check')).toBe('📝');
    });

    it('should return correct icon for "type-check" gate (E2E naming)', () => {
      expect(getGateIcon('type-check')).toBe('📝');
    });

    it('should return correct icon for "linting" gate (backend naming)', () => {
      expect(getGateIcon('linting')).toBe('✨');
    });

    it('should return correct icon for "lint" gate (E2E naming)', () => {
      expect(getGateIcon('lint')).toBe('✨');
    });

    it('should return correct icon for "code_review" gate (backend naming)', () => {
      expect(getGateIcon('code_review')).toBe('🔍');
    });

    it('should return correct icon for "review" gate (E2E naming)', () => {
      expect(getGateIcon('review')).toBe('🔍');
    });

    it('should return default icon for unknown gate type', () => {
      expect(getGateIcon('unknown_gate')).toBe('⚙️');
    });

    it('should return default icon for empty string', () => {
      expect(getGateIcon('')).toBe('⚙️');
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
    it('should return checkmark for "passed" status', () => {
      expect(getStatusIcon('passed')).toBe('✅');
    });

    it('should return X for "failed" status', () => {
      expect(getStatusIcon('failed')).toBe('❌');
    });

    it('should return hourglass for "running" status', () => {
      expect(getStatusIcon('running')).toBe('⏳');
    });

    it('should return pause icon for "pending" status', () => {
      expect(getStatusIcon('pending')).toBe('⏸️');
    });

    it('should return question mark for null status', () => {
      expect(getStatusIcon(null)).toBe('❓');
    });

    it('should return question mark for undefined status', () => {
      expect(getStatusIcon(undefined as any)).toBe('❓');
    });

    it('should return question mark for unknown status', () => {
      expect(getStatusIcon('unknown' as any)).toBe('❓');
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
    it('should accept all valid gate types', () => {
      const validTypes: GateTypeE2E[] = ['tests', 'coverage', 'type-check', 'lint', 'review'];
      validTypes.forEach((type) => {
        expect(() => getGateIcon(type)).not.toThrow();
        expect(() => getGateName(type)).not.toThrow();
      });
    });

    it('should accept all valid status values', () => {
      const validStatuses: QualityGateStatusValue[] = ['passed', 'failed', 'running', 'pending', null];
      validStatuses.forEach((status) => {
        expect(() => getStatusIcon(status)).not.toThrow();
        expect(() => getStatusClasses(status)).not.toThrow();
      });
    });

    it('should handle string inputs gracefully', () => {
      // Test that string inputs don't cause runtime errors
      expect(() => getGateIcon('any-string')).not.toThrow();
      expect(() => getGateName('any-string')).not.toThrow();
      expect(() => getSeverityClasses('any-string')).not.toThrow();
    });
  });

  describe('Consistency', () => {
    it('should return consistent results for the same input', () => {
      expect(getGateIcon('tests')).toBe(getGateIcon('tests'));
      expect(getGateName('coverage')).toBe(getGateName('coverage'));
      expect(getStatusClasses('passed')).toBe(getStatusClasses('passed'));
      expect(getStatusIcon('failed')).toBe(getStatusIcon('failed'));
      expect(getSeverityClasses('critical')).toBe(getSeverityClasses('critical'));
    });

    it('should handle both naming conventions for gates', () => {
      // Backend (snake_case) and E2E (kebab-case) should return same results
      expect(getGateIcon('type_check')).toBe(getGateIcon('type-check'));
      expect(getGateName('type_check')).toBe(getGateName('type-check'));

      expect(getGateIcon('linting')).toBe(getGateIcon('lint'));
      expect(getGateName('linting')).toBe(getGateName('lint'));

      expect(getGateIcon('code_review')).toBe(getGateIcon('review'));
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
      expect(getGateIcon('  tests  ')).toBe('⚙️'); // Whitespace makes it unmatched
      expect(getGateName('  tests  ')).toBe('  tests  '); // Returns as-is
    });

    it('should handle unicode characters', () => {
      expect(() => getGateIcon('测试')).not.toThrow();
      expect(() => getGateName('测试')).not.toThrow();
    });
  });
});
