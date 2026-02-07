/**
 * Shared mock data for E2E tests.
 * Mirrors the TypeScript types in src/types/index.ts.
 */

export const TEST_WORKSPACE_PATH = '/tmp/codeframe-e2e-workspace';

export const mockWorkspace = {
  id: 'ws-e2e-001',
  repo_path: TEST_WORKSPACE_PATH,
  state_dir: `${TEST_WORKSPACE_PATH}/.codeframe`,
  tech_stack: 'TypeScript with Next.js, jest',
  created_at: '2026-02-01T00:00:00Z',
};

export const mockTasks = [
  {
    id: 'task-001',
    title: 'Set up authentication',
    description: 'Implement JWT auth with refresh tokens',
    status: 'READY',
    priority: 1,
    depends_on: [],
    estimated_hours: 4,
    created_at: '2026-02-01T00:00:00Z',
    updated_at: '2026-02-01T00:00:00Z',
  },
  {
    id: 'task-002',
    title: 'Create user dashboard',
    description: 'Build the main user dashboard with stats',
    status: 'IN_PROGRESS',
    priority: 2,
    depends_on: ['task-001'],
    estimated_hours: 6,
    created_at: '2026-02-01T00:00:00Z',
    updated_at: '2026-02-02T00:00:00Z',
  },
  {
    id: 'task-003',
    title: 'Write API tests',
    description: 'Integration tests for all REST endpoints',
    status: 'BACKLOG',
    priority: 3,
    depends_on: [],
    estimated_hours: 3,
    created_at: '2026-02-01T00:00:00Z',
    updated_at: '2026-02-01T00:00:00Z',
  },
  {
    id: 'task-004',
    title: 'Deploy to staging',
    description: 'Configure CI/CD pipeline for staging environment',
    status: 'DONE',
    priority: 4,
    depends_on: ['task-001'],
    estimated_hours: 2,
    created_at: '2026-02-01T00:00:00Z',
    updated_at: '2026-02-03T00:00:00Z',
  },
  {
    id: 'task-005',
    title: 'Fix login redirect bug',
    description: 'Users are not redirected after login',
    status: 'BLOCKED',
    priority: 1,
    depends_on: ['task-001'],
    estimated_hours: 1,
    created_at: '2026-02-02T00:00:00Z',
    updated_at: '2026-02-03T00:00:00Z',
  },
  {
    id: 'task-006',
    title: 'Database migration script',
    description: 'Migrate users table to new schema',
    status: 'FAILED',
    priority: 2,
    depends_on: [],
    estimated_hours: 2,
    created_at: '2026-02-02T00:00:00Z',
    updated_at: '2026-02-03T00:00:00Z',
  },
];

export const mockTaskListResponse = {
  tasks: mockTasks,
  total: mockTasks.length,
  by_status: {
    BACKLOG: 1,
    READY: 1,
    IN_PROGRESS: 1,
    DONE: 1,
    BLOCKED: 1,
    FAILED: 1,
    MERGED: 0,
  },
};

export const mockPrd = {
  id: 'prd-001',
  workspace_id: 'ws-e2e-001',
  title: 'E2E Test Project PRD',
  content: '# Project Overview\n\nThis is a test PRD for E2E testing.\n\n## Goals\n\n- Goal 1\n- Goal 2\n\n## Requirements\n\n### Functional\n\n1. User authentication\n2. Dashboard\n3. API endpoints',
  version: 1,
  created_at: '2026-02-01T00:00:00Z',
  updated_at: '2026-02-01T00:00:00Z',
};

export const mockPrdList = {
  prds: [mockPrd],
  total: 1,
};

export const mockDiscoverySession = {
  session_id: 'disc-001',
  status: 'in_progress',
  question: 'What is the main purpose of your application?',
  questions_asked: 1,
  total_expected: 5,
};

export const mockBlockers = [
  {
    id: 'blocker-001',
    workspace_id: 'ws-e2e-001',
    task_id: 'task-005',
    question: 'What OAuth provider should be used for authentication?',
    answer: null,
    status: 'OPEN',
    created_at: '2026-02-02T00:00:00Z',
    answered_at: null,
  },
];

export const mockBlockerListResponse = {
  blockers: mockBlockers,
  total: mockBlockers.length,
  by_status: { OPEN: 1, ANSWERED: 0, RESOLVED: 0 },
};

export const mockBatchResponse = {
  id: 'batch-001',
  workspace_id: 'ws-e2e-001',
  task_ids: ['task-001', 'task-003'],
  status: 'running',
  strategy: 'serial',
  max_parallel: 1,
  on_failure: 'stop',
  started_at: '2026-02-03T00:00:00Z',
  completed_at: null,
  results: {},
};

export const mockEvents = {
  events: [
    {
      id: 1,
      workspace_id: 'ws-e2e-001',
      event_type: 'task_completed',
      payload: { task_id: 'task-004', title: 'Deploy to staging' },
      created_at: '2026-02-03T00:00:00Z',
    },
    {
      id: 2,
      workspace_id: 'ws-e2e-001',
      event_type: 'run_started',
      payload: { task_id: 'task-002', title: 'Create user dashboard' },
      created_at: '2026-02-03T01:00:00Z',
    },
  ],
  total: 2,
};

/** SSE event payloads for execution stream mock */
export const mockSSEEvents = [
  { event: 'progress', data: { phase: 'planning', step: 1, total_steps: 3, message: 'Analyzing task context...' } },
  { event: 'progress', data: { phase: 'planning', step: 2, total_steps: 3, message: 'Generating implementation plan...' } },
  { event: 'progress', data: { phase: 'planning', step: 3, total_steps: 3, message: 'Plan complete' } },
  { event: 'progress', data: { phase: 'execution', step: 1, total_steps: 2, message: 'Creating auth module...' } },
  { event: 'output', data: { stream: 'stdout', line: 'Created file: src/auth.ts' } },
  { event: 'file_change', data: { path: 'src/auth.ts', action: 'created', lines_added: 45 } },
  { event: 'progress', data: { phase: 'execution', step: 2, total_steps: 2, message: 'Running shell commands...' } },
  { event: 'shell_command', data: { command: 'npm test', exit_code: 0, stdout: 'All tests passed' } },
  { event: 'progress', data: { phase: 'verification', step: 1, total_steps: 2, message: 'Running ruff...' } },
  { event: 'verification', data: { gate: 'ruff', passed: true, message: 'No issues found' } },
  { event: 'progress', data: { phase: 'verification', step: 2, total_steps: 2, message: 'Running pytest...' } },
  { event: 'verification', data: { gate: 'pytest', passed: true, message: '12 passed' } },
  { event: 'completion', data: { status: 'completed', duration: 45.2, files_modified: ['src/auth.ts'] } },
];
