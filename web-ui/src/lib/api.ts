/**
 * API client for CodeFRAME Status Server
 */

import axios from 'axios';
import type { Project, Agent, Task, Blocker, ActivityItem } from '@/types';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8080';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

export const projectsApi = {
  list: () => api.get<{ projects: Project[] }>('/api/projects'),
  getStatus: (projectId: number) =>
    api.get<Project>(`/api/projects/${projectId}/status`),
  pause: (projectId: number) =>
    api.post(`/api/projects/${projectId}/pause`),
  resume: (projectId: number) =>
    api.post(`/api/projects/${projectId}/resume`),
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
  list: (projectId: number) =>
    api.get<{ blockers: Blocker[] }>(`/api/projects/${projectId}/blockers`),
  resolve: (projectId: number, blockerId: number, answer: string) =>
    api.post(`/api/projects/${projectId}/blockers/${blockerId}/resolve`, {
      answer,
    }),
};

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
};

export default api;
