/**
 * Git Types Test
 *
 * Tests for Git-related TypeScript type definitions.
 * Ensures types are properly exported and can be used correctly.
 */

import type {
  GitBranch,
  GitCommit,
  GitStatus,
  GitState,
  BranchStatus,
} from '@/types/git';

describe('Git Types', () => {
  describe('GitBranch', () => {
    it('should allow valid branch data', () => {
      const branch: GitBranch = {
        id: 1,
        branch_name: 'feature/auth-flow',
        issue_id: 10,
        status: 'active',
        created_at: '2025-01-01T00:00:00Z',
      };

      expect(branch.id).toBe(1);
      expect(branch.branch_name).toBe('feature/auth-flow');
      expect(branch.status).toBe('active');
    });

    it('should allow optional merged_at and merge_commit', () => {
      const mergedBranch: GitBranch = {
        id: 2,
        branch_name: 'feature/completed',
        issue_id: 20,
        status: 'merged',
        created_at: '2025-01-01T00:00:00Z',
        merged_at: '2025-01-02T00:00:00Z',
        merge_commit: 'abc123def',
      };

      expect(mergedBranch.merged_at).toBe('2025-01-02T00:00:00Z');
      expect(mergedBranch.merge_commit).toBe('abc123def');
    });
  });

  describe('GitCommit', () => {
    it('should allow valid commit data', () => {
      const commit: GitCommit = {
        hash: 'abc123def456789',
        short_hash: 'abc123d',
        message: 'feat: Add user authentication',
        author: 'Agent <agent@codeframe.io>',
        timestamp: '2025-01-01T12:00:00Z',
      };

      expect(commit.hash).toBe('abc123def456789');
      expect(commit.short_hash).toBe('abc123d');
      expect(commit.message).toBe('feat: Add user authentication');
    });

    it('should allow optional files_changed', () => {
      const commitWithFiles: GitCommit = {
        hash: 'abc123def456789',
        short_hash: 'abc123d',
        message: 'fix: Bug fix',
        author: 'Agent <agent@codeframe.io>',
        timestamp: '2025-01-01T12:00:00Z',
        files_changed: 5,
      };

      expect(commitWithFiles.files_changed).toBe(5);
    });
  });

  describe('GitStatus', () => {
    it('should allow valid git status data', () => {
      const status: GitStatus = {
        current_branch: 'main',
        is_dirty: false,
        modified_files: [],
        untracked_files: [],
        staged_files: [],
      };

      expect(status.current_branch).toBe('main');
      expect(status.is_dirty).toBe(false);
    });

    it('should allow files in all categories', () => {
      const dirtyStatus: GitStatus = {
        current_branch: 'feature/new',
        is_dirty: true,
        modified_files: ['src/app.ts', 'src/lib.ts'],
        untracked_files: ['new-file.txt'],
        staged_files: ['staged.ts'],
      };

      expect(dirtyStatus.modified_files).toHaveLength(2);
      expect(dirtyStatus.untracked_files).toHaveLength(1);
      expect(dirtyStatus.staged_files).toHaveLength(1);
    });
  });

  describe('GitState', () => {
    it('should allow null status (loading state)', () => {
      const state: GitState = {
        status: null,
        recentCommits: [],
        branches: [],
        isLoading: true,
        error: null,
      };

      expect(state.status).toBeNull();
      expect(state.isLoading).toBe(true);
    });

    it('should allow populated state with all data', () => {
      const state: GitState = {
        status: {
          current_branch: 'main',
          is_dirty: false,
          modified_files: [],
          untracked_files: [],
          staged_files: [],
        },
        recentCommits: [
          {
            hash: 'abc123',
            short_hash: 'abc123',
            message: 'Initial commit',
            author: 'Developer',
            timestamp: '2025-01-01T00:00:00Z',
          },
        ],
        branches: [
          {
            id: 1,
            branch_name: 'main',
            issue_id: 0,
            status: 'active',
            created_at: '2025-01-01T00:00:00Z',
          },
        ],
        isLoading: false,
        error: null,
      };

      expect(state.status?.current_branch).toBe('main');
      expect(state.recentCommits).toHaveLength(1);
      expect(state.branches).toHaveLength(1);
    });

    it('should allow error state', () => {
      const state: GitState = {
        status: null,
        recentCommits: [],
        branches: [],
        isLoading: false,
        error: 'Failed to fetch git status',
      };

      expect(state.error).toBe('Failed to fetch git status');
    });
  });

  describe('BranchStatus', () => {
    it('should only allow valid status values', () => {
      const activeStatus: BranchStatus = 'active';
      const mergedStatus: BranchStatus = 'merged';
      const abandonedStatus: BranchStatus = 'abandoned';

      expect(activeStatus).toBe('active');
      expect(mergedStatus).toBe('merged');
      expect(abandonedStatus).toBe('abandoned');
    });
  });
});
