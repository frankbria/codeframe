/**
 * Contract tests for the `src/lib/api.ts` request layer (issue #774).
 *
 * Every other test in the suite MOCKS this module, so drift in the actual HTTP
 * request — wrong method, wrong URL, a renamed query param, a reshaped body —
 * passes green everywhere else. These tests pin method + URL + params + body for
 * the critical endpoints so that drift fails here instead of in production.
 *
 * Approach (the "axios-stub" option from the issue's acceptance criteria): swap
 * the shared client's adapter for a capturing stub. The adapter runs *after*
 * axios has applied the request interceptor (auth header), URL building, and
 * body serialization, so `config` holds exactly what would go on the wire. No
 * network, no msw/jsdom polyfills.
 */
import type { AxiosAdapter, InternalAxiosRequestConfig } from 'axios';

import api, {
  workspaceApi,
  tasksApi,
  eventsApi,
} from '@/lib/api';
import { setToken } from '@/lib/auth';

// jsdom 30's window.location is non-configurable; the 401 interceptor imports
// this seam, so stub it to keep unrelated redirects from firing.
jest.mock('@/lib/navigation', () => ({
  currentPathname: jest.fn(() => '/tasks'),
  redirectTo: jest.fn(),
}));

interface CapturedRequest {
  method?: string;
  url?: string;
  params?: Record<string, unknown>;
  body: unknown;
  authorization?: unknown;
}

let captured: CapturedRequest;
let stubResponseData: unknown = {};

const originalAdapter = api.defaults.adapter;

const capturingAdapter: AxiosAdapter = async (config: InternalAxiosRequestConfig) => {
  captured = {
    method: config.method,
    url: config.url,
    params: config.params,
    // Axios has already serialized objects to a JSON string by the time the
    // adapter runs; undefined for GET/DELETE with no body.
    body: config.data ? JSON.parse(config.data as string) : undefined,
    authorization: config.headers?.get?.('Authorization'),
  };
  return {
    data: stubResponseData,
    status: 200,
    statusText: 'OK',
    headers: {},
    config,
  };
};

beforeEach(() => {
  localStorage.clear();
  captured = { body: undefined };
  stubResponseData = {};
  api.defaults.adapter = capturingAdapter;
});

afterEach(() => {
  api.defaults.adapter = originalAdapter;
});

describe('api.ts request contract', () => {
  describe('workspaceApi', () => {
    it('checkExists → GET /api/v2/workspaces/exists?repo_path=', async () => {
      await workspaceApi.checkExists('/repo/path');
      expect(captured.method).toBe('get');
      expect(captured.url).toBe('/api/v2/workspaces/exists');
      expect(captured.params).toEqual({ repo_path: '/repo/path' });
      expect(captured.body).toBeUndefined();
    });

    it('init → POST /api/v2/workspaces with {repo_path, tech_stack, detect}', async () => {
      await workspaceApi.init('/repo/path', { techStack: 'python', detect: false });
      expect(captured.method).toBe('post');
      expect(captured.url).toBe('/api/v2/workspaces');
      expect(captured.body).toEqual({
        repo_path: '/repo/path',
        tech_stack: 'python',
        detect: false,
      });
    });

    it('init defaults detect to true when not supplied', async () => {
      await workspaceApi.init('/repo/path');
      expect(captured.body).toEqual({
        repo_path: '/repo/path',
        tech_stack: undefined,
        detect: true,
      });
    });

    it('list → GET /api/v2/workspaces and unwraps .workspaces', async () => {
      stubResponseData = { workspaces: [{ id: 'w1' }] };
      const result = await workspaceApi.list();
      expect(captured.method).toBe('get');
      expect(captured.url).toBe('/api/v2/workspaces');
      expect(result).toEqual([{ id: 'w1' }]);
    });

    it('remove → DELETE /api/v2/workspaces/:id', async () => {
      await workspaceApi.remove('w1');
      expect(captured.method).toBe('delete');
      expect(captured.url).toBe('/api/v2/workspaces/w1');
    });
  });

  describe('tasksApi', () => {
    it('getAll → GET /api/v2/tasks with workspace_path (status omitted when absent)', async () => {
      await tasksApi.getAll('/ws');
      expect(captured.method).toBe('get');
      expect(captured.url).toBe('/api/v2/tasks');
      expect(captured.params).toEqual({ workspace_path: '/ws' });
    });

    it('getAll includes status when provided', async () => {
      await tasksApi.getAll('/ws', 'READY');
      expect(captured.params).toEqual({ workspace_path: '/ws', status: 'READY' });
    });

    it('getOne → GET /api/v2/tasks/:id?workspace_path=', async () => {
      await tasksApi.getOne('/ws', 'task-1');
      expect(captured.method).toBe('get');
      expect(captured.url).toBe('/api/v2/tasks/task-1');
      expect(captured.params).toEqual({ workspace_path: '/ws' });
    });

    it('updateStatus → PATCH /api/v2/tasks/:id with {status} body + workspace_path param', async () => {
      await tasksApi.updateStatus('/ws', 'task-1', 'READY');
      expect(captured.method).toBe('patch');
      expect(captured.url).toBe('/api/v2/tasks/task-1');
      expect(captured.body).toEqual({ status: 'READY' });
      expect(captured.params).toEqual({ workspace_path: '/ws' });
    });

    it('updateGitHubSettings → PATCH /api/v2/tasks/:id with {auto_close_github_issue}', async () => {
      await tasksApi.updateGitHubSettings('/ws', 'task-1', true);
      expect(captured.method).toBe('patch');
      expect(captured.url).toBe('/api/v2/tasks/task-1');
      expect(captured.body).toEqual({ auto_close_github_issue: true });
      expect(captured.params).toEqual({ workspace_path: '/ws' });
    });

    it('startExecution → POST /api/v2/tasks/:id/start with execute=true param', async () => {
      await tasksApi.startExecution('/ws', 'task-1');
      expect(captured.method).toBe('post');
      expect(captured.url).toBe('/api/v2/tasks/task-1/start');
      expect(captured.params).toEqual({ workspace_path: '/ws', execute: true });
      expect(captured.body).toEqual({});
    });

    it('executeBatch → POST /api/v2/tasks/execute forwarding the request body', async () => {
      const request = { task_ids: ['a', 'b'], strategy: 'serial' as const };
      await tasksApi.executeBatch('/ws', request);
      expect(captured.method).toBe('post');
      expect(captured.url).toBe('/api/v2/tasks/execute');
      expect(captured.body).toEqual(request);
      expect(captured.params).toEqual({ workspace_path: '/ws' });
    });

    it('stopExecution URL-encodes the task id', async () => {
      await tasksApi.stopExecution('/ws', 'task/with space');
      expect(captured.method).toBe('post');
      expect(captured.url).toBe(`/api/v2/tasks/${encodeURIComponent('task/with space')}/stop`);
    });
  });

  describe('eventsApi', () => {
    it('getRecent → GET /api/v2/events with default limit 20', async () => {
      await eventsApi.getRecent('/ws');
      expect(captured.method).toBe('get');
      expect(captured.url).toBe('/api/v2/events');
      expect(captured.params).toEqual({ workspace_path: '/ws', limit: 20 });
    });

    it('getRecent forwards limit and since_id', async () => {
      await eventsApi.getRecent('/ws', { limit: 5, sinceId: 42 });
      expect(captured.params).toEqual({ workspace_path: '/ws', limit: 5, since_id: 42 });
    });
  });

  describe('auth wiring (request interceptor)', () => {
    it('attaches Bearer token to real requests when a token is stored', async () => {
      setToken('jwt-abc');
      await tasksApi.getAll('/ws');
      expect(captured.authorization).toBe('Bearer jwt-abc');
    });

    it('omits Authorization when no token is stored', async () => {
      await tasksApi.getAll('/ws');
      expect(captured.authorization).toBeFalsy();
    });
  });
});
