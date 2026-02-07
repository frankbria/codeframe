/**
 * Shared Playwright fixtures for CodeFRAME E2E tests.
 *
 * Provides:
 * - `mockApi`: Intercepts all /api/v2/* routes with mock data
 * - `withWorkspace`: Sets localStorage workspace path before navigation
 *
 * Usage in test files:
 *   import { test, expect } from '../fixtures/test-setup';
 */
import { test as base, expect, Page, Route } from '@playwright/test';
import {
  TEST_WORKSPACE_PATH,
  mockWorkspace,
  mockTaskListResponse,
  mockPrd,
  mockPrdList,
  mockEvents,
  mockBlockerListResponse,
  mockDiscoverySession,
  mockSSEEvents,
} from './mock-data';

type ApiOverrides = {
  [pattern: string]: (route: Route) => Promise<void> | void;
};

type TestFixtures = {
  /** Sets up API mocking for all standard endpoints. Call with overrides to customize. */
  mockApi: (overrides?: ApiOverrides) => Promise<void>;
  /** Sets workspace in localStorage and navigates to a path */
  withWorkspace: (path?: string) => Promise<void>;
};

export const test = base.extend<TestFixtures>({
  mockApi: async ({ page }, use) => {
    const setup = async (overrides: ApiOverrides = {}) => {
      // Workspace endpoints
      await page.route('**/api/v2/workspaces/exists*', async (route) => {
        if (overrides['workspaces/exists']) return overrides['workspaces/exists'](route);
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ exists: true, path: TEST_WORKSPACE_PATH, state_dir: `${TEST_WORKSPACE_PATH}/.codeframe` }),
        });
      });

      await page.route('**/api/v2/workspaces/current*', async (route) => {
        if (overrides['workspaces/current']) return overrides['workspaces/current'](route);
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(mockWorkspace),
        });
      });

      await page.route('**/api/v2/workspaces', async (route) => {
        if (route.request().method() === 'POST') {
          if (overrides['workspaces/init']) return overrides['workspaces/init'](route);
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify(mockWorkspace),
          });
        } else {
          await route.continue();
        }
      });

      // Task endpoints
      await page.route('**/api/v2/tasks?*', async (route) => {
        if (overrides['tasks/list']) return overrides['tasks/list'](route);
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(mockTaskListResponse),
        });
      });

      await page.route('**/api/v2/tasks/*/start*', async (route) => {
        if (overrides['tasks/start']) return overrides['tasks/start'](route);
        const url = route.request().url();
        const taskIdMatch = url.match(/\/tasks\/([^/]+)\/start/);
        const taskId = taskIdMatch?.[1] ?? 'task-001';
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            success: true,
            run_id: 'run-001',
            task_id: taskId,
            status: 'IN_PROGRESS',
            message: 'Task execution started',
          }),
        });
      });

      await page.route('**/api/v2/tasks/*/stop*', async (route) => {
        if (overrides['tasks/stop']) return overrides['tasks/stop'](route);
        await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
      });

      await page.route('**/api/v2/tasks/*/stream*', async (route) => {
        if (overrides['tasks/stream']) return overrides['tasks/stream'](route);
        // Build SSE response body
        const body = mockSSEEvents
          .map((e) => `event: ${e.event}\ndata: ${JSON.stringify(e.data)}\n\n`)
          .join('');
        await route.fulfill({
          status: 200,
          contentType: 'text/event-stream',
          body,
        });
      });

      await page.route(/\/api\/v2\/tasks\/[^/]+$/, async (route) => {
        const method = route.request().method();
        if (method === 'PATCH') {
          if (overrides['tasks/update']) return overrides['tasks/update'](route);
          const body = route.request().postDataJSON();
          const url = route.request().url();
          const taskIdMatch = url.match(/\/tasks\/([^/?]+)$/);
          const taskId = taskIdMatch?.[1] ?? 'task-001';
          const task = mockTaskListResponse.tasks.find((t) => t.id === taskId) ?? mockTaskListResponse.tasks[0];
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({ ...task, ...body }),
          });
        } else if (method === 'GET') {
          if (overrides['tasks/get']) return overrides['tasks/get'](route);
          const url = route.request().url();
          const taskIdMatch = url.match(/\/tasks\/([^/?]+)/);
          const taskId = taskIdMatch?.[1] ?? 'task-001';
          const task = mockTaskListResponse.tasks.find((t) => t.id === taskId) ?? mockTaskListResponse.tasks[0];
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify(task),
          });
        } else {
          await route.continue();
        }
      });

      // Batch execution
      await page.route('**/api/v2/tasks/execute*', async (route) => {
        if (overrides['tasks/execute']) return overrides['tasks/execute'](route);
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            success: true,
            batch_id: 'batch-001',
            task_count: 2,
            strategy: 'serial',
            message: 'Batch execution started',
          }),
        });
      });

      // PRD endpoints
      await page.route('**/api/v2/prd/latest*', async (route) => {
        if (overrides['prd/latest']) return overrides['prd/latest'](route);
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(mockPrd),
        });
      });

      await page.route('**/api/v2/prd?*', async (route) => {
        const method = route.request().method();
        if (method === 'POST') {
          if (overrides['prd/create']) return overrides['prd/create'](route);
          const body = route.request().postDataJSON();
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({ ...mockPrd, ...body }),
          });
        } else {
          if (overrides['prd/list']) return overrides['prd/list'](route);
          await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify(mockPrdList),
          });
        }
      });

      await page.route('**/api/v2/prd/*/versions*', async (route) => {
        if (overrides['prd/versions']) return overrides['prd/versions'](route);
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([mockPrd]),
        });
      });

      // Discovery endpoints
      await page.route('**/api/v2/discovery/start*', async (route) => {
        if (overrides['discovery/start']) return overrides['discovery/start'](route);
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(mockDiscoverySession),
        });
      });

      await page.route('**/api/v2/discovery/status*', async (route) => {
        if (overrides['discovery/status']) return overrides['discovery/status'](route);
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(mockDiscoverySession),
        });
      });

      await page.route('**/api/v2/discovery/*/answer*', async (route) => {
        if (overrides['discovery/answer']) return overrides['discovery/answer'](route);
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            ...mockDiscoverySession,
            questions_asked: 2,
            question: 'Who are the target users?',
          }),
        });
      });

      await page.route('**/api/v2/discovery/*/generate-prd*', async (route) => {
        if (overrides['discovery/generate-prd']) return overrides['discovery/generate-prd'](route);
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ prd_id: mockPrd.id, content: mockPrd.content }),
        });
      });

      await page.route('**/api/v2/discovery/generate-tasks*', async (route) => {
        if (overrides['discovery/generate-tasks']) return overrides['discovery/generate-tasks'](route);
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ tasks_generated: 3, task_ids: ['task-001', 'task-002', 'task-003'] }),
        });
      });

      // Blockers
      await page.route('**/api/v2/blockers?*', async (route) => {
        if (overrides['blockers/list']) return overrides['blockers/list'](route);
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(mockBlockerListResponse),
        });
      });

      await page.route('**/api/v2/blockers/*/answer*', async (route) => {
        if (overrides['blockers/answer']) return overrides['blockers/answer'](route);
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            ...mockBlockerListResponse.blockers[0],
            answer: 'Use Google OAuth',
            status: 'ANSWERED',
            answered_at: '2026-02-03T12:00:00Z',
          }),
        });
      });

      // Events
      await page.route('**/api/v2/events*', async (route) => {
        if (overrides['events']) return overrides['events'](route);
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(mockEvents),
        });
      });

      // Batches
      await page.route('**/api/v2/batches/*', async (route) => {
        if (overrides['batches/get']) return overrides['batches/get'](route);
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            id: 'batch-001',
            workspace_id: 'ws-e2e-001',
            task_ids: ['task-001', 'task-003'],
            status: 'completed',
            strategy: 'serial',
            max_parallel: 1,
            on_failure: 'stop',
            started_at: '2026-02-03T00:00:00Z',
            completed_at: '2026-02-03T00:05:00Z',
            results: { 'task-001': 'completed', 'task-003': 'completed' },
          }),
        });
      });
    };

    await use(setup);
  },

  withWorkspace: async ({ page }, use) => {
    const setup = async (path: string = TEST_WORKSPACE_PATH) => {
      // Set workspace in localStorage before navigating
      await page.addInitScript((workspacePath) => {
        localStorage.setItem('codeframe_workspace_path', workspacePath);
      }, path);
    };
    await use(setup);
  },
});

export { expect };
