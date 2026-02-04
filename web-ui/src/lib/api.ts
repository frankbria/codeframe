/**
 * API client for CodeFRAME v2 endpoints
 */
import axios, { AxiosInstance, AxiosError } from 'axios';
import type {
  WorkspaceResponse,
  WorkspaceExistsResponse,
  TaskListResponse,
  ApiError,
} from '@/types';

// Create axios instance with base configuration
const createApiClient = (): AxiosInstance => {
  const client = axios.create({
    baseURL: process.env.NEXT_PUBLIC_API_URL || '',
    headers: {
      'Content-Type': 'application/json',
    },
    withCredentials: true,
  });

  // Add response interceptor for error handling
  client.interceptors.response.use(
    (response) => response,
    (error: AxiosError<ApiError>) => {
      // Transform error for consistent handling
      const apiError: ApiError = {
        detail: error.response?.data?.detail || error.message || 'An error occurred',
        status_code: error.response?.status,
      };
      return Promise.reject(apiError);
    }
  );

  return client;
};

const api = createApiClient();

// Workspace API methods
export const workspaceApi = {
  /**
   * Check if workspace exists at a path
   */
  checkExists: async (repoPath: string): Promise<WorkspaceExistsResponse> => {
    const response = await api.get<WorkspaceExistsResponse>(
      '/api/v2/workspaces/exists',
      { params: { repo_path: repoPath } }
    );
    return response.data;
  },

  /**
   * Initialize a new workspace
   */
  init: async (
    repoPath: string,
    options?: { techStack?: string; detect?: boolean }
  ): Promise<WorkspaceResponse> => {
    const response = await api.post<WorkspaceResponse>('/api/v2/workspaces', {
      repo_path: repoPath,
      tech_stack: options?.techStack,
      detect: options?.detect ?? true,
    });
    return response.data;
  },

  /**
   * Get current workspace info
   */
  getCurrent: async (workspacePath?: string): Promise<WorkspaceResponse> => {
    const response = await api.get<WorkspaceResponse>(
      '/api/v2/workspaces/current',
      { params: workspacePath ? { workspace_path: workspacePath } : {} }
    );
    return response.data;
  },
};

// Tasks API methods
export const tasksApi = {
  /**
   * Get all tasks with optional status filter
   */
  getAll: async (status?: string): Promise<TaskListResponse> => {
    const response = await api.get<TaskListResponse>('/api/v2/tasks', {
      params: status ? { status } : {},
    });
    return response.data;
  },
};

export default api;
