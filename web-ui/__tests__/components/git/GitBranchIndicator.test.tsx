/**
 * GitBranchIndicator Component Tests
 *
 * Tests for the Git branch indicator component that displays
 * the current branch name and status in the Dashboard header.
 */

import React from 'react';
import { render, screen } from '@testing-library/react';
import GitBranchIndicator from '@/components/git/GitBranchIndicator';
import type { GitStatus } from '@/types/git';

describe('GitBranchIndicator', () => {
  describe('rendering', () => {
    it('should render nothing when status is null', () => {
      const { container } = render(<GitBranchIndicator status={null} />);
      expect(container.firstChild).toBeNull();
    });

    it('should render branch name', () => {
      const status: GitStatus = {
        current_branch: 'feature/auth',
        is_dirty: false,
        modified_files: [],
        untracked_files: [],
        staged_files: [],
      };

      render(<GitBranchIndicator status={status} />);

      expect(screen.getByText('feature/auth')).toBeInTheDocument();
    });

    it('should show branch icon', () => {
      const status: GitStatus = {
        current_branch: 'main',
        is_dirty: false,
        modified_files: [],
        untracked_files: [],
        staged_files: [],
      };

      render(<GitBranchIndicator status={status} />);

      // The component should have some visual branch indicator
      const indicator = screen.getByTestId('branch-indicator');
      expect(indicator).toBeInTheDocument();
    });
  });

  describe('dirty state indicator', () => {
    it('should show clean state when not dirty', () => {
      const status: GitStatus = {
        current_branch: 'main',
        is_dirty: false,
        modified_files: [],
        untracked_files: [],
        staged_files: [],
      };

      render(<GitBranchIndicator status={status} />);

      // Should not show dirty indicator
      expect(screen.queryByTestId('dirty-indicator')).not.toBeInTheDocument();
    });

    it('should show dirty indicator when dirty', () => {
      const status: GitStatus = {
        current_branch: 'main',
        is_dirty: true,
        modified_files: ['file.ts'],
        untracked_files: [],
        staged_files: [],
      };

      render(<GitBranchIndicator status={status} />);

      expect(screen.getByTestId('dirty-indicator')).toBeInTheDocument();
    });

    it('should show modified file count in tooltip/title', () => {
      const status: GitStatus = {
        current_branch: 'main',
        is_dirty: true,
        modified_files: ['a.ts', 'b.ts'],
        untracked_files: ['c.ts'],
        staged_files: ['d.ts'],
      };

      render(<GitBranchIndicator status={status} />);

      // 4 total changes (2 modified + 1 untracked + 1 staged)
      const indicator = screen.getByTestId('branch-indicator');
      expect(indicator).toHaveAttribute('title', expect.stringContaining('4'));
    });
  });

  describe('loading state', () => {
    it('should show loading state when isLoading is true', () => {
      render(<GitBranchIndicator status={null} isLoading={true} />);

      expect(screen.getByTestId('branch-loading')).toBeInTheDocument();
    });
  });

  describe('error state', () => {
    it('should show error state when error is present', () => {
      render(<GitBranchIndicator status={null} error="Failed to fetch" />);

      expect(screen.getByTestId('branch-error')).toBeInTheDocument();
    });
  });

  describe('styling', () => {
    it('should use muted styling for long branch names', () => {
      const status: GitStatus = {
        current_branch: 'feature/very-long-branch-name-that-needs-truncation',
        is_dirty: false,
        modified_files: [],
        untracked_files: [],
        staged_files: [],
      };

      render(<GitBranchIndicator status={status} />);

      const branchName = screen.getByText(/feature\/very-long/);
      expect(branchName.closest('[data-testid="branch-indicator"]')).toHaveClass('truncate');
    });
  });
});
