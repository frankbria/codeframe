/**
 * BlockerBadge Component Tests
 * Tests for blocker type badge display (049-human-in-loop, T016)
 */

import { render, screen } from '@testing-library/react';
import { BlockerBadge } from '@/components/BlockerBadge';

describe('BlockerBadge', () => {
  describe('SYNC blocker badge', () => {
    it('renders with correct label', () => {
      render(<BlockerBadge type="SYNC" />);
      expect(screen.getByText('CRITICAL')).toBeInTheDocument();
    });

    it('displays alert icon', () => {
      render(<BlockerBadge type="SYNC" />);
      expect(screen.getByText('🚨')).toBeInTheDocument();
    });

    it('has red background and text colors', () => {
      const { container } = render(<BlockerBadge type="SYNC" />);
      const badge = container.querySelector('span');
      expect(badge).toHaveClass('bg-red-100');
      expect(badge).toHaveClass('text-red-800');
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

    it('displays lightbulb icon', () => {
      render(<BlockerBadge type="ASYNC" />);
      expect(screen.getByText('💡')).toBeInTheDocument();
    });

    it('has yellow background and text colors', () => {
      const { container } = render(<BlockerBadge type="ASYNC" />);
      const badge = container.querySelector('span');
      expect(badge).toHaveClass('bg-yellow-100');
      expect(badge).toHaveClass('text-yellow-800');
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
      expect(badge).toHaveClass('bg-red-100');
    });

    it('works without custom className', () => {
      const { container } = render(<BlockerBadge type="ASYNC" />);
      const badge = container.querySelector('span');
      expect(badge).toHaveClass('inline-flex');
      expect(badge).toHaveClass('bg-yellow-100');
    });
  });

  describe('icon rendering', () => {
    it('renders icon with correct size class', () => {
      const { container } = render(<BlockerBadge type="SYNC" />);
      const icon = screen.getByText('🚨');
      expect(icon).toHaveClass('text-sm');
    });

    it('renders ASYNC icon with correct size class', () => {
      const { container } = render(<BlockerBadge type="ASYNC" />);
      const icon = screen.getByText('💡');
      expect(icon).toHaveClass('text-sm');
    });
  });
});
