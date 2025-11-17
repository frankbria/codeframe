export interface LintResult {
  id: number;
  task_id: number;
  linter: 'ruff' | 'eslint' | 'other';
  error_count: number;
  warning_count: number;
  files_linted: number;
  output: string;
  created_at: string;
}

export interface LintTrendEntry {
  date: string;
  linter: string;
  error_count: number;
  warning_count: number;
}

export interface LintConfig {
  project_id: number;
  config: Record<string, any>;
  has_ruff_config: boolean;
  has_eslint_config: boolean;
}
