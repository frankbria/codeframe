// T122: Lint API client
import axios from 'axios';
import type { LintResult, LintTrendEntry, LintConfig } from '@/types/lint';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8080';

export const lintApi = {
  // Get lint results for task
  getResults: async (taskId: number): Promise<{ task_id: number; results: LintResult[] }> => {
    const response = await axios.get(`${API_BASE}/api/lint/results`, {
      params: { task_id: taskId }
    });
    return response.data;
  },

  // Get lint trend
  getTrend: async (projectId: number, days: number = 7): Promise<{
    project_id: number;
    days: number;
    trend: LintTrendEntry[];
  }> => {
    const response = await axios.get(`${API_BASE}/api/lint/trend`, {
      params: { project_id: projectId, days }
    });
    return response.data;
  },

  // Get lint config
  getConfig: async (projectId: number): Promise<LintConfig> => {
    const response = await axios.get(`${API_BASE}/api/lint/config`, {
      params: { project_id: projectId }
    });
    return response.data;
  },

  // Run manual lint
  runLint: async (projectId: number, taskId?: number, files?: string[]): Promise<{
    status: string;
    has_errors: boolean;
    results: Array<{
      linter: string;
      error_count: number;
      warning_count: number;
      files_linted: number;
    }>;
  }> => {
    const response = await axios.post(`${API_BASE}/api/lint/run`, {
      project_id: projectId,
      task_id: taskId,
      files
    });
    return response.data;
  }
};
