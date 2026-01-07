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
  getIssues: (projectId: number | string, cursor?: string) =>
    api.get<IssuesResponse>(`/api/projects/${projectId}/issues`, {
      params: cursor ? { cursor } : {},
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
    api.post<{ success: boolean; message: string }>(
      `/api/projects/${projectId}/planning/generate-tasks`
    ),
  approveTaskBreakdown: (projectId: number, taskIds: string[]) =>
    api.post<{
      success: boolean;
      message: string;
      approved_count: number;
      project_phase: string;
    }>(`/api/projects/${projectId}/tasks/approve`, { task_ids: taskIds }),
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
