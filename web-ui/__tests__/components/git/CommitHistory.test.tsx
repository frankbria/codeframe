/**
 * CommitHistory Component Tests
 *
 * Tests for the commit history list component that displays
 * recent git commits with expandable details.
 */

import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import CommitHistory from '@/components/git/CommitHistory';
import type { GitCommit } from '@/types/git';

const mockCommits: GitCommit[] = [
  {
    hash: 'abc123def456789',
    short_hash: 'abc123d',
    message: 'feat: Add user authentication',
    author: 'Agent <agent@codeframe.io>',
    timestamp: '2025-01-01T12:00:00Z',
    files_changed: 5,
  },
  {
    hash: 'def456abc789123',
    short_hash: 'def456a',
    message: 'fix: Resolve login bug',
    author: 'Agent <agent@codeframe.io>',
    timestamp: '2025-01-01T11:00:00Z',
    files_changed: 2,
  },
];

describe('CommitHistory', () => {
  describe('rendering', () => {
    it('should render empty state when no commits', () => {
      render(<CommitHistory commits={[]} />);

      expect(screen.getByText(/no commits/i)).toBeInTheDocument();
    });

    it('should render list of commits', () => {
      render(<CommitHistory commits={mockCommits} />);

      expect(screen.getByText('abc123d')).toBeInTheDocument();
      expect(screen.getByText('def456a')).toBeInTheDocument();
    });

    it('should display commit messages', () => {
      render(<CommitHistory commits={mockCommits} />);

      expect(screen.getByText('feat: Add user authentication')).toBeInTheDocument();
      expect(screen.getByText('fix: Resolve login bug')).toBeInTheDocument();
    });

    it('should display file count when available', () => {
      render(<CommitHistory commits={mockCommits} />);

      expect(screen.getByText(/5 files/i)).toBeInTheDocument();
      expect(screen.getByText(/2 files/i)).toBeInTheDocument();
    });

    it('should display relative timestamps', () => {
      render(<CommitHistory commits={mockCommits} />);

      // Since dates are in the past, they should show relative time
      const timeElements = screen.getAllByRole('time');
      expect(timeElements.length).toBe(2);
    });
  });

  describe('loading state', () => {
    it('should show loading state', () => {
      render(<CommitHistory commits={[]} isLoading={true} />);

      expect(screen.getByTestId('commits-loading')).toBeInTheDocument();
    });
  });

  describe('error state', () => {
    it('should show error message', () => {
      render(<CommitHistory commits={[]} error="Failed to load commits" />);

      expect(screen.getByText(/failed to load commits/i)).toBeInTheDocument();
    });
  });

  describe('commit hash link', () => {
    it('should show short hash as monospace text', () => {
      render(<CommitHistory commits={mockCommits} />);

      const hash = screen.getByText('abc123d');
      expect(hash).toHaveClass('font-mono');
    });
  });

  describe('commit limit', () => {
    it('should respect max items limit', () => {
      const manyCommits = Array.from({ length: 20 }, (_, i) => ({
        hash: `hash${i}`,
        short_hash: `hash${i}`.slice(0, 7),
        message: `Commit ${i}`,
        author: 'Agent',
        timestamp: '2025-01-01T00:00:00Z',
      }));

      render(<CommitHistory commits={manyCommits} maxItems={5} />);

      const commitItems = screen.getAllByTestId('commit-item');
      expect(commitItems.length).toBe(5);
    });
  });

  describe('header', () => {
    it('should display title', () => {
      render(<CommitHistory commits={mockCommits} />);

      expect(screen.getByRole('heading')).toHaveTextContent(/commits/i);
    });

    it('should display commit count in header', () => {
      render(<CommitHistory commits={mockCommits} />);

      // Look for the count in parentheses format "(2)"
      expect(screen.getByText(/\(2\)/)).toBeInTheDocument();
    });
  });
});
