/**
 * GitSection Component Tests
 *
 * Tests for the Git section container component that combines
 * GitBranchIndicator, CommitHistory, and BranchList.
 */

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import GitSection from '@/components/git/GitSection';
import * as gitApi from '@/api/git';
import type { GitStatus, GitCommit, GitBranch } from '@/types/git';

// Mock SWR
jest.mock('swr', () => ({
  __esModule: true,
  default: jest.fn(),
}));

// Mock the Git API
jest.mock('@/api/git');

const mockGitApi = gitApi as jest.Mocked<typeof gitApi>;

const mockStatus: GitStatus = {
  current_branch: 'feature/test',
  is_dirty: false,
  modified_files: [],
  untracked_files: [],
  staged_files: [],
};

const mockCommits: GitCommit[] = [
  {
    hash: 'abc123',
    short_hash: 'abc123',
    message: 'Test commit',
    author: 'Agent',
    timestamp: '2025-01-01T00:00:00Z',
  },
];

const mockBranches: GitBranch[] = [
  {
    id: 1,
    branch_name: 'feature/test',
    issue_id: 10,
    status: 'active',
    created_at: '2025-01-01T00:00:00Z',
  },
];

// Get the mocked SWR
import useSWR from 'swr';
const mockUseSWR = useSWR as jest.Mock;

describe('GitSection', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('loading state', () => {
    it('should show loading state initially', () => {
      mockUseSWR.mockImplementation(() => ({
        data: undefined,
        error: undefined,
        isLoading: true,
      }));

      render(<GitSection projectId={1} />);

      expect(screen.getByTestId('git-section-loading')).toBeInTheDocument();
    });
  });

  describe('error state', () => {
    it('should show error state when API fails', () => {
      mockUseSWR.mockImplementation(() => ({
        data: undefined,
        error: new Error('API Error'),
        isLoading: false,
      }));

      render(<GitSection projectId={1} />);

      expect(screen.getByTestId('git-section-error')).toBeInTheDocument();
    });
  });

  describe('data display', () => {
    it('should render all Git components when data is loaded', () => {
      mockUseSWR.mockImplementation((key: string) => {
        if (key.includes('status')) {
          return { data: mockStatus, error: undefined, isLoading: false };
        }
        if (key.includes('commits')) {
          return { data: mockCommits, error: undefined, isLoading: false };
        }
        if (key.includes('branches')) {
          return { data: mockBranches, error: undefined, isLoading: false };
        }
        return { data: undefined, error: undefined, isLoading: false };
      });

      render(<GitSection projectId={1} />);

      // Should show section header
      expect(screen.getByText(/code & git/i)).toBeInTheDocument();
    });

    it('should pass correct data to child components', () => {
      mockUseSWR.mockImplementation((key: string) => {
        if (key.includes('status')) {
          return { data: mockStatus, error: undefined, isLoading: false };
        }
        if (key.includes('commits')) {
          return { data: mockCommits, error: undefined, isLoading: false };
        }
        if (key.includes('branches')) {
          return { data: mockBranches, error: undefined, isLoading: false };
        }
        return { data: undefined, error: undefined, isLoading: false };
      });

      render(<GitSection projectId={1} />);

      // Check branch name appears (in indicator and/or branch list)
      const branchElements = screen.getAllByText('feature/test');
      expect(branchElements.length).toBeGreaterThan(0);
    });
  });

  describe('collapsible sections', () => {
    it('should render with expandable sections', () => {
      mockUseSWR.mockImplementation((key: string) => {
        if (key.includes('status')) {
          return { data: mockStatus, error: undefined, isLoading: false };
        }
        if (key.includes('commits')) {
          return { data: mockCommits, error: undefined, isLoading: false };
        }
        if (key.includes('branches')) {
          return { data: mockBranches, error: undefined, isLoading: false };
        }
        return { data: undefined, error: undefined, isLoading: false };
      });

      render(<GitSection projectId={1} />);

      // Section should be in the document
      expect(screen.getByTestId('git-section')).toBeInTheDocument();
    });
  });
});
