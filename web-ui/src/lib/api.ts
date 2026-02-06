/**
 * API client for CodeFRAME v2 endpoints
 *
 * All endpoints require a workspace_path to identify which project
 * the operation applies to. The web UI stores this in localStorage
 * and passes it with every request.
 */
import axios, { AxiosInstance, AxiosError } from 'axios';
import type {
  WorkspaceResponse,
  WorkspaceExistsResponse,
  Task,
  TaskStatus,
  TaskListResponse,
  BatchExecutionRequest,
  StartExecutionResponse,
  TaskStartResponse,
  EventListResponse,
  ApiError,
  PrdResponse,
  PrdListResponse,
  PrdDiffResponse,
  StartDiscoveryResponse,
  AnswerResponse,
  DiscoveryStatusResponse,
  GeneratePrdResponse,
  GenerateTasksResponse,
  Blocker,
  BlockerListResponse,
  BatchResponse,
} from '@/types';

// FastAPI validation error format
interface ValidationErrorItem {
  msg: string;
  loc?: (string | number)[];
  type?: string;
}

// Backend error formats:
// 1. Simple string: "Task not found"
// 2. Validation errors: [{msg: "...", loc: [...]}]
// 3. Structured error (from api_error()): {error: "...", code: "...", detail: "..."}
type FastApiErrorDetail = string | ValidationErrorItem[] | { error?: string; detail?: string; code?: string };

/**
 * Normalize FastAPI error detail to a string.
 * FastAPI returns detail as string for simple errors, array for validation errors,
 * or a structured {error, code, detail} object from api_error().
 */
export function normalizeErrorDetail(
  rawDetail: FastApiErrorDetail | undefined,
  fallbackMessage: string
): string {
  if (Array.isArray(rawDetail)) {
    // Join validation error messages
    return rawDetail.map((err) => err.msg).join('; ');
  }
  if (typeof rawDetail === 'object' && rawDetail !== null) {
    // Structured error: combine error + detail for full context
    if (rawDetail.error && rawDetail.detail) {
      return `${rawDetail.error}: ${rawDetail.detail}`;
    }
    return rawDetail.error || rawDetail.detail || fallbackMessage || 'An error occurred';
  }
  return rawDetail || fallbackMessage || 'An error occurred';
}

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
    (error: AxiosError<{ detail?: FastApiErrorDetail }>) => {
      // Transform error for consistent handling
      const apiError: ApiError = {
        detail: normalizeErrorDetail(error.response?.data?.detail, error.message),
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
   * Initialize a new workspace at the given path
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
   * Get workspace info for a specific path
   */
  getByPath: async (workspacePath: string): Promise<WorkspaceResponse> => {
    const response = await api.get<WorkspaceResponse>(
      '/api/v2/workspaces/current',
      { params: { workspace_path: workspacePath } }
    );
    return response.data;
  },
};

// Tasks API methods
export const tasksApi = {
  /**
   * Get all tasks for a workspace
   */
  getAll: async (workspacePath: string, status?: string): Promise<TaskListResponse> => {
    const response = await api.get<TaskListResponse>('/api/v2/tasks', {
      params: {
        workspace_path: workspacePath,
        ...(status ? { status } : {}),
      },
    });
    return response.data;
  },

  /**
   * Get a single task by ID
   */
  getOne: async (workspacePath: string, taskId: string): Promise<Task> => {
    const response = await api.get<Task>(`/api/v2/tasks/${taskId}`, {
      params: { workspace_path: workspacePath },
    });
    return response.data;
  },

  /**
   * Update a task's status (e.g. BACKLOG → READY)
   */
  updateStatus: async (
    workspacePath: string,
    taskId: string,
    status: TaskStatus
  ): Promise<Task> => {
    const response = await api.patch<Task>(
      `/api/v2/tasks/${taskId}`,
      { status },
      { params: { workspace_path: workspacePath } }
    );
    return response.data;
  },

  /**
   * Start execution of a single task
   */
  startExecution: async (
    workspacePath: string,
    taskId: string
  ): Promise<TaskStartResponse> => {
    const response = await api.post<TaskStartResponse>(
      `/api/v2/tasks/${taskId}/start`,
      {},
      { params: { workspace_path: workspacePath, execute: true } }
    );
    return response.data;
  },

  /**
   * Start batch execution of multiple tasks
   */
  executeBatch: async (
    workspacePath: string,
    request: BatchExecutionRequest
  ): Promise<StartExecutionResponse> => {
    const response = await api.post<StartExecutionResponse>(
      '/api/v2/tasks/execute',
      request,
      { params: { workspace_path: workspacePath } }
    );
    return response.data;
  },

  /**
   * Stop a running task execution
   */
  stopExecution: async (workspacePath: string, taskId: string): Promise<void> => {
    await api.post(`/api/v2/tasks/${encodeURIComponent(taskId)}/stop`, {}, {
      params: { workspace_path: workspacePath },
    });
  },

  /**
   * Resume a blocked task execution
   */
  resumeExecution: async (workspacePath: string, taskId: string): Promise<void> => {
    await api.post(`/api/v2/tasks/${encodeURIComponent(taskId)}/resume`, {}, {
      params: { workspace_path: workspacePath },
    });
  },
};

// Events API methods
export const eventsApi = {
  /**
   * Get recent events for a workspace
   */
  getRecent: async (
    workspacePath: string,
    options?: { limit?: number; sinceId?: number }
  ): Promise<EventListResponse> => {
    const response = await api.get<EventListResponse>('/api/v2/events', {
      params: {
        workspace_path: workspacePath,
        limit: options?.limit ?? 20,
        ...(options?.sinceId ? { since_id: options.sinceId } : {}),
      },
    });
    return response.data;
  },
};

// Blockers API methods
export const blockersApi = {
  /**
   * Get blockers, optionally filtered by task
   */
  getForTask: async (
    workspacePath: string,
    taskId: string
  ): Promise<BlockerListResponse> => {
    const response = await api.get<BlockerListResponse>('/api/v2/blockers', {
      params: { workspace_path: workspacePath, task_id: taskId },
    });
    return response.data;
  },

  /**
   * Answer a blocker (also resets the associated task to READY)
   */
  answer: async (
    workspacePath: string,
    blockerId: string,
    answer: string
  ): Promise<Blocker> => {
    const response = await api.post<Blocker>(
      `/api/v2/blockers/${encodeURIComponent(blockerId)}/answer`,
      { answer },
      { params: { workspace_path: workspacePath } }
    );
    return response.data;
  },

  /**
   * Mark a blocker as resolved (must be answered first)
   */
  resolve: async (workspacePath: string, blockerId: string): Promise<Blocker> => {
    const response = await api.post<Blocker>(
      `/api/v2/blockers/${encodeURIComponent(blockerId)}/resolve`,
      {},
      { params: { workspace_path: workspacePath } }
    );
    return response.data;
  },
};

// Batches API methods
export const batchesApi = {
  /**
   * Get batch details including per-task results
   */
  get: async (workspacePath: string, batchId: string): Promise<BatchResponse> => {
    const response = await api.get<BatchResponse>(`/api/v2/batches/${encodeURIComponent(batchId)}`, {
      params: { workspace_path: workspacePath },
    });
    return response.data;
  },

  /**
   * Stop a running batch
   */
  stop: async (workspacePath: string, batchId: string): Promise<BatchResponse> => {
    const response = await api.post<BatchResponse>(
      `/api/v2/batches/${encodeURIComponent(batchId)}/stop`,
      {},
      { params: { workspace_path: workspacePath } }
    );
    return response.data;
  },

  /**
   * Cancel a running batch
   */
  cancel: async (workspacePath: string, batchId: string): Promise<BatchResponse> => {
    const response = await api.post<BatchResponse>(
      `/api/v2/batches/${encodeURIComponent(batchId)}/cancel`,
      {},
      { params: { workspace_path: workspacePath } }
    );
    return response.data;
  },
};

// PRD API methods
export const prdApi = {
  getAll: async (workspacePath: string): Promise<PrdListResponse> => {
    const response = await api.get<PrdListResponse>('/api/v2/prd', {
      params: { workspace_path: workspacePath },
    });
    return response.data;
  },

  getLatest: async (workspacePath: string): Promise<PrdResponse> => {
    const response = await api.get<PrdResponse>('/api/v2/prd/latest', {
      params: { workspace_path: workspacePath },
    });
    return response.data;
  },

  getById: async (prdId: string, workspacePath: string): Promise<PrdResponse> => {
    const response = await api.get<PrdResponse>(`/api/v2/prd/${prdId}`, {
      params: { workspace_path: workspacePath },
    });
    return response.data;
  },

  create: async (
    workspacePath: string,
    content: string,
    title?: string,
    metadata?: Record<string, unknown>
  ): Promise<PrdResponse> => {
    const response = await api.post<PrdResponse>(
      '/api/v2/prd',
      { content, ...(title ? { title } : {}), ...(metadata ? { metadata } : {}) },
      { params: { workspace_path: workspacePath } }
    );
    return response.data;
  },

  delete: async (prdId: string, workspacePath: string): Promise<void> => {
    await api.delete(`/api/v2/prd/${prdId}`, {
      params: { workspace_path: workspacePath },
    });
  },

  getVersions: async (prdId: string, workspacePath: string): Promise<PrdResponse[]> => {
    const response = await api.get<PrdResponse[]>(`/api/v2/prd/${prdId}/versions`, {
      params: { workspace_path: workspacePath },
    });
    return response.data;
  },

  createVersion: async (
    prdId: string,
    workspacePath: string,
    content: string,
    changeSummary: string
  ): Promise<PrdResponse> => {
    const response = await api.post<PrdResponse>(
      `/api/v2/prd/${prdId}/versions`,
      { content, change_summary: changeSummary },
      { params: { workspace_path: workspacePath } }
    );
    return response.data;
  },

  diff: async (
    prdId: string,
    workspacePath: string,
    version1?: number,
    version2?: number
  ): Promise<PrdDiffResponse> => {
    const response = await api.get<PrdDiffResponse>(`/api/v2/prd/${prdId}/diff`, {
      params: {
        workspace_path: workspacePath,
        ...(version1 !== undefined ? { version1 } : {}),
        ...(version2 !== undefined ? { version2 } : {}),
      },
    });
    return response.data;
  },
};

// Discovery API methods
export const discoveryApi = {
  start: async (workspacePath: string): Promise<StartDiscoveryResponse> => {
    const response = await api.post<StartDiscoveryResponse>(
      '/api/v2/discovery/start',
      {},
      { params: { workspace_path: workspacePath } }
    );
    return response.data;
  },

  getStatus: async (workspacePath: string): Promise<DiscoveryStatusResponse> => {
    const response = await api.get<DiscoveryStatusResponse>('/api/v2/discovery/status', {
      params: { workspace_path: workspacePath },
    });
    return response.data;
  },

  submitAnswer: async (
    sessionId: string,
    answer: string,
    workspacePath: string
  ): Promise<AnswerResponse> => {
    const response = await api.post<AnswerResponse>(
      `/api/v2/discovery/${sessionId}/answer`,
      { answer },
      { params: { workspace_path: workspacePath } }
    );
    return response.data;
  },

  generatePrd: async (
    sessionId: string,
    workspacePath: string,
    templateId?: string
  ): Promise<GeneratePrdResponse> => {
    const response = await api.post<GeneratePrdResponse>(
      `/api/v2/discovery/${sessionId}/generate-prd`,
      { ...(templateId ? { template_id: templateId } : {}) },
      { params: { workspace_path: workspacePath } }
    );
    return response.data;
  },

  reset: async (workspacePath: string): Promise<void> => {
    await api.post('/api/v2/discovery/reset', {}, {
      params: { workspace_path: workspacePath },
    });
  },

  generateTasks: async (workspacePath: string): Promise<GenerateTasksResponse> => {
    const response = await api.post<GenerateTasksResponse>(
      '/api/v2/discovery/generate-tasks',
      {},
      { params: { workspace_path: workspacePath } }
    );
    return response.data;
  },
};

export default api;
