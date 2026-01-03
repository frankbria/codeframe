/**
 * Unit tests for checkpoints API client (T104)
 *
 * Tests:
 * - All API methods (list, create, get, delete, restore, getDiff)
 * - Error handling for all methods
 *
 * Part of Sprint 10 Phase 4 - Checkpoint System (Frontend)
 */

// Mock the api-client module BEFORE imports
jest.mock('../../src/lib/api-client', () => ({
  authFetch: jest.fn(),
}));

import {
  listCheckpoints,
  createCheckpoint,
  getCheckpoint,
  deleteCheckpoint,
  restoreCheckpoint,
  getCheckpointDiff,
} from '../../src/api/checkpoints';
import { authFetch } from '../../src/lib/api-client';
import type {
  Checkpoint,
  CreateCheckpointRequest,
  RestoreCheckpointResponse,
  CheckpointDiff,
} from '../../src/types/checkpoints';

const mockAuthFetch = authFetch as jest.MockedFunction<typeof authFetch>;

describe('Checkpoints API Client', () => {
  const mockCheckpoint: Checkpoint = {
    id: 1,
    project_id: 123,
    name: 'Sprint 10 Phase 3 Complete',
    description: 'All backend tests passing',
    trigger: 'manual',
    git_commit: 'abc123def456',
    database_backup_path: '/backups/checkpoint_1.db',
    context_snapshot_path: '/backups/checkpoint_1_context.json',
    metadata: {
      project_id: 123,
      phase: 'Phase 3',
      tasks_completed: 45,
      tasks_total: 60,
      agents_active: ['backend-001', 'test-001'],
      last_task_completed: 'T097: Add checkpoint API tests',
      context_items_count: 150,
      total_cost_usd: 12.5,
    },
    created_at: '2025-11-23T10:30:00Z',
  };

  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('listCheckpoints', () => {
    it('test_list_checkpoints_success', async () => {
      // ARRANGE
      const mockCheckpoints = [mockCheckpoint];
      mockAuthFetch.mockResolvedValueOnce(mockCheckpoints);

      // ACT
      const result = await listCheckpoints(123);

      // ASSERT
      expect(mockAuthFetch).toHaveBeenCalledWith(
        'http://localhost:8080/api/projects/123/checkpoints'
      );
      expect(result).toEqual(mockCheckpoints);
    });

    it('test_list_checkpoints_error', async () => {
      // ARRANGE
      mockAuthFetch.mockRejectedValueOnce(new Error('Request failed: 500 Database connection failed'));

      // ACT & ASSERT
      await expect(listCheckpoints(123)).rejects.toThrow('Database connection failed');
    });

    it('test_list_checkpoints_network_error', async () => {
      // ARRANGE
      mockAuthFetch.mockRejectedValueOnce(new Error('Network error'));

      // ACT & ASSERT
      await expect(listCheckpoints(123)).rejects.toThrow('Network error');
    });
  });

  describe('createCheckpoint', () => {
    it('test_create_checkpoint_success', async () => {
      // ARRANGE
      const request: CreateCheckpointRequest = {
        name: 'New Checkpoint',
        description: 'Test checkpoint',
        trigger: 'manual',
      };

      mockAuthFetch.mockResolvedValueOnce(mockCheckpoint);

      // ACT
      const result = await createCheckpoint(123, request);

      // ASSERT
      expect(mockAuthFetch).toHaveBeenCalledWith(
        'http://localhost:8080/api/projects/123/checkpoints',
        {
          method: 'POST',
          body: request,
        }
      );
      expect(result).toEqual(mockCheckpoint);
    });

    it('test_create_checkpoint_error', async () => {
      // ARRANGE
      const request: CreateCheckpointRequest = {
        name: 'New Checkpoint',
      };

      mockAuthFetch.mockRejectedValueOnce(new Error('Request failed: 400 Invalid checkpoint name'));

      // ACT & ASSERT
      await expect(createCheckpoint(123, request)).rejects.toThrow('Invalid checkpoint name');
    });

    it('test_create_checkpoint_server_error', async () => {
      // ARRANGE
      const request: CreateCheckpointRequest = {
        name: 'New Checkpoint',
      };

      mockAuthFetch.mockRejectedValueOnce(new Error('Request failed: 500 Internal Server Error'));

      // ACT & ASSERT
      await expect(createCheckpoint(123, request)).rejects.toThrow('Internal Server Error');
    });
  });

  describe('getCheckpoint', () => {
    it('test_get_checkpoint_success', async () => {
      // ARRANGE
      mockAuthFetch.mockResolvedValueOnce(mockCheckpoint);

      // ACT
      const result = await getCheckpoint(123, 1);

      // ASSERT
      expect(mockAuthFetch).toHaveBeenCalledWith(
        'http://localhost:8080/api/projects/123/checkpoints/1'
      );
      expect(result).toEqual(mockCheckpoint);
    });

    it('test_get_checkpoint_not_found', async () => {
      // ARRANGE
      mockAuthFetch.mockRejectedValueOnce(new Error('Request failed: 404 Checkpoint not found'));

      // ACT & ASSERT
      await expect(getCheckpoint(123, 999)).rejects.toThrow('Checkpoint not found');
    });
  });

  describe('deleteCheckpoint', () => {
    it('test_delete_checkpoint_success', async () => {
      // ARRANGE
      const mockResponse = {
        success: true,
        message: 'Checkpoint deleted successfully',
      };

      mockAuthFetch.mockResolvedValueOnce(mockResponse);

      // ACT
      const result = await deleteCheckpoint(123, 1);

      // ASSERT
      expect(mockAuthFetch).toHaveBeenCalledWith(
        'http://localhost:8080/api/projects/123/checkpoints/1',
        { method: 'DELETE' }
      );
      expect(result).toEqual(mockResponse);
    });

    it('test_delete_checkpoint_error', async () => {
      // ARRANGE
      mockAuthFetch.mockRejectedValueOnce(new Error('Request failed: 403 Permission denied'));

      // ACT & ASSERT
      await expect(deleteCheckpoint(123, 1)).rejects.toThrow('Permission denied');
    });
  });

  describe('restoreCheckpoint', () => {
    it('test_restore_checkpoint_success', async () => {
      // ARRANGE
      const mockResponse: RestoreCheckpointResponse = {
        success: true,
        git_commit: 'abc123def456',
        restored_at: '2025-11-23T12:00:00Z',
        message: 'Checkpoint restored successfully',
      };

      mockAuthFetch.mockResolvedValueOnce(mockResponse);

      // ACT
      const result = await restoreCheckpoint(123, 1, true);

      // ASSERT
      expect(mockAuthFetch).toHaveBeenCalledWith(
        'http://localhost:8080/api/projects/123/checkpoints/1/restore',
        {
          method: 'POST',
          body: { confirm_restore: true },
        }
      );
      expect(result).toEqual(mockResponse);
    });

    it('test_restore_checkpoint_not_confirmed', async () => {
      // ARRANGE
      mockAuthFetch.mockRejectedValueOnce(new Error('Request failed: 400 Confirmation required'));

      // ACT & ASSERT
      await expect(restoreCheckpoint(123, 1, false)).rejects.toThrow('Confirmation required');
    });

    it('test_restore_checkpoint_conflict', async () => {
      // ARRANGE
      mockAuthFetch.mockRejectedValueOnce(new Error('Request failed: 409 Git conflict detected'));

      // ACT & ASSERT
      await expect(restoreCheckpoint(123, 1, true)).rejects.toThrow('Git conflict detected');
    });
  });

  describe('getCheckpointDiff', () => {
    it('test_get_checkpoint_diff_success', async () => {
      // ARRANGE
      const mockDiff: CheckpointDiff = {
        files_changed: 5,
        insertions: 120,
        deletions: 45,
        diff: 'diff --git a/file.py b/file.py\n...',
      };

      mockAuthFetch.mockResolvedValueOnce(mockDiff);

      // ACT
      const result = await getCheckpointDiff(123, 1);

      // ASSERT
      expect(mockAuthFetch).toHaveBeenCalledWith(
        'http://localhost:8080/api/projects/123/checkpoints/1/diff',
        { signal: undefined }
      );
      expect(result).toEqual(mockDiff);
    });

    it('test_get_checkpoint_diff_with_signal', async () => {
      // ARRANGE
      const mockDiff: CheckpointDiff = {
        files_changed: 5,
        insertions: 120,
        deletions: 45,
        diff: 'diff --git a/file.py b/file.py\n...',
      };
      const abortController = new AbortController();

      mockAuthFetch.mockResolvedValueOnce(mockDiff);

      // ACT
      const result = await getCheckpointDiff(123, 1, abortController.signal);

      // ASSERT
      expect(mockAuthFetch).toHaveBeenCalledWith(
        'http://localhost:8080/api/projects/123/checkpoints/1/diff',
        { signal: abortController.signal }
      );
      expect(result).toEqual(mockDiff);
    });

    it('test_get_checkpoint_diff_error', async () => {
      // ARRANGE
      mockAuthFetch.mockRejectedValueOnce(new Error('Request failed: 404 Checkpoint not found'));

      // ACT & ASSERT
      await expect(getCheckpointDiff(123, 999)).rejects.toThrow('Checkpoint not found');
    });

    it('test_get_checkpoint_diff_git_error', async () => {
      // ARRANGE
      mockAuthFetch.mockRejectedValueOnce(new Error('Request failed: 500 Git command failed'));

      // ACT & ASSERT
      await expect(getCheckpointDiff(123, 1)).rejects.toThrow('Git command failed');
    });
  });

  describe('Error handling edge cases', () => {
    it('test_handles_not_authenticated', async () => {
      // ARRANGE
      mockAuthFetch.mockRejectedValueOnce(new Error('Not authenticated'));

      // ACT & ASSERT
      await expect(listCheckpoints(123)).rejects.toThrow('Not authenticated');
    });

    it('test_handles_network_timeout', async () => {
      // ARRANGE
      mockAuthFetch.mockRejectedValueOnce(new Error('Timeout'));

      // ACT & ASSERT
      await expect(listCheckpoints(123)).rejects.toThrow('Timeout');
    });
  });
});
