/**
 * ReviewScoreChart Component Tests (T063)
 * Tests for visual breakdown of review scores
 * Part of Sprint 9 Phase 3 (Review Agent API/UI Integration)
 */

import { render, screen } from '@testing-library/react';
import ReviewScoreChart from '@/components/review/ReviewScoreChart';
import type { ReviewReport } from '@/types/review';

describe('ReviewScoreChart', () => {
  const createMockReport = (overrides?: Partial<ReviewReport>): ReviewReport => ({
    task_id: 1,
    reviewer_agent_id: 'review-001',
    overall_score: 85,
    complexity_score: 80,
    security_score: 90,
    style_score: 85,
    status: 'approved',
    findings: [],
    summary: 'Code quality is good with minor improvements needed.',
    created_at: '2025-11-21T10:00:00Z',
    ...overrides,
  });

  describe('Overall score display', () => {
    it('renders overall score value', () => {
      const report = createMockReport({ overall_score: 85 });
      const { container } = render(<ReviewScoreChart report={report} />);

      // Use getAllByText since score appears multiple times (overall + breakdown)
      const scores = screen.getAllByText('85.0');
      expect(scores.length).toBeGreaterThan(0);
      expect(scores[0]).toBeInTheDocument();
    });

    it('renders score denominator', () => {
      const report = createMockReport();
      render(<ReviewScoreChart report={report} />);

      expect(screen.getByText('/100')).toBeInTheDocument();
    });

    it('displays "Overall Code Quality" label', () => {
      const report = createMockReport();
      render(<ReviewScoreChart report={report} />);

      expect(screen.getByText('Overall Code Quality')).toBeInTheDocument();
    });

    it('applies secondary color for excellent score (>90)', () => {
      const report = createMockReport({ overall_score: 95 });
      const { container } = render(<ReviewScoreChart report={report} />);
      const scoreElement = screen.getByText('95.0');

      expect(scoreElement).toHaveClass('text-secondary');
    });

    it('applies primary color for good score (70-89)', () => {
      const report = createMockReport({ overall_score: 75 });
      const { container } = render(<ReviewScoreChart report={report} />);
      const scoreElement = screen.getByText('75.0');

      expect(scoreElement).toHaveClass('text-primary/60');
    });

    it('applies destructive color for fair score (50-69)', () => {
      const report = createMockReport({ overall_score: 60 });
      const { container } = render(<ReviewScoreChart report={report} />);
      const scoreElement = screen.getByText('60.0');

      expect(scoreElement).toHaveClass('text-destructive/60');
    });

    it('applies destructive color for poor score (<50)', () => {
      const report = createMockReport({ overall_score: 40 });
      const { container } = render(<ReviewScoreChart report={report} />);
      const scoreElement = screen.getByText('40.0');

      expect(scoreElement).toHaveClass('text-destructive');
    });

    it('handles perfect score (100)', () => {
      const report = createMockReport({ overall_score: 100 });
      render(<ReviewScoreChart report={report} />);

      expect(screen.getByText('100.0')).toBeInTheDocument();
    });

    it('handles minimum score (0)', () => {
      const report = createMockReport({ overall_score: 0 });
      render(<ReviewScoreChart report={report} />);

      expect(screen.getByText('0.0')).toBeInTheDocument();
    });
  });

  describe('Status badge', () => {
    it('renders approved status badge with green styling', () => {
      const report = createMockReport({ status: 'approved' });
      render(<ReviewScoreChart report={report} />);

      const badge = screen.getByText('APPROVED');
      expect(badge).toBeInTheDocument();
      expect(badge).toHaveClass('bg-secondary');
      expect(badge).toHaveClass('text-secondary-foreground');
      expect(badge).toHaveClass('border-border');
    });

    it('renders changes_requested status badge with yellow styling', () => {
      const report = createMockReport({ status: 'changes_requested' });
      render(<ReviewScoreChart report={report} />);

      const badge = screen.getByText('CHANGES REQUESTED');
      expect(badge).toBeInTheDocument();
      expect(badge).toHaveClass('bg-muted');
      expect(badge).toHaveClass('text-foreground');
      expect(badge).toHaveClass('border-border');
    });

    it('renders rejected status badge with red styling', () => {
      const report = createMockReport({ status: 'rejected' });
      render(<ReviewScoreChart report={report} />);

      const badge = screen.getByText('REJECTED');
      expect(badge).toBeInTheDocument();
      expect(badge).toHaveClass('bg-destructive');
      expect(badge).toHaveClass('text-destructive-foreground');
      expect(badge).toHaveClass('border-destructive');
    });

    it('applies base badge classes', () => {
      const report = createMockReport({ status: 'approved' });
      render(<ReviewScoreChart report={report} />);

      const badge = screen.getByText('APPROVED');
      expect(badge).toHaveClass('px-3');
      expect(badge).toHaveClass('py-1');
      expect(badge).toHaveClass('rounded-full');
      expect(badge).toHaveClass('text-sm');
      expect(badge).toHaveClass('font-medium');
      expect(badge).toHaveClass('border');
    });
  });

  describe('Score breakdown', () => {
    it('renders "Score Breakdown" heading', () => {
      const report = createMockReport();
      render(<ReviewScoreChart report={report} />);

      expect(screen.getByText('Score Breakdown')).toBeInTheDocument();
    });

    it('renders security score with correct weight', () => {
      const report = createMockReport({ security_score: 90 });
      render(<ReviewScoreChart report={report} />);

      expect(screen.getByText('Security')).toBeInTheDocument();
      expect(screen.getByText('90.0')).toBeInTheDocument();
      expect(screen.getByText('Weight: 40%')).toBeInTheDocument();
    });

    it('renders complexity score with correct weight', () => {
      const report = createMockReport({ complexity_score: 80, overall_score: 75 });
      render(<ReviewScoreChart report={report} />);

      expect(screen.getByText('Complexity')).toBeInTheDocument();
      expect(screen.getAllByText('80.0').length).toBeGreaterThan(0);
      expect(screen.getByText('Weight: 30%')).toBeInTheDocument();
    });

    it('renders style score with correct weight', () => {
      const report = createMockReport({ style_score: 85, overall_score: 82 });
      render(<ReviewScoreChart report={report} />);

      expect(screen.getByText('Style')).toBeInTheDocument();
      expect(screen.getAllByText('85.0').length).toBeGreaterThan(0);
      expect(screen.getByText('Weight: 20%')).toBeInTheDocument();
    });

    it('renders coverage score with correct weight', () => {
      const report = createMockReport({ overall_score: 75 });
      render(<ReviewScoreChart report={report} />);

      expect(screen.getByText('Coverage')).toBeInTheDocument();
      expect(screen.getAllByText('80.0').length).toBeGreaterThan(0); // Placeholder value
      expect(screen.getByText('Weight: 10%')).toBeInTheDocument();
    });

    it('renders all four score bars', () => {
      const report = createMockReport();
      const { container } = render(<ReviewScoreChart report={report} />);

      const scoreBars = container.querySelectorAll('.h-3.rounded-full');
      expect(scoreBars).toHaveLength(4); // Security, Complexity, Style, Coverage
    });
  });

  describe('Score bar visualization', () => {
    it('renders progress bar with correct width for high score', () => {
      const report = createMockReport({ security_score: 90 });
      const { container } = render(<ReviewScoreChart report={report} />);

      const progressBars = container.querySelectorAll('[style*="width"]');
      const securityBar = progressBars[0]; // First score bar is Security

      expect(securityBar).toHaveStyle({ width: '90%' });
    });

    it('renders progress bar with secondary color for excellent score', () => {
      const report = createMockReport({ security_score: 95 });
      const { container } = render(<ReviewScoreChart report={report} />);

      const progressBars = container.querySelectorAll('.h-full.rounded-full');
      const securityBar = progressBars[0];

      expect(securityBar).toHaveClass('bg-secondary');
    });

    it('renders progress bar with primary color for good score', () => {
      const report = createMockReport({ complexity_score: 75 });
      const { container } = render(<ReviewScoreChart report={report} />);

      const progressBars = container.querySelectorAll('.h-full.rounded-full');
      const complexityBar = progressBars[1];

      expect(complexityBar).toHaveClass('bg-primary/60');
    });

    it('renders progress bar with destructive color for fair score', () => {
      const report = createMockReport({ style_score: 60 });
      const { container } = render(<ReviewScoreChart report={report} />);

      const progressBars = container.querySelectorAll('.h-full.rounded-full');
      const styleBar = progressBars[2];

      expect(styleBar).toHaveClass('bg-destructive/60');
    });

    it('renders progress bar with destructive color for poor score', () => {
      const report = createMockReport({ security_score: 40 });
      const { container } = render(<ReviewScoreChart report={report} />);

      const progressBars = container.querySelectorAll('.h-full.rounded-full');
      const securityBar = progressBars[0];

      expect(securityBar).toHaveClass('bg-destructive');
    });

    it('applies transition animation to progress bars', () => {
      const report = createMockReport();
      const { container } = render(<ReviewScoreChart report={report} />);

      const progressBars = container.querySelectorAll('.h-full.rounded-full');
      progressBars.forEach((bar) => {
        expect(bar).toHaveClass('transition-all');
        expect(bar).toHaveClass('duration-500');
      });
    });
  });

  describe('Summary section', () => {
    it('renders summary text', () => {
      const summary = 'Code quality is excellent with no issues found.';
      const report = createMockReport({ summary });
      render(<ReviewScoreChart report={report} />);

      expect(screen.getByText(summary)).toBeInTheDocument();
    });

    it('handles long summary text', () => {
      const longSummary = 'A'.repeat(500);
      const report = createMockReport({ summary: longSummary });
      render(<ReviewScoreChart report={report} />);

      expect(screen.getByText(longSummary)).toBeInTheDocument();
    });

    it('handles empty summary', () => {
      const report = createMockReport({ summary: '' });
      const { container } = render(<ReviewScoreChart report={report} />);

      // Summary section should still render, just with empty text
      const summarySection = container.querySelector('.pt-4.border-t');
      expect(summarySection).toBeInTheDocument();
    });

    it('applies correct styling to summary', () => {
      const report = createMockReport();
      const { container } = render(<ReviewScoreChart report={report} />);

      const summary = screen.getByText(report.summary);
      expect(summary).toHaveClass('text-sm');
      expect(summary).toHaveClass('text-foreground');
      expect(summary).toHaveClass('leading-relaxed');
    });
  });

  describe('Layout and styling', () => {
    it('applies spacing between sections', () => {
      const report = createMockReport();
      const { container } = render(<ReviewScoreChart report={report} />);

      const mainContainer = container.querySelector('.space-y-6');
      expect(mainContainer).toBeInTheDocument();
    });

    it('applies border to overall score section', () => {
      const report = createMockReport();
      const { container } = render(<ReviewScoreChart report={report} />);

      const scoreSection = container.querySelector('.pb-6.border-b');
      expect(scoreSection).toBeInTheDocument();
    });

    it('applies border to summary section', () => {
      const report = createMockReport();
      const { container } = render(<ReviewScoreChart report={report} />);

      const summarySection = container.querySelector('.pt-4.border-t');
      expect(summarySection).toBeInTheDocument();
    });

    it('centers overall score content', () => {
      const report = createMockReport();
      const { container } = render(<ReviewScoreChart report={report} />);

      const scoreSection = container.querySelector('.text-center.pb-6');
      expect(scoreSection).toBeInTheDocument();
    });

    it('applies uppercase styling to breakdown heading', () => {
      const report = createMockReport();
      render(<ReviewScoreChart report={report} />);

      const heading = screen.getByText('Score Breakdown');
      expect(heading).toHaveClass('uppercase');
      expect(heading).toHaveClass('tracking-wide');
    });
  });

  describe('Score precision', () => {
    it('displays scores with one decimal place', () => {
      const report = createMockReport({
        overall_score: 85.6789,
        security_score: 90.1234,
      });
      render(<ReviewScoreChart report={report} />);

      expect(screen.getByText('85.7')).toBeInTheDocument();
      expect(screen.getByText('90.1')).toBeInTheDocument();
    });

    it('rounds scores correctly', () => {
      const report = createMockReport({
        overall_score: 85.95,
        security_score: 90.94,
      });
      render(<ReviewScoreChart report={report} />);

      expect(screen.getByText('86.0')).toBeInTheDocument();
      expect(screen.getByText('90.9')).toBeInTheDocument();
    });

    it('handles integer scores', () => {
      const report = createMockReport({
        overall_score: 85,
        security_score: 90,
        complexity_score: 78,
        style_score: 88,
      });
      render(<ReviewScoreChart report={report} />);

      expect(screen.getAllByText('85.0').length).toBeGreaterThan(0);
      expect(screen.getAllByText('90.0').length).toBeGreaterThan(0);
    });
  });

  describe('Edge cases', () => {
    it('handles all scores at 100', () => {
      const report = createMockReport({
        overall_score: 100,
        security_score: 100,
        complexity_score: 100,
        style_score: 100,
      });

      const { container } = render(<ReviewScoreChart report={report} />);

      expect(screen.getAllByText('100.0').length).toBeGreaterThan(0);
      const progressBars = container.querySelectorAll('[style*="width: 100%"]');
      expect(progressBars.length).toBeGreaterThan(0);
    });

    it('handles all scores at 0', () => {
      const report = createMockReport({
        overall_score: 0,
        security_score: 0,
        complexity_score: 0,
        style_score: 0,
      });

      const { container } = render(<ReviewScoreChart report={report} />);

      expect(screen.getAllByText('0.0').length).toBeGreaterThan(0);
      const progressBars = container.querySelectorAll('[style*="width: 0%"]');
      expect(progressBars.length).toBeGreaterThan(0);
    });

    it('handles mixed score ranges', () => {
      const report = createMockReport({
        overall_score: 75,
        security_score: 95,
        complexity_score: 60,
        style_score: 45,
      });

      render(<ReviewScoreChart report={report} />);

      expect(screen.getByText('95.0')).toBeInTheDocument();
      expect(screen.getByText('60.0')).toBeInTheDocument();
      expect(screen.getByText('45.0')).toBeInTheDocument();
    });

    it('handles decimal scores near boundaries', () => {
      const report = createMockReport({
        overall_score: 89.9, // Just below 90 threshold
      });

      const { container } = render(<ReviewScoreChart report={report} />);
      const scoreElement = screen.getByText('89.9');

      // Should be primary/60, not secondary (since < 90)
      expect(scoreElement).toHaveClass('text-primary/60');
    });
  });

  describe('Score bar component', () => {
    it('renders score bar label', () => {
      const report = createMockReport();
      render(<ReviewScoreChart report={report} />);

      expect(screen.getByText('Security')).toBeInTheDocument();
      expect(screen.getByText('Complexity')).toBeInTheDocument();
      expect(screen.getByText('Style')).toBeInTheDocument();
      expect(screen.getByText('Coverage')).toBeInTheDocument();
    });

    it('applies correct text styling to labels', () => {
      const report = createMockReport();
      render(<ReviewScoreChart report={report} />);

      const label = screen.getByText('Security');
      expect(label).toHaveClass('font-medium');
      expect(label).toHaveClass('text-foreground');
    });

    it('applies correct text styling to scores', () => {
      const report = createMockReport({ security_score: 90 });
      render(<ReviewScoreChart report={report} />);

      const score = screen.getByText('90.0');
      expect(score).toHaveClass('font-semibold');
      expect(score).toHaveClass('text-foreground');
    });

    it('applies correct weight label styling', () => {
      const report = createMockReport();
      const { container } = render(<ReviewScoreChart report={report} />);

      const weightLabel = screen.getByText('Weight: 40%');
      expect(weightLabel).toHaveClass('text-xs');
      expect(weightLabel).toHaveClass('text-muted-foreground');
    });
  });
});
