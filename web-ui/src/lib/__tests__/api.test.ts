/**
 * Tests for API client methods
 * Following TDD methodology - tests written BEFORE implementation
 */

import type { ProjectResponse, StartProjectResponse } from '@/types';

// Create mock functions
const mockPost = jest.fn();
const mockGet = jest.fn();

// Mock axios before importing api module
jest.mock('axios', () => {
  const mockAxiosInstance = {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
    get: (...args: any[]) => mockGet(...args),
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
    post: (...args: any[]) => mockPost(...args),
    put: jest.fn(),
    delete: jest.fn(),
    patch: jest.fn(),
    interceptors: {
      request: {
        use: jest.fn(),
        eject: jest.fn(),
      },
      response: {
        use: jest.fn(),
        eject: jest.fn(),
      },
    },
  };

  return {
    __esModule: true,
    default: {
      create: jest.fn(() => mockAxiosInstance),
    },
  };
});

// Now import the API module after mocking axios
import { projectsApi, blockersApi } from '../api';

beforeEach(() => {
  jest.clearAllMocks();
});

describe('projectsApi.createProject', () => {
  it('should make POST request to /api/projects with correct payload', async () => {
    const mockResponse: ProjectResponse = {
      id: 1,
      name: 'Test Project',
      status: 'init',
      phase: 'discovery',
      created_at: '2025-10-17T12:00:00Z',
      config: {},
    };

    mockPost.mockResolvedValueOnce({
      status: 201,
      data: mockResponse,
    });

    const result = await projectsApi.createProject('Test Project', 'Test project description');

    // Verify POST was called with correct endpoint and payload
    expect(mockPost).toHaveBeenCalledWith('/api/projects', {
      name: 'Test Project',
      description: 'Test project description',
      source_type: 'empty',
    });

    // Verify response
    expect(result.status).toBe(201);
    expect(result.data).toEqual(mockResponse);
  });

  it('should handle 400 Bad Request error', async () => {
    const errorResponse = {
      response: {
        status: 400,
        data: { error: 'Invalid project name' },
      },
    };

    mockPost.mockRejectedValueOnce(errorResponse);

    await expect(
      projectsApi.createProject('', 'Test description')
    ).rejects.toMatchObject(errorResponse);
  });

  it('should handle 409 Conflict error (duplicate project)', async () => {
    const errorResponse = {
      response: {
        status: 409,
        data: { error: 'Project already exists' },
      },
    };

    mockPost.mockRejectedValueOnce(errorResponse);

    await expect(
      projectsApi.createProject('Existing Project', 'A project that already exists')
    ).rejects.toMatchObject(errorResponse);
  });

  it('should handle 500 Internal Server Error', async () => {
    const errorResponse = {
      response: {
        status: 500,
        data: { error: 'Internal server error' },
      },
    };

    mockPost.mockRejectedValueOnce(errorResponse);

    await expect(
      projectsApi.createProject('Test Project', 'Test project description')
    ).rejects.toMatchObject(errorResponse);
  });
});

describe('projectsApi.startProject', () => {
  it('should make POST request to /api/projects/{id}/start', async () => {
    const mockResponse: StartProjectResponse = {
      message: 'Project started successfully',
      status: 'active',
    };

    mockPost.mockResolvedValueOnce({
      status: 202,
      data: mockResponse,
    });

    const result = await projectsApi.startProject(42);

    // Verify correct endpoint was called
    expect(mockPost).toHaveBeenCalledWith('/api/projects/42/start');

    // Verify 202 Accepted response
    expect(result.status).toBe(202);
    expect(result.data).toEqual(mockResponse);
  });

  it('should handle 404 Not Found error (project does not exist)', async () => {
    const errorResponse = {
      response: {
        status: 404,
        data: { error: 'Project not found' },
      },
    };

    mockPost.mockRejectedValueOnce(errorResponse);

    await expect(projectsApi.startProject(999)).rejects.toMatchObject(errorResponse);
  });

  it('should handle 400 Bad Request error (invalid state)', async () => {
    const errorResponse = {
      response: {
        status: 400,
        data: { error: 'Project cannot be started in current state' },
      },
    };

    mockPost.mockRejectedValueOnce(errorResponse);

    await expect(projectsApi.startProject(1)).rejects.toMatchObject(errorResponse);
  });

  it('should handle 500 Internal Server Error', async () => {
    const errorResponse = {
      response: {
        status: 500,
        data: { error: 'Internal server error' },
      },
    };

    mockPost.mockRejectedValueOnce(errorResponse);

    await expect(projectsApi.startProject(1)).rejects.toMatchObject(errorResponse);
  });
});

describe('blockersApi (T019 - 049-human-in-loop)', () => {
  describe('list() method', () => {
    it('should call correct endpoint with projectId', async () => {
      const mockResponse = {
        data: {
          blockers: [
            {
              id: 1,
              agent_id: 'test-agent',
              task_id: 123,
              blocker_type: 'SYNC',
              question: 'Test question?',
              status: 'PENDING',
            },
          ],
        },
      };

      mockGet.mockResolvedValue(mockResponse);

      const result = await blockersApi.list(1);

      expect(mockGet).toHaveBeenCalledWith(
        '/api/projects/1/blockers',
        { params: {} }
      );
      expect(result.data.blockers).toHaveLength(1);
    });

    it('should include status parameter when provided', async () => {
      const mockResponse = { data: { blockers: [] } };
      mockGet.mockResolvedValue(mockResponse);

      await blockersApi.list(1, 'PENDING');

      expect(mockGet).toHaveBeenCalledWith(
        '/api/projects/1/blockers',
        { params: { status: 'PENDING' } }
      );
    });

    it('should omit status parameter when not provided', async () => {
      const mockResponse = { data: { blockers: [] } };
      mockGet.mockResolvedValue(mockResponse);

      await blockersApi.list(1);

      expect(mockGet).toHaveBeenCalledWith(
        '/api/projects/1/blockers',
        { params: {} }
      );
    });

    it('should work with different project IDs', async () => {
      const mockResponse = { data: { blockers: [] } };
      mockGet.mockResolvedValue(mockResponse);

      await blockersApi.list(42);

      expect(mockGet).toHaveBeenCalledWith(
        '/api/projects/42/blockers',
        { params: {} }
      );
    });

    it('should work with different status values', async () => {
      const mockResponse = { data: { blockers: [] } };
      mockGet.mockResolvedValue(mockResponse);

      await blockersApi.list(1, 'RESOLVED');

      expect(mockGet).toHaveBeenCalledWith(
        '/api/projects/1/blockers',
        { params: { status: 'RESOLVED' } }
      );
    });
  });

  describe('get() method', () => {
    it('should call correct endpoint with blockerId', async () => {
      const mockResponse = {
        data: {
          id: 1,
          agent_id: 'test-agent',
          task_id: 123,
          blocker_type: 'SYNC',
          question: 'Test question?',
          status: 'PENDING',
        },
      };

      mockGet.mockResolvedValue(mockResponse);

      const result = await blockersApi.get(1);

      expect(mockGet).toHaveBeenCalledWith('/api/blockers/1');
      expect(result.data.id).toBe(1);
    });

    it('should work with different blocker IDs', async () => {
      const mockResponse = {
        data: {
          id: 999,
          agent_id: 'test-agent',
          task_id: 123,
          blocker_type: 'ASYNC',
          question: 'Another question?',
          status: 'PENDING',
        },
      };

      mockGet.mockResolvedValue(mockResponse);

      const result = await blockersApi.get(999);

      expect(mockGet).toHaveBeenCalledWith('/api/blockers/999');
      expect(result.data.id).toBe(999);
    });
  });

  describe('fetchBlockers() alias method', () => {
    it('should work as alias for list()', async () => {
      const mockResponse = { data: { blockers: [] } };
      mockGet.mockResolvedValue(mockResponse);

      await blockersApi.fetchBlockers(1);

      expect(mockGet).toHaveBeenCalledWith(
        '/api/projects/1/blockers',
        { params: {} }
      );
    });

    it('should support status parameter', async () => {
      const mockResponse = { data: { blockers: [] } };
      mockGet.mockResolvedValue(mockResponse);

      await blockersApi.fetchBlockers(1, 'PENDING');

      expect(mockGet).toHaveBeenCalledWith(
        '/api/projects/1/blockers',
        { params: { status: 'PENDING' } }
      );
    });
  });

  describe('fetchBlocker() alias method', () => {
    it('should work as alias for get()', async () => {
      const mockResponse = {
        data: {
          id: 1,
          agent_id: 'test-agent',
          task_id: 123,
          blocker_type: 'SYNC',
          question: 'Test question?',
          status: 'PENDING',
        },
      };

      mockGet.mockResolvedValue(mockResponse);

      const result = await blockersApi.fetchBlocker(1);

      expect(mockGet).toHaveBeenCalledWith('/api/blockers/1');
      expect(result.data.id).toBe(1);
    });
  });

  describe('resolve() method', () => {
    it('should call correct endpoint with answer', async () => {
      const mockResponse = { data: { success: true } };
      mockPost.mockResolvedValue(mockResponse);

      await blockersApi.resolve(123, 'Use SQLite');

      expect(mockPost).toHaveBeenCalledWith(
        '/api/blockers/123/resolve',
        { answer: 'Use SQLite' }
      );
    });

    it('should work with different blocker IDs', async () => {
      const mockResponse = { data: { success: true } };
      mockPost.mockResolvedValue(mockResponse);

      await blockersApi.resolve(999, 'Test answer');

      expect(mockPost).toHaveBeenCalledWith(
        '/api/blockers/999/resolve',
        { answer: 'Test answer' }
      );
    });
  });

  describe('error handling', () => {
    it('should propagate errors from list()', async () => {
      const mockError = new Error('Network error');
      mockGet.mockRejectedValue(mockError);

      await expect(blockersApi.list(1)).rejects.toThrow('Network error');
    });

    it('should propagate errors from get()', async () => {
      const mockError = new Error('Not found');
      mockGet.mockRejectedValue(mockError);

      await expect(blockersApi.get(1)).rejects.toThrow('Not found');
    });

    it('should propagate errors from resolve()', async () => {
      const mockError = new Error('Unauthorized');
      mockPost.mockRejectedValue(mockError);

      await expect(blockersApi.resolve(123, 'answer')).rejects.toThrow('Unauthorized');
    });
  });
});
