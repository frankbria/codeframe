/**
 * BranchList Component Tests
 *
 * Tests for the branch list component that displays
 * all git branches with status indicators.
 */

import React from 'react';
import { render, screen } from '@testing-library/react';
import BranchList from '@/components/git/BranchList';
import type { GitBranch } from '@/types/git';

const mockBranches: GitBranch[] = [
  {
    id: 1,
    branch_name: 'feature/auth',
    issue_id: 10,
    status: 'active',
    created_at: '2025-01-01T00:00:00Z',
  },
  {
    id: 2,
    branch_name: 'feature/dashboard',
    issue_id: 20,
    status: 'merged',
    created_at: '2025-01-01T00:00:00Z',
    merged_at: '2025-01-02T00:00:00Z',
    merge_commit: 'abc123',
  },
  {
    id: 3,
    branch_name: 'feature/abandoned',
    issue_id: 30,
    status: 'abandoned',
    created_at: '2025-01-01T00:00:00Z',
  },
];

describe('BranchList', () => {
  describe('rendering', () => {
    it('should render empty state when no branches', () => {
      render(<BranchList branches={[]} />);

      expect(screen.getByText(/no branches/i)).toBeInTheDocument();
    });

    it('should render list of branches', () => {
      render(<BranchList branches={mockBranches} />);

      expect(screen.getByText('feature/auth')).toBeInTheDocument();
      expect(screen.getByText('feature/dashboard')).toBeInTheDocument();
      expect(screen.getByText('feature/abandoned')).toBeInTheDocument();
    });

    it('should render branch count in header', () => {
      render(<BranchList branches={mockBranches} />);

      expect(screen.getByText(/\(3\)/)).toBeInTheDocument();
    });
  });

  describe('status badges', () => {
    it('should show active status badge', () => {
      render(<BranchList branches={[mockBranches[0]]} />);

      expect(screen.getByText('active')).toBeInTheDocument();
    });

    it('should show merged status badge', () => {
      render(<BranchList branches={[mockBranches[1]]} />);

      expect(screen.getByText('merged')).toBeInTheDocument();
    });

    it('should show abandoned status badge', () => {
      render(<BranchList branches={[mockBranches[2]]} />);

      expect(screen.getByText('abandoned')).toBeInTheDocument();
    });

    it('should use correct styling for active branch', () => {
      render(<BranchList branches={[mockBranches[0]]} />);

      const badge = screen.getByText('active');
      expect(badge).toHaveClass('bg-primary/10');
    });

    it('should use correct styling for merged branch', () => {
      render(<BranchList branches={[mockBranches[1]]} />);

      const badge = screen.getByText('merged');
      expect(badge).toHaveClass('bg-secondary/10');
    });

    it('should use correct styling for abandoned branch', () => {
      render(<BranchList branches={[mockBranches[2]]} />);

      const badge = screen.getByText('abandoned');
      expect(badge).toHaveClass('bg-muted');
    });
  });

  describe('merged branch info', () => {
    it('should show merge commit for merged branches', () => {
      render(<BranchList branches={[mockBranches[1]]} />);

      expect(screen.getByText(/abc123/i)).toBeInTheDocument();
    });
  });

  describe('loading state', () => {
    it('should show loading state', () => {
      render(<BranchList branches={[]} isLoading={true} />);

      expect(screen.getByTestId('branches-loading')).toBeInTheDocument();
    });
  });

  describe('error state', () => {
    it('should show error message', () => {
      render(<BranchList branches={[]} error="Failed to load branches" />);

      expect(screen.getByText(/failed to load branches/i)).toBeInTheDocument();
    });
  });

  describe('filtering', () => {
    it('should filter by status when provided', () => {
      render(<BranchList branches={mockBranches} filterStatus="active" />);

      expect(screen.getByText('feature/auth')).toBeInTheDocument();
      expect(screen.queryByText('feature/dashboard')).not.toBeInTheDocument();
    });
  });
});
