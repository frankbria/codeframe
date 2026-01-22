// T122: Lint API client
import { authFetch } from '@/lib/api-client';
import type { LintResult, LintTrendEntry, LintConfig } from '@/types/lint';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8080';

export const lintApi = {
  // Get lint results for task
  getResults: async (taskId: number): Promise<{ task_id: number; results: LintResult[] }> => {
    return authFetch<{ task_id: number; results: LintResult[] }>(
      `${API_BASE}/api/lint/results?task_id=${taskId}`
    );
  },

  // Get lint trend
  getTrend: async (projectId: number, days: number = 7): Promise<{
    project_id: number;
    days: number;
    trend: LintTrendEntry[];
  }> => {
    return authFetch<{
      project_id: number;
      days: number;
      trend: LintTrendEntry[];
    }>(`${API_BASE}/api/lint/trend?project_id=${projectId}&days=${days}`);
  },

  // Get lint config
  getConfig: async (projectId: number): Promise<LintConfig> => {
    return authFetch<LintConfig>(
      `${API_BASE}/api/lint/config?project_id=${projectId}`
    );
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
    return authFetch<{
      status: string;
      has_errors: boolean;
      results: Array<{
        linter: string;
        error_count: number;
        warning_count: number;
        files_linted: number;
      }>;
    }>(`${API_BASE}/api/lint/run`, {
      method: 'POST',
      body: {
        project_id: projectId,
        task_id: taskId,
        files
      }
    });
  }
};
