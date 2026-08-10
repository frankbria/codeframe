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
import { readFileSync } from 'fs';

import type { AxiosAdapter, InternalAxiosRequestConfig } from 'axios';

import api, {
  workspaceApi,
  tasksApi,
  eventsApi,
  blockersApi,
  batchesApi,
  prdApi,
  discoveryApi,
  reviewApi,
  gatesApi,
  gitApi,
  proofApi,
  prApi,
  sessionsApi,
  settingsApi,
  proofConfigApi,
  workspaceConfigApi,
  notificationsApi,
  integrationsApi,
  costsApi,
} from '@/lib/api';
import * as apiModule from '@/lib/api';
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

  describe('blockersApi', () => {
    it('getAll → GET /api/v2/blockers with workspace_path only', async () => {
      await blockersApi.getAll('/ws');
      expect(captured.method).toBe('get');
      expect(captured.url).toBe('/api/v2/blockers');
      expect(captured.params).toEqual({ workspace_path: '/ws' });
    });

    it('getAll omits status/limit when not supplied, forwards when they are', async () => {
      await blockersApi.getAll('/ws', { status: 'OPEN' as never, limit: 5 });
      expect(captured.params).toEqual({ workspace_path: '/ws', status: 'OPEN', limit: 5 });
    });

    it('getForTask → GET /api/v2/blockers?task_id=', async () => {
      await blockersApi.getForTask('/ws', 't-1');
      expect(captured.url).toBe('/api/v2/blockers');
      expect(captured.params).toEqual({ workspace_path: '/ws', task_id: 't-1' });
    });

    it('answer → POST /api/v2/blockers/:id/answer with {answer}', async () => {
      await blockersApi.answer('/ws', 'b 1', 'because');
      expect(captured.method).toBe('post');
      expect(captured.url).toBe('/api/v2/blockers/b%201/answer');
      expect(captured.body).toEqual({ answer: 'because' });
      expect(captured.params).toEqual({ workspace_path: '/ws' });
    });

    it('resolve → POST /api/v2/blockers/:id/resolve', async () => {
      await blockersApi.resolve('/ws', 'b-1');
      expect(captured.method).toBe('post');
      expect(captured.url).toBe('/api/v2/blockers/b-1/resolve');
      expect(captured.body).toEqual({});
    });
  });

  describe('batchesApi', () => {
    it('list → GET /api/v2/batches', async () => {
      await batchesApi.list('/ws');
      expect(captured.method).toBe('get');
      expect(captured.url).toBe('/api/v2/batches');
      expect(captured.params).toEqual({ workspace_path: '/ws' });
    });

    it('list forwards status and limit when supplied', async () => {
      await batchesApi.list('/ws', { status: 'RUNNING', limit: 3 });
      expect(captured.params).toEqual({ workspace_path: '/ws', status: 'RUNNING', limit: 3 });
    });

    it('get → GET /api/v2/batches/:id, id encoded', async () => {
      await batchesApi.get('/ws', 'b/1');
      expect(captured.url).toBe('/api/v2/batches/b%2F1');
    });

    it('stop → POST /api/v2/batches/:id/stop', async () => {
      await batchesApi.stop('/ws', 'b-1');
      expect(captured.method).toBe('post');
      expect(captured.url).toBe('/api/v2/batches/b-1/stop');
      expect(captured.body).toEqual({});
    });

    it('cancel → POST /api/v2/batches/:id/cancel', async () => {
      await batchesApi.cancel('/ws', 'b-1');
      expect(captured.url).toBe('/api/v2/batches/b-1/cancel');
    });
  });

  describe('prdApi', () => {
    it('getAll → GET /api/v2/prd', async () => {
      await prdApi.getAll('/ws');
      expect(captured.method).toBe('get');
      expect(captured.url).toBe('/api/v2/prd');
      expect(captured.params).toEqual({ workspace_path: '/ws' });
    });

    it('getLatest → GET /api/v2/prd/latest', async () => {
      await prdApi.getLatest('/ws');
      expect(captured.url).toBe('/api/v2/prd/latest');
    });

    it('getById → GET /api/v2/prd/:id', async () => {
      await prdApi.getById('p-1', '/ws');
      expect(captured.url).toBe('/api/v2/prd/p-1');
    });

    it('create → POST /api/v2/prd with {content} and optional title/metadata', async () => {
      await prdApi.create('/ws', '# doc');
      expect(captured.method).toBe('post');
      expect(captured.url).toBe('/api/v2/prd');
      expect(captured.body).toEqual({ content: '# doc' });

      await prdApi.create('/ws', '# doc', 'T', { a: 1 });
      expect(captured.body).toEqual({ content: '# doc', title: 'T', metadata: { a: 1 } });
    });

    it('delete → DELETE /api/v2/prd/:id', async () => {
      await prdApi.delete('p-1', '/ws');
      expect(captured.method).toBe('delete');
      expect(captured.url).toBe('/api/v2/prd/p-1');
    });

    it('getVersions → GET /api/v2/prd/:id/versions', async () => {
      await prdApi.getVersions('p-1', '/ws');
      expect(captured.method).toBe('get');
      expect(captured.url).toBe('/api/v2/prd/p-1/versions');
      expect(captured.params).toEqual({ workspace_path: '/ws' });
      expect(captured.body).toBeUndefined();
    });

    it('createVersion → POST with snake_case change_summary', async () => {
      await prdApi.createVersion('p-1', '/ws', '# v2', 'why');
      expect(captured.method).toBe('post');
      expect(captured.url).toBe('/api/v2/prd/p-1/versions');
      expect(captured.body).toEqual({ content: '# v2', change_summary: 'why' });
    });

    it('diff omits version params unless given', async () => {
      await prdApi.diff('p-1', '/ws');
      expect(captured.params).toEqual({ workspace_path: '/ws' });

      await prdApi.diff('p-1', '/ws', 1, 2);
      expect(captured.params).toEqual({ workspace_path: '/ws', version1: 1, version2: 2 });
    });

    it('diff forwards version 0, which a truthy check would drop', async () => {
      await prdApi.diff('p-1', '/ws', 0, 2);
      expect(captured.params).toEqual({ workspace_path: '/ws', version1: 0, version2: 2 });
    });

    it('refineStressTest → POST /api/v2/prd/stress-test/refine with {prd_id, answers}', async () => {
      const answers = [{ label: 'L', questions: ['q?'], answer: 'a' }];
      await prdApi.refineStressTest('p-1', '/ws', answers);
      expect(captured.url).toBe('/api/v2/prd/stress-test/refine');
      expect(captured.body).toEqual({ prd_id: 'p-1', answers });
    });
  });

  describe('discoveryApi', () => {
    it('start → POST /api/v2/discovery/start', async () => {
      await discoveryApi.start('/ws');
      expect(captured.method).toBe('post');
      expect(captured.url).toBe('/api/v2/discovery/start');
      expect(captured.body).toEqual({});
      expect(captured.params).toEqual({ workspace_path: '/ws' });
    });

    it('getStatus → GET /api/v2/discovery/status', async () => {
      await discoveryApi.getStatus('/ws');
      expect(captured.method).toBe('get');
      expect(captured.url).toBe('/api/v2/discovery/status');
    });

    it('submitAnswer → POST /api/v2/discovery/:sessionId/answer with {answer}', async () => {
      await discoveryApi.submitAnswer('s-1', 'my answer', '/ws');
      expect(captured.url).toBe('/api/v2/discovery/s-1/answer');
      expect(captured.body).toEqual({ answer: 'my answer' });
    });

    it('generatePrd → POST /api/v2/discovery/:sessionId/generate-prd', async () => {
      await discoveryApi.generatePrd('s-1', '/ws');
      expect(captured.url).toBe('/api/v2/discovery/s-1/generate-prd');
      expect(captured.body).toEqual({});

      await discoveryApi.generatePrd('s-1', '/ws', 'lean');
      expect(captured.body).toEqual({ template_id: 'lean' });
    });

    it('reset → POST /api/v2/discovery/reset', async () => {
      await discoveryApi.reset('/ws');
      expect(captured.url).toBe('/api/v2/discovery/reset');
    });

    it('generateTasks → POST /api/v2/discovery/generate-tasks', async () => {
      await discoveryApi.generateTasks('/ws');
      expect(captured.url).toBe('/api/v2/discovery/generate-tasks');
    });
  });

  describe('reviewApi', () => {
    it('getDiff → GET /api/v2/review/diff, staged omitted unless true', async () => {
      await reviewApi.getDiff('/ws');
      expect(captured.method).toBe('get');
      expect(captured.url).toBe('/api/v2/review/diff');
      expect(captured.params).toEqual({ workspace_path: '/ws' });

      await reviewApi.getDiff('/ws', true);
      expect(captured.params).toEqual({ workspace_path: '/ws', staged: true });
    });

    it('getPatch → GET /api/v2/review/patch as bytes', async () => {
      // The endpoint returns application/octet-stream since #1077 — a patch is
      // a file fed back to `git apply`, and JSON cannot carry a non-UTF-8 byte.
      stubResponseData = new Uint8Array([0x2b, 0x63, 0x61, 0x66, 0xe9]).buffer;

      const result = await reviewApi.getPatch('/ws');

      expect(captured.url).toBe('/api/v2/review/patch');
      expect(result.bytes).toBe(stubResponseData);
      // The display string is decoded from those bytes; the invalid byte
      // becomes U+FFFD here, which is fine for a textarea and never downloaded.
      expect(result.patch.startsWith('+caf')).toBe(true);
    });

    it('getPatch falls back to a default filename without Content-Disposition', async () => {
      stubResponseData = new Uint8Array([0x61]).buffer;
      const result = await reviewApi.getPatch('/ws');
      expect(result.filename).toBe('changes.patch');
    });

    it('generateCommitMessage → POST /api/v2/review/commit-message', async () => {
      await reviewApi.generateCommitMessage('/ws');
      expect(captured.method).toBe('post');
      expect(captured.url).toBe('/api/v2/review/commit-message');
      expect(captured.body).toEqual({});
    });
  });

  describe('gatesApi', () => {
    it('run → POST /api/v2/gates/run, defaulting gates to null and verbose to false', async () => {
      await gatesApi.run('/ws');
      expect(captured.method).toBe('post');
      expect(captured.url).toBe('/api/v2/gates/run');
      expect(captured.body).toEqual({ gates: null, verbose: false });
      expect(captured.params).toEqual({ workspace_path: '/ws' });
    });

    it('run forwards an explicit gate list', async () => {
      await gatesApi.run('/ws', { gates: ['lint'], verbose: true });
      expect(captured.body).toEqual({ gates: ['lint'], verbose: true });
    });
  });

  describe('gitApi', () => {
    it('getStatus → GET /api/v2/git/status', async () => {
      await gitApi.getStatus('/ws');
      expect(captured.method).toBe('get');
      expect(captured.url).toBe('/api/v2/git/status');
    });

    it('commit → POST /api/v2/git/commit with {files, message}', async () => {
      await gitApi.commit('/ws', ['a.ts', 'b.ts'], 'msg');
      expect(captured.method).toBe('post');
      expect(captured.url).toBe('/api/v2/git/commit');
      expect(captured.body).toEqual({ files: ['a.ts', 'b.ts'], message: 'msg' });
      expect(captured.params).toEqual({ workspace_path: '/ws' });
    });
  });

  describe('proofApi', () => {
    it('getStatus → GET /api/v2/proof/status', async () => {
      await proofApi.getStatus('/ws');
      expect(captured.url).toBe('/api/v2/proof/status');
    });

    it('listRequirements omits status unless supplied', async () => {
      await proofApi.listRequirements('/ws');
      expect(captured.url).toBe('/api/v2/proof/requirements');
      expect(captured.params).toEqual({ workspace_path: '/ws' });

      await proofApi.listRequirements('/ws', 'OPEN' as never);
      expect(captured.params).toEqual({ workspace_path: '/ws', status: 'OPEN' });
    });

    it('getRequirement → GET /api/v2/proof/requirements/:id', async () => {
      await proofApi.getRequirement('/ws', 'REQ-1');
      expect(captured.method).toBe('get');
      expect(captured.url).toBe('/api/v2/proof/requirements/REQ-1');
      expect(captured.params).toEqual({ workspace_path: '/ws' });
    });

    it('getEvidence → GET /api/v2/proof/requirements/:id/evidence', async () => {
      await proofApi.getEvidence('/ws', 'REQ-1');
      expect(captured.method).toBe('get');
      expect(captured.url).toBe('/api/v2/proof/requirements/REQ-1/evidence');
      expect(captured.params).toEqual({ workspace_path: '/ws' });
    });

    it('capture → POST /api/v2/proof/requirements with the body verbatim', async () => {
      const body = { title: 'T', description: 'd' } as never;
      await proofApi.capture('/ws', body);
      expect(captured.method).toBe('post');
      expect(captured.url).toBe('/api/v2/proof/requirements');
      expect(captured.body).toEqual({ title: 'T', description: 'd' });
    });

    it('waive → POST /api/v2/proof/requirements/:id/waive', async () => {
      await proofApi.waive('/ws', 'REQ-1', { reason: 'r' } as never);
      expect(captured.url).toBe('/api/v2/proof/requirements/REQ-1/waive');
      expect(captured.body).toEqual({ reason: 'r' });
    });

    it('startRun → POST /api/v2/proof/run with the body verbatim', async () => {
      await proofApi.startRun('/ws', { gates: ['unit'], strictness: 'strict' } as never);
      expect(captured.method).toBe('post');
      expect(captured.url).toBe('/api/v2/proof/run');
      expect(captured.body).toEqual({ gates: ['unit'], strictness: 'strict' });
      expect(captured.params).toEqual({ workspace_path: '/ws' });
    });

    it('getRun → GET /api/v2/proof/runs/:id', async () => {
      await proofApi.getRun('/ws', 'r-1');
      expect(captured.method).toBe('get');
      expect(captured.url).toBe('/api/v2/proof/runs/r-1');
      expect(captured.params).toEqual({ workspace_path: '/ws' });
    });

    it('listRuns → GET /api/v2/proof/runs with a default limit of 5', async () => {
      await proofApi.listRuns('/ws');
      expect(captured.params).toEqual({ workspace_path: '/ws', limit: 5 });
    });

    it('getRunDetail → GET /api/v2/proof/runs/:id/evidence', async () => {
      await proofApi.getRunDetail('/ws', 'r-1');
      expect(captured.method).toBe('get');
      expect(captured.url).toBe('/api/v2/proof/runs/r-1/evidence');
      expect(captured.params).toEqual({ workspace_path: '/ws' });
    });
  });

  describe('prApi', () => {
    it('create → POST /api/v2/pr with the request verbatim', async () => {
      await prApi.create('/ws', { branch: '', title: 'T', body: 'B' });
      expect(captured.method).toBe('post');
      expect(captured.url).toBe('/api/v2/pr');
      expect(captured.body).toEqual({ branch: '', title: 'T', body: 'B' });
    });

    it('getStatus → GET /api/v2/pr/status?pr_number=', async () => {
      await prApi.getStatus('/ws', 7);
      expect(captured.params).toEqual({ workspace_path: '/ws', pr_number: 7 });
    });

    it('merge defaults the method to squash and omits override keys', async () => {
      await prApi.merge('/ws', 7);
      expect(captured.method).toBe('post');
      expect(captured.url).toBe('/api/v2/pr/7/merge');
      expect(captured.body).toEqual({ method: 'squash' });
    });

    it('merge sends override and its reason together', async () => {
      await prApi.merge('/ws', 7, { override: true, override_reason: 'because' });
      expect(captured.body).toEqual({
        method: 'squash',
        override: true,
        override_reason: 'because',
      });
    });

    it('list defaults state to open', async () => {
      await prApi.list('/ws');
      expect(captured.params).toEqual({ workspace_path: '/ws', state: 'open' });
    });

    it('getHistory omits limit unless supplied', async () => {
      await prApi.getHistory('/ws');
      expect(captured.params).toEqual({ workspace_path: '/ws' });
      await prApi.getHistory('/ws', 10);
      expect(captured.params).toEqual({ workspace_path: '/ws', limit: 10 });
    });

    it('getFiles → GET /api/v2/pr/:n/files and unwraps .files', async () => {
      stubResponseData = { files: ['a.ts'] };
      const files = await prApi.getFiles('/ws', 7);
      expect(captured.url).toBe('/api/v2/pr/7/files');
      expect(files).toEqual(['a.ts']);
    });
  });

  describe('sessionsApi', () => {
    it('getAll → GET /api/v2/sessions and wraps the array', async () => {
      stubResponseData = [{ id: 's1' }];
      const res = await sessionsApi.getAll('/ws');
      expect(captured.url).toBe('/api/v2/sessions');
      expect(captured.params).toEqual({ workspace_path: '/ws' });
      expect(res).toEqual({ sessions: [{ id: 's1' }], total: 1 });
    });

    it('getAll forwards a state filter', async () => {
      stubResponseData = [];
      await sessionsApi.getAll('/ws', { state: 'active' as never });
      expect(captured.params).toEqual({ workspace_path: '/ws', state: 'active' });
    });

    it('create → POST /api/v2/sessions with the payload verbatim', async () => {
      await sessionsApi.create({ workspace_path: '/ws' } as never);
      expect(captured.method).toBe('post');
      expect(captured.url).toBe('/api/v2/sessions');
      expect(captured.body).toEqual({ workspace_path: '/ws' });
    });

    it('getOne encodes the session id', async () => {
      await sessionsApi.getOne('s/1');
      expect(captured.url).toBe('/api/v2/sessions/s%2F1');
    });

    it('getMessages maps created_at to createdAt', async () => {
      stubResponseData = [
        { id: 'm1', role: 'user', content: 'hi', created_at: '2026-01-01T00:00:00Z' },
      ];
      const msgs = await sessionsApi.getMessages('s-1', { limit: 10 });
      expect(captured.url).toBe('/api/v2/sessions/s-1/messages');
      expect(captured.params).toEqual({ limit: 10 });
      expect(msgs).toEqual([
        { id: 'm1', role: 'user', content: 'hi', createdAt: '2026-01-01T00:00:00Z' },
      ]);
    });

    it('end → DELETE /api/v2/sessions/:id', async () => {
      await sessionsApi.end('s-1');
      expect(captured.method).toBe('delete');
      expect(captured.url).toBe('/api/v2/sessions/s-1');
    });
  });

  describe('settingsApi', () => {
    it('get → GET /api/v2/settings', async () => {
      await settingsApi.get('/ws');
      expect(captured.url).toBe('/api/v2/settings');
      expect(captured.params).toEqual({ workspace_path: '/ws' });
    });

    it('update → PUT /api/v2/settings with the body verbatim', async () => {
      await settingsApi.update('/ws', { engine: 'react' } as never);
      expect(captured.method).toBe('put');
      expect(captured.body).toEqual({ engine: 'react' });
    });

    it('getKeys → GET /api/v2/settings/keys with no params', async () => {
      await settingsApi.getKeys();
      expect(captured.url).toBe('/api/v2/settings/keys');
      expect(captured.params).toBeUndefined();
    });

    it('storeKey → PUT /api/v2/settings/keys/:provider with {value}', async () => {
      await settingsApi.storeKey('anthropic' as never, 'sk-1');
      expect(captured.method).toBe('put');
      expect(captured.url).toBe('/api/v2/settings/keys/anthropic');
      expect(captured.body).toEqual({ value: 'sk-1' });
    });

    it('removeKey → DELETE /api/v2/settings/keys/:provider', async () => {
      await settingsApi.removeKey('anthropic' as never);
      expect(captured.method).toBe('delete');
      expect(captured.url).toBe('/api/v2/settings/keys/anthropic');
    });

    it('verifyKey sends value:null when omitted', async () => {
      await settingsApi.verifyKey('anthropic' as never);
      expect(captured.method).toBe('post');
      expect(captured.url).toBe('/api/v2/settings/verify-key');
      expect(captured.body).toEqual({ provider: 'anthropic', value: null });
    });

    it('verifyKey forwards a supplied value', async () => {
      await settingsApi.verifyKey('anthropic' as never, 'sk-live');
      expect(captured.body).toEqual({ provider: 'anthropic', value: 'sk-live' });
    });
  });

  describe('proofConfigApi', () => {
    it('getConfig → GET /api/v2/proof/config', async () => {
      await proofConfigApi.getConfig('/ws');
      expect(captured.url).toBe('/api/v2/proof/config');
      expect(captured.params).toEqual({ workspace_path: '/ws' });
    });

    it('updateConfig → PUT /api/v2/proof/config', async () => {
      await proofConfigApi.updateConfig('/ws', { strictness: 'strict' } as never);
      expect(captured.method).toBe('put');
      expect(captured.body).toEqual({ strictness: 'strict' });
    });
  });

  describe('workspaceConfigApi', () => {
    it('getConfig → GET /api/v2/workspaces/config', async () => {
      await workspaceConfigApi.getConfig('/ws');
      expect(captured.url).toBe('/api/v2/workspaces/config');
    });

    it('updateConfig → PUT /api/v2/workspaces/config', async () => {
      await workspaceConfigApi.updateConfig('/ws', { tech_stack: 'py' } as never);
      expect(captured.method).toBe('put');
      expect(captured.body).toEqual({ tech_stack: 'py' });
    });
  });

  describe('notificationsApi', () => {
    it('get → GET /api/v2/settings/notifications', async () => {
      await notificationsApi.get('/ws');
      expect(captured.url).toBe('/api/v2/settings/notifications');
    });

    it('update → PUT /api/v2/settings/notifications', async () => {
      await notificationsApi.update('/ws', { enabled: true, url: 'u' } as never);
      expect(captured.method).toBe('put');
      expect(captured.body).toEqual({ enabled: true, url: 'u' });
    });

    it('test → POST /api/v2/settings/notifications/test with no body', async () => {
      await notificationsApi.test('/ws');
      expect(captured.method).toBe('post');
      expect(captured.url).toBe('/api/v2/settings/notifications/test');
      expect(captured.body).toBeUndefined();
    });
  });

  describe('integrationsApi', () => {
    it('getStatus → GET /api/v2/integrations/github/status', async () => {
      await integrationsApi.getStatus('/ws');
      expect(captured.url).toBe('/api/v2/integrations/github/status');
    });

    it('connect → POST .../connect with {pat, repo}', async () => {
      await integrationsApi.connect('/ws', 'ghp_x', 'o/r');
      expect(captured.method).toBe('post');
      expect(captured.url).toBe('/api/v2/integrations/github/connect');
      expect(captured.body).toEqual({ pat: 'ghp_x', repo: 'o/r' });
    });

    it('disconnect → DELETE .../disconnect', async () => {
      await integrationsApi.disconnect('/ws');
      expect(captured.method).toBe('delete');
      expect(captured.url).toBe('/api/v2/integrations/github/disconnect');
    });

    it('getIssues sends snake_case per_page and defaults page/search/label', async () => {
      await integrationsApi.getIssues('/ws');
      expect(captured.url).toBe('/api/v2/integrations/github/issues');
      expect(captured.params).toEqual({
        workspace_path: '/ws',
        page: 1,
        per_page: 25,
        search: '',
        label: '',
      });
    });

    it('getIssues forwards explicit paging and filters', async () => {
      await integrationsApi.getIssues('/ws', { page: 3, perPage: 50, search: 'bug', label: 'ui' });
      expect(captured.params).toEqual({
        workspace_path: '/ws',
        page: 3,
        per_page: 50,
        search: 'bug',
        label: 'ui',
      });
    });

    it('importIssues → POST .../import with snake_case issue_numbers', async () => {
      await integrationsApi.importIssues('/ws', [1, 2]);
      expect(captured.url).toBe('/api/v2/integrations/github/import');
      expect(captured.body).toEqual({ issue_numbers: [1, 2] });
    });
  });

  describe('costsApi', () => {
    it('getSummary → GET /api/v2/costs/summary?days=', async () => {
      await costsApi.getSummary('/ws', 7);
      expect(captured.url).toBe('/api/v2/costs/summary');
      expect(captured.params).toEqual({ workspace_path: '/ws', days: 7 });
    });

    it('getTopTasks defaults days=30 and limit=10', async () => {
      await costsApi.getTopTasks('/ws');
      expect(captured.url).toBe('/api/v2/costs/tasks');
      expect(captured.params).toEqual({ workspace_path: '/ws', days: 30, limit: 10 });
    });

    it('getByAgent defaults days=30', async () => {
      await costsApi.getByAgent('/ws');
      expect(captured.url).toBe('/api/v2/costs/by-agent');
      expect(captured.params).toEqual({ workspace_path: '/ws', days: 30 });
    });
  });

  // ── Coverage guard (issue #965) ────────────────────────────────────────
  //
  // The whole point of this file is that every OTHER suite mocks @/lib/api, so
  // a wrong method, path, renamed query param or reshaped body passes green
  // everywhere else. That guarantee is only as good as its coverage, and it
  // previously covered 3 of 19 namespaces. This guard fails when a namespace
  // is added without a contract case, so the gap cannot silently reopen.

  describe('coverage guard', () => {
    const COVERED = new Set([
      'workspaceApi',
      'tasksApi',
      'eventsApi',
      'blockersApi',
      'batchesApi',
      'prdApi',
      'discoveryApi',
      'reviewApi',
      'gatesApi',
      'gitApi',
      'proofApi',
      'prApi',
      'sessionsApi',
      'settingsApi',
      'proofConfigApi',
      'workspaceConfigApi',
      'notificationsApi',
      'integrationsApi',
      'costsApi',
    ]);

    it('every exported *Api namespace has contract cases in this file', () => {
      const exported = Object.keys(apiModule).filter((k) => k.endsWith('Api'));
      const uncovered = exported.filter((n) => !COVERED.has(n));
      expect(uncovered).toEqual([]);
    });

    it('the covered list has no stale entries', () => {
      const exported = new Set(
        Object.keys(apiModule).filter((k) => k.endsWith('Api'))
      );
      const stale = [...COVERED].filter((n) => !exported.has(n));
      expect(stale).toEqual([]);
    });

    it('each covered namespace has a describe block naming it', () => {
      // Cheap structural check: the source of this file must mention every
      // covered namespace inside a describe(...) header, so an entry cannot be
      // added to COVERED without actual cases behind it.
      const src = readFileSync(__filename, 'utf8');
      const missing = [...COVERED].filter(
        (n) => !src.includes(`describe('${n}'`)
      );
      expect(missing).toEqual([]);
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
