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
    get: (...args: any[]) => mockGet(...args),
    post: (...args: any[]) => mockPost(...args),
    put: jest.fn(),
    delete: jest.fn(),
    patch: jest.fn(),
  };

  return {
    __esModule: true,
    default: {
      create: jest.fn(() => mockAxiosInstance),
    },
  };
});

// Now import the API module after mocking axios
import { projectsApi } from '../api';

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

    const result = await projectsApi.createProject('Test Project', 'python');

    // Verify POST was called with correct endpoint and payload
    expect(mockPost).toHaveBeenCalledWith('/api/projects', {
      project_name: 'Test Project',
      project_type: 'python',
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
      projectsApi.createProject('', 'python')
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
      projectsApi.createProject('Existing Project', 'python')
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
      projectsApi.createProject('Test Project', 'python')
    ).rejects.toMatchObject(errorResponse);
  });

  it('should support all project types', async () => {
    const projectTypes = ['python', 'javascript', 'typescript', 'java', 'go', 'rust'];

    for (const type of projectTypes) {
      mockPost.mockResolvedValueOnce({
        status: 201,
        data: {
          id: 1,
          name: `Test ${type} Project`,
          status: 'init',
          created_at: '2025-10-17T12:00:00Z',
        },
      });

      await projectsApi.createProject(`Test ${type} Project`, type);

      expect(mockPost).toHaveBeenCalledWith('/api/projects', {
        project_name: `Test ${type} Project`,
        project_type: type,
      });
    }
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
