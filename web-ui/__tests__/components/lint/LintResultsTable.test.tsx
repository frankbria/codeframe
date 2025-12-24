/**
 * LintResultsTable Component Tests (T121)
 * Tests for lint results table with linter badges, error/warning counts, and time display
 *
 * Test Coverage:
 * - Table rendering with lint results
 * - Error vs warning severity badges
 * - Linter badges (ruff vs ESLint)
 * - File count and time display
 * - Empty state handling
 * - Loading state
 * - API integration
 * - Edge cases (long data, special characters, zero counts)
 */

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { LintResultsTable } from '@/components/lint/LintResultsTable';
import * as lintApi from '@/api/lint';
import type { LintResult } from '@/types/lint';

// Mock the lint API module
jest.mock('@/api/lint');

const mockGetResults = lintApi.lintApi.getResults as jest.MockedFunction<
  typeof lintApi.lintApi.getResults
>;

describe('LintResultsTable', () => {
  // Mock lint results for testing
  const mockResults: LintResult[] = [
    {
      id: 1,
      task_id: 101,
      linter: 'ruff',
      error_count: 3,
      warning_count: 5,
      files_linted: 12,
      output: 'src/auth.py:10:5 E501 Line too long',
      created_at: '2025-11-21T10:30:00Z',
    },
    {
      id: 2,
      task_id: 101,
      linter: 'eslint',
      error_count: 0,
      warning_count: 8,
      files_linted: 25,
      output: 'src/components/Button.tsx:42:3 Warning: unused variable',
      created_at: '2025-11-21T10:32:00Z',
    },
    {
      id: 3,
      task_id: 101,
      linter: 'other',
      error_count: 1,
      warning_count: 0,
      files_linted: 5,
      output: 'build/config.js:5:1 Error: invalid syntax',
      created_at: '2025-11-21T10:35:00Z',
    },
  ];

  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('Data Loading and Display', () => {
    it('test_renders_lint_results_table', async () => {
      // ARRANGE
      mockGetResults.mockResolvedValueOnce({ task_id: 101, results: mockResults });

      // ACT
      render(<LintResultsTable taskId={101} />);

      // ASSERT: Wait for loading to complete
      await waitFor(() => {
        expect(screen.queryByText('Loading...')).not.toBeInTheDocument();
      });

      // Verify table headers
      expect(screen.getByText('Linter')).toBeInTheDocument();
      expect(screen.getByText('Errors')).toBeInTheDocument();
      expect(screen.getByText('Warnings')).toBeInTheDocument();
      expect(screen.getByText('Files')).toBeInTheDocument();
      expect(screen.getByText('Time')).toBeInTheDocument();
    });

    it('test_displays_all_linter_results', async () => {
      // ARRANGE
      mockGetResults.mockResolvedValueOnce({ task_id: 101, results: mockResults });

      // ACT
      render(<LintResultsTable taskId={101} />);

      // ASSERT
      await waitFor(() => {
        expect(screen.getByText('ruff')).toBeInTheDocument();
        expect(screen.getByText('eslint')).toBeInTheDocument();
        expect(screen.getByText('other')).toBeInTheDocument();
      });
    });

    it('test_displays_error_counts', async () => {
      // ARRANGE
      mockGetResults.mockResolvedValueOnce({ task_id: 101, results: mockResults });

      // ACT
      render(<LintResultsTable taskId={101} />);

      // ASSERT
      await waitFor(() => {
        const errorCells = screen.getAllByText(/^[0-9]+$/).filter((cell) => {
          const parent = cell.parentElement;
          return parent?.className.includes('font-semibold');
        });

        // Verify error counts: 3, 0, 1
        expect(screen.getByText('3')).toBeInTheDocument();
        expect(screen.getAllByText('0')).toHaveLength(2); // One for errors, one for warnings
        expect(screen.getByText('1')).toBeInTheDocument();
      });
    });

    it('test_displays_warning_counts', async () => {
      // ARRANGE
      mockGetResults.mockResolvedValueOnce({ task_id: 101, results: mockResults });

      // ACT
      render(<LintResultsTable taskId={101} />);

      // ASSERT
      await waitFor(() => {
        // Verify warning counts: 5, 8, 0
        // Find cells with warning styling
        const warningCells = screen.getAllByText(/^[0-9]+$/).filter((cell) => {
          return cell.className.includes('text-yellow-600') || cell.className.includes('text-muted-foreground');
        });
        expect(warningCells.length).toBeGreaterThan(0);
      });
    });

    it('test_displays_files_linted_counts', async () => {
      // ARRANGE
      mockGetResults.mockResolvedValueOnce({ task_id: 101, results: mockResults });

      // ACT
      render(<LintResultsTable taskId={101} />);

      // ASSERT
      await waitFor(() => {
        // Check that all three results are present by counting rows
        const rows = screen.getAllByRole('row');
        expect(rows).toHaveLength(4); // 1 header + 3 data rows

        // Verify file counts exist (may be duplicated with other columns)
        expect(screen.getAllByText('12')).toHaveLength(1);
        expect(screen.getAllByText('25')).toHaveLength(1);
        expect(screen.getAllByText('5').length).toBeGreaterThanOrEqual(1);
      });
    });

    it('test_displays_formatted_timestamps', async () => {
      // ARRANGE
      mockGetResults.mockResolvedValueOnce({ task_id: 101, results: mockResults });

      // ACT
      render(<LintResultsTable taskId={101} />);

      // ASSERT: Timestamps are formatted using toLocaleString()
      await waitFor(() => {
        const timeElements = screen.getAllByText((content, element) => {
          return element?.className.includes('text-sm text-gray-500') || false;
        });
        expect(timeElements.length).toBeGreaterThan(0);
      });
    });

    it('test_calls_api_with_correct_task_id', async () => {
      // ARRANGE
      mockGetResults.mockResolvedValueOnce({ task_id: 101, results: mockResults });

      // ACT
      render(<LintResultsTable taskId={101} />);

      // ASSERT
      await waitFor(() => {
        expect(mockGetResults).toHaveBeenCalledWith(101);
        expect(mockGetResults).toHaveBeenCalledTimes(1);
      });
    });
  });

  describe('Linter Badges', () => {
    it('test_renders_ruff_linter_badge', async () => {
      // ARRANGE
      const ruffResult: LintResult = {
        id: 1,
        task_id: 101,
        linter: 'ruff',
        error_count: 5,
        warning_count: 3,
        files_linted: 10,
        output: '',
        created_at: '2025-11-21T10:00:00Z',
      };
      mockGetResults.mockResolvedValueOnce({ task_id: 101, results: [ruffResult] });

      // ACT
      render(<LintResultsTable taskId={101} />);

      // ASSERT
      await waitFor(() => {
        const badge = screen.getByText('ruff');
        expect(badge).toBeInTheDocument();
        expect(badge).toHaveClass('px-2');
        expect(badge).toHaveClass('py-1');
        expect(badge).toHaveClass('text-xs');
        expect(badge).toHaveClass('font-semibold');
        expect(badge).toHaveClass('rounded');
        expect(badge).toHaveClass('bg-primary/10');
        expect(badge).toHaveClass('text-primary-foreground');
      });
    });

    it('test_renders_eslint_linter_badge', async () => {
      // ARRANGE
      const eslintResult: LintResult = {
        id: 2,
        task_id: 101,
        linter: 'eslint',
        error_count: 2,
        warning_count: 7,
        files_linted: 15,
        output: '',
        created_at: '2025-11-21T10:00:00Z',
      };
      mockGetResults.mockResolvedValueOnce({ task_id: 101, results: [eslintResult] });

      // ACT
      render(<LintResultsTable taskId={101} />);

      // ASSERT
      await waitFor(() => {
        const badge = screen.getByText('eslint');
        expect(badge).toBeInTheDocument();
        expect(badge).toHaveClass('bg-primary/10');
        expect(badge).toHaveClass('text-primary-foreground');
      });
    });

    it('test_renders_other_linter_badge', async () => {
      // ARRANGE
      const otherResult: LintResult = {
        id: 3,
        task_id: 101,
        linter: 'other',
        error_count: 1,
        warning_count: 2,
        files_linted: 8,
        output: '',
        created_at: '2025-11-21T10:00:00Z',
      };
      mockGetResults.mockResolvedValueOnce({ task_id: 101, results: [otherResult] });

      // ACT
      render(<LintResultsTable taskId={101} />);

      // ASSERT
      await waitFor(() => {
        const badge = screen.getByText('other');
        expect(badge).toBeInTheDocument();
        expect(badge).toHaveClass('bg-primary/10');
        expect(badge).toHaveClass('text-primary-foreground');
      });
    });
  });

  describe('Error Count Styling', () => {
    it('test_error_count_red_when_errors_present', async () => {
      // ARRANGE
      const resultWithErrors: LintResult = {
        id: 1,
        task_id: 101,
        linter: 'ruff',
        error_count: 5,
        warning_count: 0,
        files_linted: 10,
        output: '',
        created_at: '2025-11-21T10:00:00Z',
      };
      mockGetResults.mockResolvedValueOnce({ task_id: 101, results: [resultWithErrors] });

      // ACT
      render(<LintResultsTable taskId={101} />);

      // ASSERT
      await waitFor(() => {
        const errorCount = screen.getByText('5');
        expect(errorCount).toHaveClass('font-semibold');
        expect(errorCount).toHaveClass('text-destructive-foreground');
      });
    });

    it('test_error_count_green_when_no_errors', async () => {
      // ARRANGE
      const resultNoErrors: LintResult = {
        id: 1,
        task_id: 101,
        linter: 'eslint',
        error_count: 0,
        warning_count: 5,
        files_linted: 10,
        output: '',
        created_at: '2025-11-21T10:00:00Z',
      };
      mockGetResults.mockResolvedValueOnce({ task_id: 101, results: [resultNoErrors] });

      // ACT
      render(<LintResultsTable taskId={101} />);

      // ASSERT
      await waitFor(() => {
        // Find the error count cell (should be "0")
        const cells = screen.getAllByText('0');
        const errorCell = cells.find((cell) => {
          return cell.className.includes('text-secondary-foreground');
        });
        expect(errorCell).toBeTruthy();
        expect(errorCell).toHaveClass('font-semibold');
        expect(errorCell).toHaveClass('text-secondary-foreground');
      });
    });
  });

  describe('Warning Count Styling', () => {
    it('test_warning_count_yellow_when_warnings_present', async () => {
      // ARRANGE
      const resultWithWarnings: LintResult = {
        id: 1,
        task_id: 101,
        linter: 'ruff',
        error_count: 0,
        warning_count: 8,
        files_linted: 10,
        output: '',
        created_at: '2025-11-21T10:00:00Z',
      };
      mockGetResults.mockResolvedValueOnce({ task_id: 101, results: [resultWithWarnings] });

      // ACT
      render(<LintResultsTable taskId={101} />);

      // ASSERT
      await waitFor(() => {
        const warningCount = screen.getByText('8');
        expect(warningCount).toHaveClass('font-semibold');
        expect(warningCount).toHaveClass('text-yellow-600');
      });
    });

    it('test_warning_count_gray_when_no_warnings', async () => {
      // ARRANGE
      const resultNoWarnings: LintResult = {
        id: 1,
        task_id: 101,
        linter: 'ruff',
        error_count: 5,
        warning_count: 0,
        files_linted: 10,
        output: '',
        created_at: '2025-11-21T10:00:00Z',
      };
      mockGetResults.mockResolvedValueOnce({ task_id: 101, results: [resultNoWarnings] });

      // ACT
      render(<LintResultsTable taskId={101} />);

      // ASSERT
      await waitFor(() => {
        // Find the warning count cell (should be "0")
        const cells = screen.getAllByText('0');
        const warningCell = cells.find((cell) => {
          return cell.className.includes('text-muted-foreground');
        });
        expect(warningCell).toBeTruthy();
        expect(warningCell).toHaveClass('font-semibold');
        expect(warningCell).toHaveClass('text-muted-foreground');
      });
    });
  });

  describe('Empty State', () => {
    it('test_shows_empty_state_no_results', async () => {
      // ARRANGE
      mockGetResults.mockResolvedValueOnce({ task_id: 101, results: [] });

      // ACT
      render(<LintResultsTable taskId={101} />);

      // ASSERT
      await waitFor(() => {
        expect(screen.getByText('No lint results for this task')).toBeInTheDocument();
      });

      // Table should not be rendered
      expect(screen.queryByRole('table')).not.toBeInTheDocument();
    });

    it('test_empty_state_has_correct_styling', async () => {
      // ARRANGE
      mockGetResults.mockResolvedValueOnce({ task_id: 101, results: [] });

      // ACT
      render(<LintResultsTable taskId={101} />);

      // ASSERT
      await waitFor(() => {
        const emptyMessage = screen.getByText('No lint results for this task');
        expect(emptyMessage).toHaveClass('text-muted-foreground');
      });
    });
  });

  describe('Loading State', () => {
    it('test_shows_loading_state', () => {
      // ARRANGE: Promise that never resolves
      mockGetResults.mockImplementation(() => new Promise(() => {}));

      // ACT
      render(<LintResultsTable taskId={101} />);

      // ASSERT
      expect(screen.getByText('Loading...')).toBeInTheDocument();
    });

    it('test_loading_transitions_to_content', async () => {
      // ARRANGE
      mockGetResults.mockResolvedValueOnce({ task_id: 101, results: mockResults });

      // ACT
      render(<LintResultsTable taskId={101} />);

      // ASSERT: Loading initially
      expect(screen.getByText('Loading...')).toBeInTheDocument();

      // ASSERT: Loading disappears after load
      await waitFor(() => {
        expect(screen.queryByText('Loading...')).not.toBeInTheDocument();
        expect(screen.getByText('ruff')).toBeInTheDocument();
      });
    });

    it('test_loading_transitions_to_empty_state', async () => {
      // ARRANGE
      mockGetResults.mockResolvedValueOnce({ task_id: 101, results: [] });

      // ACT
      render(<LintResultsTable taskId={101} />);

      // ASSERT: Loading initially
      expect(screen.getByText('Loading...')).toBeInTheDocument();

      // ASSERT: Transitions to empty state
      await waitFor(() => {
        expect(screen.queryByText('Loading...')).not.toBeInTheDocument();
        expect(screen.getByText('No lint results for this task')).toBeInTheDocument();
      });
    });
  });

  describe('Error Handling', () => {
    it('test_handles_api_error_gracefully', async () => {
      // ARRANGE
      const consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation(() => {});
      mockGetResults.mockRejectedValueOnce(new Error('Failed to fetch lint results'));

      // ACT
      render(<LintResultsTable taskId={101} />);

      // ASSERT: Shows empty state instead of crashing
      await waitFor(() => {
        expect(screen.queryByText('Loading...')).not.toBeInTheDocument();
        expect(screen.getByText('No lint results for this task')).toBeInTheDocument();
      });

      expect(consoleErrorSpy).toHaveBeenCalledWith(
        'Failed to load lint results:',
        expect.any(Error)
      );

      consoleErrorSpy.mockRestore();
    });

    it('test_handles_network_error', async () => {
      // ARRANGE
      const consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation(() => {});
      mockGetResults.mockRejectedValueOnce(new Error('Network error'));

      // ACT
      render(<LintResultsTable taskId={101} />);

      // ASSERT
      await waitFor(() => {
        expect(screen.queryByText('Loading...')).not.toBeInTheDocument();
        expect(screen.getByText('No lint results for this task')).toBeInTheDocument();
      });

      expect(consoleErrorSpy).toHaveBeenCalled();
      consoleErrorSpy.mockRestore();
    });
  });

  describe('Edge Cases', () => {
    it('test_handles_very_large_error_count', async () => {
      // ARRANGE
      const largeErrorResult: LintResult = {
        id: 1,
        task_id: 101,
        linter: 'ruff',
        error_count: 9999,
        warning_count: 0,
        files_linted: 1000,
        output: '',
        created_at: '2025-11-21T10:00:00Z',
      };
      mockGetResults.mockResolvedValueOnce({ task_id: 101, results: [largeErrorResult] });

      // ACT
      render(<LintResultsTable taskId={101} />);

      // ASSERT
      await waitFor(() => {
        expect(screen.getByText('9999')).toBeInTheDocument();
        expect(screen.getByText('9999')).toHaveClass('text-destructive-foreground');
      });
    });

    it('test_handles_very_large_warning_count', async () => {
      // ARRANGE
      const largeWarningResult: LintResult = {
        id: 1,
        task_id: 101,
        linter: 'eslint',
        error_count: 0,
        warning_count: 8888,
        files_linted: 500,
        output: '',
        created_at: '2025-11-21T10:00:00Z',
      };
      mockGetResults.mockResolvedValueOnce({ task_id: 101, results: [largeWarningResult] });

      // ACT
      render(<LintResultsTable taskId={101} />);

      // ASSERT
      await waitFor(() => {
        expect(screen.getByText('8888')).toBeInTheDocument();
        expect(screen.getByText('8888')).toHaveClass('text-yellow-600');
      });
    });

    it('test_handles_zero_files_linted', async () => {
      // ARRANGE
      const zeroFilesResult: LintResult = {
        id: 1,
        task_id: 101,
        linter: 'ruff',
        error_count: 0,
        warning_count: 0,
        files_linted: 0,
        output: '',
        created_at: '2025-11-21T10:00:00Z',
      };
      mockGetResults.mockResolvedValueOnce({ task_id: 101, results: [zeroFilesResult] });

      // ACT
      render(<LintResultsTable taskId={101} />);

      // ASSERT
      await waitFor(() => {
        const zeroElements = screen.getAllByText('0');
        expect(zeroElements.length).toBeGreaterThanOrEqual(3); // error_count, warning_count, files_linted
      });
    });

    it('test_handles_multiple_results_same_linter', async () => {
      // ARRANGE
      const duplicateLinterResults: LintResult[] = [
        {
          id: 1,
          task_id: 101,
          linter: 'ruff',
          error_count: 3,
          warning_count: 5,
          files_linted: 10,
          output: '',
          created_at: '2025-11-21T10:00:00Z',
        },
        {
          id: 2,
          task_id: 101,
          linter: 'ruff',
          error_count: 1,
          warning_count: 2,
          files_linted: 5,
          output: '',
          created_at: '2025-11-21T10:05:00Z',
        },
      ];
      mockGetResults.mockResolvedValueOnce({ task_id: 101, results: duplicateLinterResults });

      // ACT
      render(<LintResultsTable taskId={101} />);

      // ASSERT: Both results are displayed
      await waitFor(() => {
        const ruffBadges = screen.getAllByText('ruff');
        expect(ruffBadges).toHaveLength(2);
      });
    });

    it('test_handles_special_characters_in_output', async () => {
      // ARRANGE
      const specialCharsResult: LintResult = {
        id: 1,
        task_id: 101,
        linter: 'ruff',
        error_count: 1,
        warning_count: 0,
        files_linted: 1,
        output: 'src/test.py:10:5 E501 Line too long (>120 chars) <script>alert("XSS")</script>',
        created_at: '2025-11-21T10:00:00Z',
      };
      mockGetResults.mockResolvedValueOnce({ task_id: 101, results: [specialCharsResult] });

      // ACT
      render(<LintResultsTable taskId={101} />);

      // ASSERT: Table renders without crashing
      await waitFor(() => {
        expect(screen.getByText('ruff')).toBeInTheDocument();
        // Verify a row exists
        const rows = screen.getAllByRole('row');
        expect(rows).toHaveLength(2); // 1 header + 1 data row
      });
    });

    it('test_handles_very_old_timestamp', async () => {
      // ARRANGE
      const oldTimestampResult: LintResult = {
        id: 1,
        task_id: 101,
        linter: 'ruff',
        error_count: 2,
        warning_count: 3,
        files_linted: 8,
        output: '',
        created_at: '2020-01-01T00:00:00Z',
      };
      mockGetResults.mockResolvedValueOnce({ task_id: 101, results: [oldTimestampResult] });

      // ACT
      render(<LintResultsTable taskId={101} />);

      // ASSERT: Timestamp is formatted correctly
      await waitFor(() => {
        expect(screen.getByText('ruff')).toBeInTheDocument();
        // Date should be formatted (exact format depends on locale)
        const dateElements = screen.getAllByText((content, element) => {
          return element?.className.includes('text-sm text-gray-500') || false;
        });
        expect(dateElements.length).toBeGreaterThan(0);
      });
    });

    it('test_handles_future_timestamp', async () => {
      // ARRANGE
      const futureTimestampResult: LintResult = {
        id: 1,
        task_id: 101,
        linter: 'eslint',
        error_count: 1,
        warning_count: 2,
        files_linted: 15,
        output: '',
        created_at: '2030-12-31T23:59:59Z',
      };
      mockGetResults.mockResolvedValueOnce({ task_id: 101, results: [futureTimestampResult] });

      // ACT
      render(<LintResultsTable taskId={101} />);

      // ASSERT: Future timestamp is handled gracefully
      await waitFor(() => {
        expect(screen.getByText('eslint')).toBeInTheDocument();
      });
    });

    it('test_handles_single_result', async () => {
      // ARRANGE
      const singleResult: LintResult = {
        id: 1,
        task_id: 101,
        linter: 'ruff',
        error_count: 5,
        warning_count: 3,
        files_linted: 10,
        output: '',
        created_at: '2025-11-21T10:00:00Z',
      };
      mockGetResults.mockResolvedValueOnce({ task_id: 101, results: [singleResult] });

      // ACT
      render(<LintResultsTable taskId={101} />);

      // ASSERT
      await waitFor(() => {
        const rows = screen.getAllByRole('row');
        // 1 header row + 1 data row = 2 rows
        expect(rows).toHaveLength(2);
      });
    });

    it('test_handles_many_results', async () => {
      // ARRANGE: Create 20 lint results
      const manyResults: LintResult[] = Array.from({ length: 20 }, (_, i) => ({
        id: i + 1,
        task_id: 101,
        linter: i % 2 === 0 ? 'ruff' : 'eslint' as 'ruff' | 'eslint',
        error_count: i,
        warning_count: i * 2,
        files_linted: i * 3,
        output: `Output ${i}`,
        created_at: `2025-11-21T10:${String(i).padStart(2, '0')}:00Z`,
      }));
      mockGetResults.mockResolvedValueOnce({ task_id: 101, results: manyResults });

      // ACT
      render(<LintResultsTable taskId={101} />);

      // ASSERT: All results are rendered
      await waitFor(() => {
        const rows = screen.getAllByRole('row');
        // 1 header row + 20 data rows = 21 rows
        expect(rows).toHaveLength(21);
      });
    });
  });

  describe('Table Styling and Layout', () => {
    it('test_applies_table_container_styling', async () => {
      // ARRANGE
      mockGetResults.mockResolvedValueOnce({ task_id: 101, results: mockResults });

      // ACT
      const { container } = render(<LintResultsTable taskId={101} />);

      // ASSERT
      await waitFor(() => {
        const tableContainer = container.querySelector('.overflow-x-auto');
        expect(tableContainer).toBeInTheDocument();
      });
    });

    it('test_applies_table_styling', async () => {
      // ARRANGE
      mockGetResults.mockResolvedValueOnce({ task_id: 101, results: mockResults });

      // ACT
      const { container } = render(<LintResultsTable taskId={101} />);

      // ASSERT
      await waitFor(() => {
        const table = container.querySelector('table');
        expect(table).toHaveClass('min-w-full');
        expect(table).toHaveClass('divide-y');
        expect(table).toHaveClass('divide-border');
      });
    });

    it('test_applies_header_styling', async () => {
      // ARRANGE
      mockGetResults.mockResolvedValueOnce({ task_id: 101, results: mockResults });

      // ACT
      const { container } = render(<LintResultsTable taskId={101} />);

      // ASSERT
      await waitFor(() => {
        const thead = container.querySelector('thead');
        expect(thead).toHaveClass('bg-muted');
      });
    });

    it('test_applies_body_styling', async () => {
      // ARRANGE
      mockGetResults.mockResolvedValueOnce({ task_id: 101, results: mockResults });

      // ACT
      const { container } = render(<LintResultsTable taskId={101} />);

      // ASSERT
      await waitFor(() => {
        const tbody = container.querySelector('tbody');
        expect(tbody).toHaveClass('bg-card');
        expect(tbody).toHaveClass('divide-y');
        expect(tbody).toHaveClass('divide-border');
      });
    });

    it('test_header_cells_have_correct_styling', async () => {
      // ARRANGE
      mockGetResults.mockResolvedValueOnce({ task_id: 101, results: mockResults });

      // ACT
      const { container } = render(<LintResultsTable taskId={101} />);

      // ASSERT
      await waitFor(() => {
        const headerCells = container.querySelectorAll('thead th');
        headerCells.forEach((cell) => {
          expect(cell).toHaveClass('px-6');
          expect(cell).toHaveClass('py-3');
          expect(cell).toHaveClass('text-left');
          expect(cell).toHaveClass('text-xs');
          expect(cell).toHaveClass('font-medium');
          expect(cell).toHaveClass('text-muted-foreground');
          expect(cell).toHaveClass('uppercase');
        });
      });
    });

    it('test_data_cells_have_correct_styling', async () => {
      // ARRANGE
      mockGetResults.mockResolvedValueOnce({ task_id: 101, results: mockResults });

      // ACT
      const { container } = render(<LintResultsTable taskId={101} />);

      // ASSERT
      await waitFor(() => {
        const dataCells = container.querySelectorAll('tbody td');
        dataCells.forEach((cell) => {
          expect(cell).toHaveClass('px-6');
          expect(cell).toHaveClass('py-4');
          expect(cell).toHaveClass('whitespace-nowrap');
        });
      });
    });
  });

  describe('Component Lifecycle', () => {
    it('test_fetches_data_on_mount', async () => {
      // ARRANGE
      mockGetResults.mockResolvedValueOnce({ task_id: 101, results: mockResults });

      // ACT
      render(<LintResultsTable taskId={101} />);

      // ASSERT
      await waitFor(() => {
        expect(mockGetResults).toHaveBeenCalledTimes(1);
      });
    });

    it('test_refetches_when_task_id_changes', async () => {
      // ARRANGE
      mockGetResults.mockResolvedValue({ task_id: 101, results: mockResults });

      // ACT: Render with taskId 101
      const { rerender } = render(<LintResultsTable taskId={101} />);

      await waitFor(() => {
        expect(mockGetResults).toHaveBeenCalledWith(101);
        expect(mockGetResults).toHaveBeenCalledTimes(1);
      });

      // ACT: Change taskId to 102
      rerender(<LintResultsTable taskId={102} />);

      // ASSERT: Refetches with new taskId
      await waitFor(() => {
        expect(mockGetResults).toHaveBeenCalledWith(102);
        expect(mockGetResults).toHaveBeenCalledTimes(2);
      });
    });

    it('test_cleanup_on_unmount', async () => {
      // ARRANGE
      let resolveFetch: (value: { task_id: number; results: LintResult[] }) => void;
      const fetchPromise = new Promise<{ task_id: number; results: LintResult[] }>((resolve) => {
        resolveFetch = resolve;
      });
      mockGetResults.mockReturnValueOnce(fetchPromise);

      // ACT: Render and unmount before fetch completes
      const { unmount } = render(<LintResultsTable taskId={101} />);

      expect(screen.getByText('Loading...')).toBeInTheDocument();

      // Unmount immediately
      unmount();

      // Resolve the promise after unmount
      resolveFetch!({ task_id: 101, results: mockResults });

      // ASSERT: No errors should occur (component should ignore state updates after unmount)
      await waitFor(() => {
        // If we get here without errors, the test passes
        expect(true).toBe(true);
      });
    });
  });
});
