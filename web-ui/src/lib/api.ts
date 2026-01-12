/**
 * API client for CodeFRAME Status Server
 */

import axios from 'axios';
import type { Project, Agent, Blocker, ActivityItem, ProjectResponse, StartProjectResponse } from '@/types';
import type { PRDResponse, IssuesResponse, DiscoveryProgressResponse } from '@/types/api';
import type { Task } from '@/types/agentState';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8080';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add auth token to all requests
api.interceptors.request.use((config) => {
  if (typeof window !== 'undefined') {
    const token = localStorage.getItem('auth_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
  }
  return config;
});

// Response interceptor for error logging and handling
api.interceptors.response.use(
  (response) => response,
  (error) => {
    // Log authentication errors with endpoint details
    if (error.response?.status === 401) {
      const endpoint = error.config?.url || 'unknown endpoint';
      console.error(`[API] 401 Unauthorized at ${endpoint}`, {
        method: error.config?.method?.toUpperCase(),
        url: endpoint,
        hasAuthHeader: !!error.config?.headers?.Authorization,
      });

      // In development, provide more context
      if (process.env.NODE_ENV === 'development') {
        console.warn(
          '[API] Authentication failed. Check that:\n' +
          '  1. User is logged in (auth_token exists in localStorage)\n' +
          '  2. Token has not expired\n' +
          '  3. Backend JWT validation is configured correctly'
        );
      }
    }

    // Log other errors in development
    if (process.env.NODE_ENV === 'development' && error.response) {
      console.error(`[API] ${error.response.status} at ${error.config?.url}`, {
        data: error.response.data,
        status: error.response.status,
      });
    }

    return Promise.reject(error);
  }
);

export const projectsApi = {
  list: () => api.get<{ projects: Project[] }>('/api/projects'),
  createProject: (name: string, description: string) =>
    api.post<ProjectResponse>('/api/projects', {
      name,
      description,
      source_type: 'empty',
    }),
  startProject: (projectId: number) =>
    api.post<StartProjectResponse>(`/api/projects/${projectId}/start`),
  getStatus: (projectId: number) =>
    api.get<Project>(`/api/projects/${projectId}/status`),
  pause: (projectId: number) =>
    api.post(`/api/projects/${projectId}/pause`),
  resume: (projectId: number) =>
    api.post(`/api/projects/${projectId}/resume`),
  getPRD: (projectId: number | string) =>
    api.get<PRDResponse>(`/api/projects/${projectId}/prd`),
  getIssues: (projectId: number | string, options?: { cursor?: string; include?: 'tasks' }) =>
    api.get<IssuesResponse>(`/api/projects/${projectId}/issues`, {
      params: {
        ...(options?.cursor && { cursor: options.cursor }),
        ...(options?.include && { include: options.include }),
      },
    }),
  getDiscoveryProgress: (projectId: number | string) =>
    api.get<DiscoveryProgressResponse>(`/api/projects/${projectId}/discovery/progress`),
  restartDiscovery: (projectId: number | string) =>
    api.post<{ success: boolean; message: string; state: string }>(
      `/api/projects/${projectId}/discovery/restart`
    ),
  retryPrdGeneration: (projectId: number | string) =>
    api.post<{ success: boolean; message: string }>(
      `/api/projects/${projectId}/discovery/generate-prd`
    ),
  generateTasks: (projectId: number | string) =>
    api.post<{ success: boolean; message: string; tasks_already_exist?: boolean }>(
      `/api/projects/${projectId}/discovery/generate-tasks`
    ),
  /**
   * Approve task breakdown and transition project to development phase.
   *
   * The backend uses an exclusion model - all tasks are approved by default,
   * and you specify which ones to exclude. This function converts from the
   * frontend's selection model (which tasks ARE selected).
   *
   * @param projectId - Project ID
   * @param selectedTaskIds - Array of task IDs that the user selected (will be approved)
   * @param allTaskIds - Array of all task IDs (needed to compute exclusions)
   * @returns Approval response with success status and counts
   */
  approveTaskBreakdown: (projectId: number, selectedTaskIds: string[], allTaskIds: string[]) => {
    // Compute excluded task IDs: tasks that are in allTaskIds but NOT in selectedTaskIds
    const selectedSet = new Set(selectedTaskIds);
    const excludedTaskIds = allTaskIds
      .filter((id) => !selectedSet.has(id))
      .map((id) => {
        // Extract numeric ID from strings like 'task-4' or just '4'
        // Defensive: only accept 'prefix-digits' or pure digits, reject malformed IDs
        const match = id.match(/-(\d+)$/) || id.match(/^(\d+)$/);
        if (!match) return NaN;
        return parseInt(match[1], 10);
      })
      .filter((id) => !isNaN(id));

    return api.post<{
      success: boolean;
      message: string;
      approved_count: number;
      project_phase: string;
    }>(`/api/projects/${projectId}/tasks/approve`, {
      approved: true,
      excluded_task_ids: excludedTaskIds,
    });
  },
};

export const agentsApi = {
  list: (projectId: number) =>
    api.get<{ agents: Agent[] }>(`/api/projects/${projectId}/agents`),
};

export const tasksApi = {
  list: (projectId: number, filters?: { status?: string; limit?: number }) =>
    api.get<{ tasks: Task[]; total: number }>(`/api/projects/${projectId}/tasks`, {
      params: filters,
    }),
  /**
   * Manually trigger assignment for pending unassigned tasks (Issue #248 fix).
   *
   * This endpoint allows users to restart the multi-agent execution process
   * when tasks are stuck in 'pending' state with no agent assigned.
   *
   * @param projectId - Project ID
   * @returns Assignment response with pending count and status message
   */
  assignPending: (projectId: number) =>
    api.post<{
      success: boolean;
      pending_count: number;
      message: string;
    }>(`/api/projects/${projectId}/tasks/assign`),
};

export const blockersApi = {
  list: (projectId: number, status?: string) =>
    api.get<{ blockers: Blocker[] }>(`/api/projects/${projectId}/blockers`, {
      params: status ? { status } : {},
    }),
  get: (blockerId: number) =>
    api.get<Blocker>(`/api/blockers/${blockerId}`),
  resolve: (blockerId: number, answer: string) =>
    api.post<{ blocker_id: number; status: string; resolved_at: string }>(
      `/api/blockers/${blockerId}/resolve`,
      { answer }
    ),

  // Aliases for T019 compatibility
  fetchBlockers: (projectId: number, status?: string) =>
    api.get<{ blockers: Blocker[] }>(`/api/projects/${projectId}/blockers`, {
      params: status ? { status } : {},
    }),
  fetchBlocker: (blockerId: number) =>
    api.get<Blocker>(`/api/blockers/${blockerId}`),
};

/**
 * Resolve a blocker with user's answer (T023).
 *
 * @param blockerId - ID of the blocker to resolve
 * @param answer - User's answer to the blocker question
 * @returns Promise resolving to success indicator
 */
export async function resolveBlocker(blockerId: number, answer: string): Promise<{ success: boolean }> {
  try {
    await blockersApi.resolve(blockerId, answer);
    return { success: true };
  } catch (error) {
    throw error;
  }
}

export const activityApi = {
  list: (projectId: number, limit?: number) =>
    api.get<{ activity: ActivityItem[] }>(`/api/projects/${projectId}/activity`, {
      params: { limit },
    }),
};

export const chatApi = {
  send: (projectId: number, message: string) =>
    api.post<{ response: string; timestamp: string }>(
      `/api/projects/${projectId}/chat`,
      { message }
    ),
  getHistory: (projectId: number, limit?: number, offset?: number) =>
    api.get<{ messages: { role: string; content: string; timestamp: string }[] }>(
      `/api/projects/${projectId}/chat/history`,
      { params: { limit, offset } }
    ),
};

export default api;
