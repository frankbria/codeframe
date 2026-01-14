/**
 * ReviewFindingsList Component Tests (T062)
 * Tests for review findings display with severity indicators
 * Part of Sprint 9 Phase 3 (Review Agent API/UI Integration)
 * Updated for emoji-to-Hugeicons migration: icons now use Hugeicons components
 */

import { render, screen } from '@testing-library/react';
import ReviewFindingsList from '@/components/review/ReviewFindingsList';
import type { ReviewFinding, FindingSeverity } from '@/types/review';

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
    CheckmarkCircle01Icon: createMockIcon('CheckmarkCircle01Icon'),
    LockIcon: createMockIcon('LockIcon'),
    RepeatIcon: createMockIcon('RepeatIcon'),
    SparklesIcon: createMockIcon('SparklesIcon'),
    ChartBarLineIcon: createMockIcon('ChartBarLineIcon'),
    KnightShieldIcon: createMockIcon('KnightShieldIcon'),
    FileEditIcon: createMockIcon('FileEditIcon'),
    Idea01Icon: createMockIcon('Idea01Icon'),
  };
});

describe('ReviewFindingsList', () => {
  describe('Empty state', () => {
    it('renders empty state when no findings provided', () => {
      render(<ReviewFindingsList findings={[]} />);

      expect(screen.getByText('No findings - excellent code quality!')).toBeInTheDocument();
      expect(screen.getByTestId('CheckmarkCircle01Icon')).toBeInTheDocument();
    });

    it('applies correct CSS classes to empty state container', () => {
      const { container } = render(<ReviewFindingsList findings={[]} />);
      const emptyState = container.querySelector('div.text-center');

      expect(emptyState).toHaveClass('text-center');
      expect(emptyState).toHaveClass('py-8');
      expect(emptyState).toHaveClass('text-muted-foreground');
    });

    it('displays CheckmarkCircle01Icon in empty state', () => {
      render(<ReviewFindingsList findings={[]} />);
      const icon = screen.getByTestId('CheckmarkCircle01Icon');

      expect(icon).toBeInTheDocument();
    });
  });

  describe('Finding rendering', () => {
    const mockFinding: ReviewFinding = {
      file_path: 'src/components/Button.tsx',
      line_number: 42,
      category: 'security',
      severity: 'high',
      message: 'Potential XSS vulnerability detected',
      suggestion: 'Use proper input sanitization',
    };

    it('renders finding message', () => {
      render(<ReviewFindingsList findings={[mockFinding]} />);

      expect(screen.getByText('Potential XSS vulnerability detected')).toBeInTheDocument();
    });

    it('renders file path', () => {
      render(<ReviewFindingsList findings={[mockFinding]} />);

      expect(screen.getByText('src/components/Button.tsx')).toBeInTheDocument();
    });

    it('renders line number', () => {
      render(<ReviewFindingsList findings={[mockFinding]} />);

      expect(screen.getByText('Line 42')).toBeInTheDocument();
    });

    it('renders category name', () => {
      render(<ReviewFindingsList findings={[mockFinding]} />);

      expect(screen.getByText('security')).toBeInTheDocument();
    });

    it('renders suggestion when provided', () => {
      render(<ReviewFindingsList findings={[mockFinding]} />);

      expect(screen.getByText('Use proper input sanitization')).toBeInTheDocument();
    });

    it('does not render suggestion section when suggestion is not provided', () => {
      const findingWithoutSuggestion = { ...mockFinding, suggestion: undefined };
      const { container } = render(<ReviewFindingsList findings={[findingWithoutSuggestion]} />);

      const suggestionBox = container.querySelector('.bg-blue-50');
      expect(suggestionBox).not.toBeInTheDocument();
    });

    it('applies hover effect to finding container', () => {
      const { container } = render(<ReviewFindingsList findings={[mockFinding]} />);
      const findingCard = container.querySelector('.hover\\:bg-muted');

      expect(findingCard).toBeInTheDocument();
      expect(findingCard).toHaveClass('hover:bg-muted');
      expect(findingCard).toHaveClass('transition-colors');
    });
  });

  describe('Severity badges', () => {
    const createFindingWithSeverity = (severity: FindingSeverity): ReviewFinding => ({
      file_path: 'test.ts',
      line_number: 1,
      category: 'security',
      severity,
      message: 'Test message',
    });

    it('renders critical severity badge with red styling', () => {
      render(<ReviewFindingsList findings={[createFindingWithSeverity('critical')]} />);

      const badge = screen.getByText('CRITICAL');
      expect(badge).toBeInTheDocument();
      expect(badge).toHaveClass('bg-destructive');
      expect(badge).toHaveClass('text-destructive-foreground');
      expect(badge).toHaveClass('border-destructive');
    });

    it('renders high severity badge with orange styling', () => {
      render(<ReviewFindingsList findings={[createFindingWithSeverity('high')]} />);

      const badge = screen.getByText('HIGH');
      expect(badge).toBeInTheDocument();
      expect(badge).toHaveClass('bg-destructive/80');
      expect(badge).toHaveClass('text-destructive-foreground');
      expect(badge).toHaveClass('border-destructive');
    });

    it('renders medium severity badge with yellow styling', () => {
      render(<ReviewFindingsList findings={[createFindingWithSeverity('medium')]} />);

      const badge = screen.getByText('MEDIUM');
      expect(badge).toBeInTheDocument();
      expect(badge).toHaveClass('bg-muted');
      expect(badge).toHaveClass('text-foreground');
      expect(badge).toHaveClass('border-border');
    });

    it('renders low severity badge with blue styling', () => {
      render(<ReviewFindingsList findings={[createFindingWithSeverity('low')]} />);

      const badge = screen.getByText('LOW');
      expect(badge).toBeInTheDocument();
      expect(badge).toHaveClass('bg-secondary');
      expect(badge).toHaveClass('text-secondary-foreground');
      expect(badge).toHaveClass('border-border');
    });

    it('renders info severity badge with gray styling', () => {
      render(<ReviewFindingsList findings={[createFindingWithSeverity('info')]} />);

      const badge = screen.getByText('INFO');
      expect(badge).toBeInTheDocument();
      expect(badge).toHaveClass('bg-muted');
      expect(badge).toHaveClass('text-muted-foreground');
      expect(badge).toHaveClass('border-border');
    });

    it('applies badge base classes', () => {
      render(<ReviewFindingsList findings={[createFindingWithSeverity('high')]} />);

      const badge = screen.getByText('HIGH');
      expect(badge).toHaveClass('px-2');
      expect(badge).toHaveClass('py-1');
      expect(badge).toHaveClass('rounded-full');
      expect(badge).toHaveClass('text-xs');
      expect(badge).toHaveClass('font-medium');
      expect(badge).toHaveClass('border');
    });
  });

  describe('Category icons', () => {
    const createFindingWithCategory = (category: string): ReviewFinding => ({
      file_path: 'test.ts',
      line_number: 1,
      category: category as any,
      severity: 'medium',
      message: 'Test message',
    });

    it('renders security category icon', () => {
      render(<ReviewFindingsList findings={[createFindingWithCategory('security')]} />);
      expect(screen.getByTestId('LockIcon')).toBeInTheDocument();
    });

    it('renders complexity category icon', () => {
      render(<ReviewFindingsList findings={[createFindingWithCategory('complexity')]} />);
      expect(screen.getByTestId('RepeatIcon')).toBeInTheDocument();
    });

    it('renders style category icon', () => {
      render(<ReviewFindingsList findings={[createFindingWithCategory('style')]} />);
      expect(screen.getByTestId('SparklesIcon')).toBeInTheDocument();
    });

    it('renders coverage category icon', () => {
      render(<ReviewFindingsList findings={[createFindingWithCategory('coverage')]} />);
      expect(screen.getByTestId('ChartBarLineIcon')).toBeInTheDocument();
    });

    it('renders owasp category icon', () => {
      render(<ReviewFindingsList findings={[createFindingWithCategory('owasp')]} />);
      expect(screen.getByTestId('KnightShieldIcon')).toBeInTheDocument();
    });

    it('renders default category icon for unknown category', () => {
      render(<ReviewFindingsList findings={[createFindingWithCategory('unknown')]} />);
      expect(screen.getByTestId('FileEditIcon')).toBeInTheDocument();
    });
  });

  describe('Multiple findings', () => {
    const mockFindings: ReviewFinding[] = [
      {
        file_path: 'src/auth.ts',
        line_number: 10,
        category: 'security',
        severity: 'critical',
        message: 'Password stored in plain text',
        suggestion: 'Use bcrypt for password hashing',
      },
      {
        file_path: 'src/utils.ts',
        line_number: 55,
        category: 'complexity',
        severity: 'medium',
        message: 'Function has cyclomatic complexity of 15',
        suggestion: 'Refactor into smaller functions',
      },
      {
        file_path: 'src/styles.css',
        line_number: 120,
        category: 'style',
        severity: 'low',
        message: 'Inconsistent indentation',
      },
    ];

    it('renders all findings', () => {
      render(<ReviewFindingsList findings={mockFindings} />);

      expect(screen.getByText('Password stored in plain text')).toBeInTheDocument();
      expect(screen.getByText('Function has cyclomatic complexity of 15')).toBeInTheDocument();
      expect(screen.getByText('Inconsistent indentation')).toBeInTheDocument();
    });

    it('renders correct number of finding cards', () => {
      const { container } = render(<ReviewFindingsList findings={mockFindings} />);
      const findingCards = container.querySelectorAll('.border.rounded-lg');

      expect(findingCards).toHaveLength(3);
    });

    it('renders findings with correct severity badges', () => {
      render(<ReviewFindingsList findings={mockFindings} />);

      expect(screen.getByText('CRITICAL')).toBeInTheDocument();
      expect(screen.getByText('MEDIUM')).toBeInTheDocument();
      expect(screen.getByText('LOW')).toBeInTheDocument();
    });

    it('renders correct file paths for all findings', () => {
      render(<ReviewFindingsList findings={mockFindings} />);

      expect(screen.getByText('src/auth.ts')).toBeInTheDocument();
      expect(screen.getByText('src/utils.ts')).toBeInTheDocument();
      expect(screen.getByText('src/styles.css')).toBeInTheDocument();
    });

    it('renders suggestions only for findings that have them', () => {
      render(<ReviewFindingsList findings={mockFindings} />);

      expect(screen.getByText('Use bcrypt for password hashing')).toBeInTheDocument();
      expect(screen.getByText('Refactor into smaller functions')).toBeInTheDocument();
      // Third finding has no suggestion, so no extra suggestion should appear
      const suggestions = screen.getAllByText(/Suggestion:/);
      expect(suggestions).toHaveLength(2);
    });
  });

  describe('Styling and layout', () => {
    const mockFinding: ReviewFinding = {
      file_path: 'test.ts',
      line_number: 1,
      category: 'security',
      severity: 'high',
      message: 'Test message',
      suggestion: 'Test suggestion',
    };

    it('applies correct container spacing', () => {
      const { container } = render(<ReviewFindingsList findings={[mockFinding]} />);
      const listContainer = container.querySelector('.space-y-3');

      expect(listContainer).toBeInTheDocument();
      expect(listContainer).toHaveClass('space-y-3');
    });

    it('applies correct padding to finding card', () => {
      const { container } = render(<ReviewFindingsList findings={[mockFinding]} />);
      const card = container.querySelector('.p-4');

      expect(card).toBeInTheDocument();
      expect(card).toHaveClass('p-4');
    });

    it('applies monospace font to file path', () => {
      const { container } = render(<ReviewFindingsList findings={[mockFinding]} />);
      const filePath = screen.getByText('test.ts');

      expect(filePath).toHaveClass('font-mono');
    });

    it('applies suggestion box styling', () => {
      const { container } = render(<ReviewFindingsList findings={[mockFinding]} />);
      const suggestionBox = container.querySelector('.bg-muted');

      expect(suggestionBox).toBeInTheDocument();
      expect(suggestionBox).toHaveClass('bg-muted');
      expect(suggestionBox).toHaveClass('border-border');
      expect(suggestionBox).toHaveClass('rounded');
    });

    it('capitalizes category name', () => {
      const { container } = render(<ReviewFindingsList findings={[mockFinding]} />);
      const category = screen.getByText('security');

      expect(category).toHaveClass('capitalize');
    });
  });

  describe('Edge cases', () => {
    it('handles finding with line number 0', () => {
      const finding: ReviewFinding = {
        file_path: 'test.ts',
        line_number: 0,
        category: 'security',
        severity: 'low',
        message: 'Test',
      };

      render(<ReviewFindingsList findings={[finding]} />);
      expect(screen.getByText('Line 0')).toBeInTheDocument();
    });

    it('handles finding with very long message', () => {
      const longMessage = 'A'.repeat(500);
      const finding: ReviewFinding = {
        file_path: 'test.ts',
        line_number: 1,
        category: 'security',
        severity: 'low',
        message: longMessage,
      };

      render(<ReviewFindingsList findings={[finding]} />);
      expect(screen.getByText(longMessage)).toBeInTheDocument();
    });

    it('handles finding with very long file path', () => {
      const longPath = 'src/' + 'folder/'.repeat(20) + 'file.ts';
      const finding: ReviewFinding = {
        file_path: longPath,
        line_number: 1,
        category: 'security',
        severity: 'low',
        message: 'Test',
      };

      render(<ReviewFindingsList findings={[finding]} />);
      expect(screen.getByText(longPath)).toBeInTheDocument();
    });

    it('handles empty suggestion string', () => {
      const finding: ReviewFinding = {
        file_path: 'test.ts',
        line_number: 1,
        category: 'security',
        severity: 'low',
        message: 'Test',
        suggestion: '',
      };

      const { container } = render(<ReviewFindingsList findings={[finding]} />);
      // Empty string is falsy, so suggestion box should not render
      const suggestionBox = container.querySelector('.bg-blue-50');
      expect(suggestionBox).not.toBeInTheDocument();
    });
  });
});
