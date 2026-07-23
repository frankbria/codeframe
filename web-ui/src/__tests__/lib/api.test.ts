import { normalizeErrorDetail } from '@/lib/api';

describe('api client', () => {
  describe('normalizeErrorDetail', () => {
    it('returns string detail as-is', () => {
      const result = normalizeErrorDetail('Resource not found', 'fallback');
      expect(result).toBe('Resource not found');
    });

    it('joins array of validation errors into string', () => {
      const validationErrors = [
        { msg: 'field required', loc: ['body', 'name'] },
        { msg: 'invalid format', loc: ['body', 'email'] },
      ];
      const result = normalizeErrorDetail(validationErrors, 'fallback');
      expect(result).toBe('field required; invalid format');
    });

    it('handles single validation error in array', () => {
      const validationErrors = [{ msg: 'value is not a valid integer' }];
      const result = normalizeErrorDetail(validationErrors, 'fallback');
      expect(result).toBe('value is not a valid integer');
    });

    it('uses fallback when detail is undefined', () => {
      const result = normalizeErrorDetail(undefined, 'Network Error');
      expect(result).toBe('Network Error');
    });

    it('uses fallback when detail is empty string', () => {
      const result = normalizeErrorDetail('', 'Default message');
      expect(result).toBe('Default message');
    });

    it('uses default message when both detail and fallback are empty', () => {
      const result = normalizeErrorDetail(undefined, '');
      expect(result).toBe('An error occurred');
    });

    it('handles empty validation error array', () => {
      const result = normalizeErrorDetail([], 'fallback');
      expect(result).toBe('');
    });

    it('handles validation errors with only msg property', () => {
      const validationErrors = [{ msg: 'error 1' }, { msg: 'error 2' }];
      const result = normalizeErrorDetail(validationErrors, 'fallback');
      expect(result).toBe('error 1; error 2');
    });

    it('combines error and detail from structured api_error object', () => {
      const structuredError = { error: 'Cannot execute', code: 'INVALID_STATE', detail: 'No tasks ready' };
      const result = normalizeErrorDetail(structuredError, 'fallback');
      expect(result).toBe('Cannot execute: No tasks ready');
    });

    it('falls back to detail when structured error has no error field', () => {
      const structuredError = { code: 'NOT_FOUND', detail: 'Task not found' };
      const result = normalizeErrorDetail(structuredError, 'fallback');
      expect(result).toBe('Task not found');
    });

    it('uses fallback when structured error has no error or detail', () => {
      const structuredError = { code: 'UNKNOWN' };
      const result = normalizeErrorDetail(structuredError, 'Something went wrong');
      expect(result).toBe('Something went wrong');
    });
  });
});
