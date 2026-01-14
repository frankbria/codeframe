/**
 * Git API Client Tests
 *
 * Tests for the Git API client functions.
 * Uses mocked fetch to verify correct API calls.
 */

import {
  getGitStatus,
  getCommits,
  getBranches,
  getBranch,
} from '@/api/git';
import type { GitStatus, GitCommit, GitBranch } from '@/types/git';

// Mock localStorage
const mockLocalStorage = {
  getItem: jest.fn((): string | null => 'mock-auth-token'),
  setItem: jest.fn(),
  removeItem: jest.fn(),
  clear: jest.fn(),
  length: 0,
  key: jest.fn(),
};
Object.defineProperty(window, 'localStorage', { value: mockLocalStorage });

// Mock fetch globally
const mockFetch = jest.fn();
global.fetch = mockFetch;

describe('Git API Client', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockLocalStorage.getItem.mockReturnValue('mock-auth-token');
  });

  describe('getGitStatus', () => {
    it('should fetch git status for a project', async () => {
      const mockStatus: GitStatus = {
        current_branch: 'feature/auth',
        is_dirty: false,
        modified_files: [],
        untracked_files: [],
        staged_files: [],
      };

      mockFetch.mockResolvedValueOnce({
        ok: true,
        text: () => Promise.resolve(JSON.stringify(mockStatus)),
      });

      const result = await getGitStatus(123);

      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/projects/123/git/status'),
        expect.objectContaining({
          headers: expect.objectContaining({
            'Authorization': 'Bearer mock-auth-token',
          }),
        })
      );
      expect(result).toEqual(mockStatus);
    });

    it('should throw error when not authenticated', async () => {
      mockLocalStorage.getItem.mockReturnValueOnce(null);

      await expect(getGitStatus(123)).rejects.toThrow('Not authenticated');
    });

    it('should throw error on API failure', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 404,
        text: () => Promise.resolve('Not found'),
      });

      await expect(getGitStatus(123)).rejects.toThrow();
    });
  });

  describe('getCommits', () => {
    it('should fetch commits with default limit', async () => {
      const mockCommits: GitCommit[] = [
        {
          hash: 'abc123def456',
          short_hash: 'abc123d',
          message: 'feat: Add login',
          author: 'Agent',
          timestamp: '2025-01-01T00:00:00Z',
          files_changed: 3,
        },
      ];

      mockFetch.mockResolvedValueOnce({
        ok: true,
        text: () => Promise.resolve(JSON.stringify({ commits: mockCommits })),
      });

      const result = await getCommits(123);

      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/projects/123/git/commits'),
        expect.any(Object)
      );
      expect(result).toEqual(mockCommits);
    });

    it('should fetch commits with custom limit', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        text: () => Promise.resolve(JSON.stringify({ commits: [] })),
      });

      await getCommits(123, { limit: 5 });

      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('limit=5'),
        expect.any(Object)
      );
    });

    it('should fetch commits for specific branch', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        text: () => Promise.resolve(JSON.stringify({ commits: [] })),
      });

      await getCommits(123, { branch: 'feature/test' });

      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('branch=feature%2Ftest'),
        expect.any(Object)
      );
    });
  });

  describe('getBranches', () => {
    it('should fetch branches with default status filter', async () => {
      const mockBranches: GitBranch[] = [
        {
          id: 1,
          branch_name: 'feature/auth',
          issue_id: 10,
          status: 'active',
          created_at: '2025-01-01T00:00:00Z',
        },
      ];

      mockFetch.mockResolvedValueOnce({
        ok: true,
        text: () => Promise.resolve(JSON.stringify({ branches: mockBranches })),
      });

      const result = await getBranches(123);

      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/projects/123/git/branches'),
        expect.any(Object)
      );
      expect(result).toEqual(mockBranches);
    });

    it('should filter branches by status', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        text: () => Promise.resolve(JSON.stringify({ branches: [] })),
      });

      await getBranches(123, 'merged');

      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('status=merged'),
        expect.any(Object)
      );
    });
  });

  describe('getBranch', () => {
    it('should fetch single branch by name', async () => {
      const mockBranch: GitBranch = {
        id: 1,
        branch_name: 'feature/auth',
        issue_id: 10,
        status: 'active',
        created_at: '2025-01-01T00:00:00Z',
      };

      mockFetch.mockResolvedValueOnce({
        ok: true,
        text: () => Promise.resolve(JSON.stringify(mockBranch)),
      });

      const result = await getBranch(123, 'feature/auth');

      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/projects/123/git/branches/feature%2Fauth'),
        expect.any(Object)
      );
      expect(result).toEqual(mockBranch);
    });

    it('should handle branch not found', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 404,
        text: () => Promise.resolve('Branch not found'),
      });

      await expect(getBranch(123, 'nonexistent')).rejects.toThrow();
    });
  });
});
