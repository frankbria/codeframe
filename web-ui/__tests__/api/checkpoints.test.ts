/**
 * Unit tests for checkpoints API client (T104)
 *
 * Tests:
 * - All API methods (list, create, get, delete, restore, getDiff)
 * - Error handling for all methods
 *
 * Part of Sprint 10 Phase 4 - Checkpoint System (Frontend)
 */

import {
  listCheckpoints,
  createCheckpoint,
  getCheckpoint,
  deleteCheckpoint,
  restoreCheckpoint,
  getCheckpointDiff,
} from '../../src/api/checkpoints';
import type {
  Checkpoint,
  CreateCheckpointRequest,
  RestoreCheckpointResponse,
  CheckpointDiff,
} from '../../src/types/checkpoints';

// Mock fetch
global.fetch = jest.fn();

const API_BASE_URL = 'http://localhost:8080';

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
    (global.fetch as jest.Mock).mockClear();
  });

  describe('listCheckpoints', () => {
    it('test_list_checkpoints_success', async () => {
      // ARRANGE
      const mockCheckpoints = [mockCheckpoint];
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => mockCheckpoints,
      });

      // ACT
      const result = await listCheckpoints(123);

      // ASSERT
      expect(global.fetch).toHaveBeenCalledWith(
        `${API_BASE_URL}/api/projects/123/checkpoints`,
        {
          method: 'GET',
          headers: { 'Content-Type': 'application/json' },
        }
      );
      expect(result).toEqual(mockCheckpoints);
    });

    it('test_list_checkpoints_error', async () => {
      // ARRANGE
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 500,
        statusText: 'Internal Server Error',
        json: async () => ({ detail: 'Database connection failed' }),
      });

      // ACT & ASSERT
      await expect(listCheckpoints(123)).rejects.toThrow('Database connection failed');
    });

    it('test_list_checkpoints_network_error', async () => {
      // ARRANGE
      (global.fetch as jest.Mock).mockRejectedValueOnce(new Error('Network error'));

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

      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => mockCheckpoint,
      });

      // ACT
      const result = await createCheckpoint(123, request);

      // ASSERT
      expect(global.fetch).toHaveBeenCalledWith(
        `${API_BASE_URL}/api/projects/123/checkpoints`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(request),
        }
      );
      expect(result).toEqual(mockCheckpoint);
    });

    it('test_create_checkpoint_error', async () => {
      // ARRANGE
      const request: CreateCheckpointRequest = {
        name: 'New Checkpoint',
      };

      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 400,
        statusText: 'Bad Request',
        json: async () => ({ detail: 'Invalid checkpoint name' }),
      });

      // ACT & ASSERT
      await expect(createCheckpoint(123, request)).rejects.toThrow('Invalid checkpoint name');
    });

    it('test_create_checkpoint_json_parse_error', async () => {
      // ARRANGE
      const request: CreateCheckpointRequest = {
        name: 'New Checkpoint',
      };

      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 500,
        statusText: 'Internal Server Error',
        json: async () => {
          throw new Error('Invalid JSON');
        },
      });

      // ACT & ASSERT
      await expect(createCheckpoint(123, request)).rejects.toThrow(
        'Failed to create checkpoint'
      );
    });
  });

  describe('getCheckpoint', () => {
    it('test_get_checkpoint_success', async () => {
      // ARRANGE
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => mockCheckpoint,
      });

      // ACT
      const result = await getCheckpoint(123, 1);

      // ASSERT
      expect(global.fetch).toHaveBeenCalledWith(
        `${API_BASE_URL}/api/projects/123/checkpoints/1`,
        {
          method: 'GET',
          headers: { 'Content-Type': 'application/json' },
        }
      );
      expect(result).toEqual(mockCheckpoint);
    });

    it('test_get_checkpoint_not_found', async () => {
      // ARRANGE
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 404,
        statusText: 'Not Found',
        json: async () => ({ detail: 'Checkpoint not found' }),
      });

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

      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse,
      });

      // ACT
      const result = await deleteCheckpoint(123, 1);

      // ASSERT
      expect(global.fetch).toHaveBeenCalledWith(
        `${API_BASE_URL}/api/projects/123/checkpoints/1`,
        {
          method: 'DELETE',
          headers: { 'Content-Type': 'application/json' },
        }
      );
      expect(result).toEqual(mockResponse);
    });

    it('test_delete_checkpoint_error', async () => {
      // ARRANGE
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 403,
        statusText: 'Forbidden',
        json: async () => ({ detail: 'Permission denied' }),
      });

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

      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse,
      });

      // ACT
      const result = await restoreCheckpoint(123, 1, true);

      // ASSERT
      expect(global.fetch).toHaveBeenCalledWith(
        `${API_BASE_URL}/api/projects/123/checkpoints/1/restore`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ confirm_restore: true }),
        }
      );
      expect(result).toEqual(mockResponse);
    });

    it('test_restore_checkpoint_not_confirmed', async () => {
      // ARRANGE
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 400,
        statusText: 'Bad Request',
        json: async () => ({ detail: 'Confirmation required' }),
      });

      // ACT & ASSERT
      await expect(restoreCheckpoint(123, 1, false)).rejects.toThrow('Confirmation required');
    });

    it('test_restore_checkpoint_conflict', async () => {
      // ARRANGE
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 409,
        statusText: 'Conflict',
        json: async () => ({ detail: 'Git conflict detected' }),
      });

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

      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => mockDiff,
      });

      // ACT
      const result = await getCheckpointDiff(123, 1);

      // ASSERT
      expect(global.fetch).toHaveBeenCalledWith(
        `${API_BASE_URL}/api/projects/123/checkpoints/1/diff`,
        {
          method: 'GET',
          headers: { 'Content-Type': 'application/json' },
        }
      );
      expect(result).toEqual(mockDiff);
    });

    it('test_get_checkpoint_diff_error', async () => {
      // ARRANGE
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 404,
        statusText: 'Not Found',
        json: async () => ({ detail: 'Checkpoint not found' }),
      });

      // ACT & ASSERT
      await expect(getCheckpointDiff(123, 999)).rejects.toThrow('Checkpoint not found');
    });

    it('test_get_checkpoint_diff_git_error', async () => {
      // ARRANGE
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 500,
        statusText: 'Internal Server Error',
        json: async () => ({ detail: 'Git command failed' }),
      });

      // ACT & ASSERT
      await expect(getCheckpointDiff(123, 1)).rejects.toThrow('Git command failed');
    });
  });

  describe('Error handling edge cases', () => {
    it('test_handles_empty_error_response', async () => {
      // ARRANGE
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 500,
        statusText: 'Internal Server Error',
        json: async () => ({}), // Empty error object
      });

      // ACT & ASSERT
      await expect(listCheckpoints(123)).rejects.toThrow('HTTP 500: Internal Server Error');
    });

    it('test_handles_malformed_error_response', async () => {
      // ARRANGE
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 400,
        statusText: 'Bad Request',
        json: async () => {
          throw new Error('Malformed JSON');
        },
      });

      // ACT & ASSERT
      await expect(listCheckpoints(123)).rejects.toThrow('Failed to list checkpoints');
    });

    it('test_handles_network_timeout', async () => {
      // ARRANGE
      (global.fetch as jest.Mock).mockImplementation(
        () => new Promise((_, reject) => setTimeout(() => reject(new Error('Timeout')), 100))
      );

      // ACT & ASSERT
      await expect(listCheckpoints(123)).rejects.toThrow('Timeout');
    });
  });
});
