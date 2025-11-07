/**
 * Validation Tests
 * Tests T119 and T120: Validation function behavior
 */

import { validateAgentCount, validateActivitySize } from '@/lib/validation';

describe('Validation Functions', () => {
  // Save original console.warn and NODE_ENV
  const originalWarn = console.warn;
  const originalNodeEnv = process.env.NODE_ENV;
  let warnSpy: jest.SpyInstance;

  beforeEach(() => {
    // Set NODE_ENV to development for warnings to appear
    process.env.NODE_ENV = 'development';
    // Mock console.warn to capture warnings
    warnSpy = jest.spyOn(console, 'warn').mockImplementation(() => {});
  });

  afterEach(() => {
    // Restore original console.warn and NODE_ENV
    warnSpy.mockRestore();
    process.env.NODE_ENV = originalNodeEnv;
  });

  describe('T119: validateAgentCount', () => {
    it('should return true when agent count is within limit (10 or fewer)', () => {
      expect(validateAgentCount(1)).toBe(true);
      expect(validateAgentCount(5)).toBe(true);
      expect(validateAgentCount(10)).toBe(true);
      expect(warnSpy).not.toHaveBeenCalled();
    });

    it('should return false and warn when agent count exceeds 10', () => {
      const result = validateAgentCount(11);

      expect(result).toBe(false);
      expect(warnSpy).toHaveBeenCalledWith(
        expect.stringContaining('[AgentState] Agent count (11) exceeds recommended limit of 10')
      );
    });

    it('should warn for agent counts significantly over limit', () => {
      validateAgentCount(15);

      expect(warnSpy).toHaveBeenCalledWith(
        expect.stringContaining('Agent count (15) exceeds recommended limit')
      );
    });

    it('should include performance warning message', () => {
      validateAgentCount(12);

      expect(warnSpy).toHaveBeenCalledWith(
        expect.stringContaining('Performance may degrade')
      );
    });
  });

  describe('T120: validateActivitySize', () => {
    it('should return true when activity size is within limit (50 or fewer)', () => {
      expect(validateActivitySize(1)).toBe(true);
      expect(validateActivitySize(25)).toBe(true);
      expect(validateActivitySize(50)).toBe(true);
      expect(warnSpy).not.toHaveBeenCalled();
    });

    it('should return false and warn when activity size exceeds 50', () => {
      const result = validateActivitySize(51);

      expect(result).toBe(false);
      expect(warnSpy).toHaveBeenCalledWith(
        expect.stringContaining('[AgentState] Activity feed size (51) exceeds maximum of 50')
      );
    });

    it('should warn for activity sizes significantly over limit', () => {
      validateActivitySize(100);

      expect(warnSpy).toHaveBeenCalledWith(
        expect.stringContaining('Activity feed size (100) exceeds maximum')
      );
    });

    it('should include pruning reminder in warning message', () => {
      validateActivitySize(55);

      expect(warnSpy).toHaveBeenCalledWith(
        expect.stringContaining('Older items should have been pruned')
      );
    });
  });

  describe('Edge Cases', () => {
    it('should handle zero agent count', () => {
      expect(validateAgentCount(0)).toBe(true);
      expect(warnSpy).not.toHaveBeenCalled();
    });

    it('should handle zero activity size', () => {
      expect(validateActivitySize(0)).toBe(true);
      expect(warnSpy).not.toHaveBeenCalled();
    });

    it('should handle boundary values correctly', () => {
      // At limit - no warning
      validateAgentCount(10);
      validateActivitySize(50);
      expect(warnSpy).not.toHaveBeenCalled();

      // Just over limit - warning
      validateAgentCount(11);
      validateActivitySize(51);
      expect(warnSpy).toHaveBeenCalledTimes(2);
    });
  });
});
