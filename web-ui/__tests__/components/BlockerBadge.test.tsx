/**
 * BlockerBadge Component Tests
 * Tests for blocker type badge display (049-human-in-loop, T016)
 * Updated for emoji-to-Hugeicons migration: icons now use Hugeicons components
 */

import { render, screen } from '@testing-library/react';
import { BlockerBadge } from '@/components/BlockerBadge';

// Mock Hugeicons
jest.mock('@hugeicons/react', () => {
  const React = require('react');
  return {
    Alert02Icon: ({ className }: { className?: string }) => (
      <svg data-testid="Alert02Icon" className={className} aria-hidden="true" />
    ),
    Idea01Icon: ({ className }: { className?: string }) => (
      <svg data-testid="Idea01Icon" className={className} aria-hidden="true" />
    ),
  };
});

describe('BlockerBadge', () => {
  describe('SYNC blocker badge', () => {
    it('renders with correct label', () => {
      render(<BlockerBadge type="SYNC" />);
      expect(screen.getByText('CRITICAL')).toBeInTheDocument();
    });

    it('displays Alert02Icon', () => {
      render(<BlockerBadge type="SYNC" />);
      expect(screen.getByTestId('Alert02Icon')).toBeInTheDocument();
    });

    it('has red background and text colors', () => {
      const { container } = render(<BlockerBadge type="SYNC" />);
      const badge = container.querySelector('span');
      expect(badge).toHaveClass('bg-destructive/10');
      expect(badge).toHaveClass('text-destructive');
    });

    it('has tooltip explaining sync blocker', () => {
      const { container } = render(<BlockerBadge type="SYNC" />);
      const badge = container.querySelector('span[title]');
      expect(badge).toHaveAttribute('title', 'SYNC blocker - Agent paused, immediate action required');
    });

    it('includes base CSS classes', () => {
      const { container } = render(<BlockerBadge type="SYNC" />);
      const badge = container.querySelector('span');
      expect(badge).toHaveClass('inline-flex');
      expect(badge).toHaveClass('items-center');
      expect(badge).toHaveClass('gap-1');
      expect(badge).toHaveClass('px-2');
      expect(badge).toHaveClass('py-1');
      expect(badge).toHaveClass('rounded-full');
      expect(badge).toHaveClass('text-xs');
      expect(badge).toHaveClass('font-medium');
    });
  });

  describe('ASYNC blocker badge', () => {
    it('renders with correct label', () => {
      render(<BlockerBadge type="ASYNC" />);
      expect(screen.getByText('INFO')).toBeInTheDocument();
    });

    it('displays Idea01Icon', () => {
      render(<BlockerBadge type="ASYNC" />);
      expect(screen.getByTestId('Idea01Icon')).toBeInTheDocument();
    });

    it('has yellow background and text colors', () => {
      const { container } = render(<BlockerBadge type="ASYNC" />);
      const badge = container.querySelector('span');
      expect(badge).toHaveClass('bg-accent/10');
      expect(badge).toHaveClass('text-accent-foreground');
    });

    it('has tooltip explaining async blocker', () => {
      const { container } = render(<BlockerBadge type="ASYNC" />);
      const badge = container.querySelector('span[title]');
      expect(badge).toHaveAttribute('title', 'ASYNC blocker - Agent continuing, info only');
    });

    it('includes base CSS classes', () => {
      const { container } = render(<BlockerBadge type="ASYNC" />);
      const badge = container.querySelector('span');
      expect(badge).toHaveClass('inline-flex');
      expect(badge).toHaveClass('items-center');
      expect(badge).toHaveClass('rounded-full');
    });
  });

  describe('custom className', () => {
    it('applies custom className when provided', () => {
      const { container } = render(<BlockerBadge type="SYNC" className="custom-test-class" />);
      const badge = container.querySelector('span');
      expect(badge).toHaveClass('custom-test-class');
    });

    it('preserves base classes when custom className added', () => {
      const { container } = render(<BlockerBadge type="SYNC" className="my-custom-class" />);
      const badge = container.querySelector('span');
      expect(badge).toHaveClass('my-custom-class');
      expect(badge).toHaveClass('inline-flex');
      expect(badge).toHaveClass('bg-destructive/10');
    });

    it('works without custom className', () => {
      const { container } = render(<BlockerBadge type="ASYNC" />);
      const badge = container.querySelector('span');
      expect(badge).toHaveClass('inline-flex');
      expect(badge).toHaveClass('bg-accent/10');
    });
  });

  describe('icon rendering', () => {
    it('renders SYNC icon with correct size class', () => {
      render(<BlockerBadge type="SYNC" />);
      const icon = screen.getByTestId('Alert02Icon');
      expect(icon).toHaveClass('h-3.5', 'w-3.5');
    });

    it('renders ASYNC icon with correct size class', () => {
      render(<BlockerBadge type="ASYNC" />);
      const icon = screen.getByTestId('Idea01Icon');
      expect(icon).toHaveClass('h-3.5', 'w-3.5');
    });
  });
});
