import { renderHook, act, waitFor } from '@testing-library/react';
import { useBatchNotificationWatcher } from '@/hooks/useBatchNotificationWatcher';
import { batchesApi, tasksApi } from '@/lib/api';
import { getSelectedWorkspacePath } from '@/lib/workspace-storage';
import type { BatchListResponse, BatchResponse, Task } from '@/types';

jest.mock('@/lib/api');
jest.mock('@/lib/workspace-storage');

const mockList = batchesApi.list as jest.MockedFunction<typeof batchesApi.list>;
const mockGetTask = tasksApi.getOne as jest.MockedFunction<typeof tasksApi.getOne>;
const mockGetWorkspacePath = getSelectedWorkspacePath as jest.MockedFunction<
  typeof getSelectedWorkspacePath
>;

function batch(overrides: Partial<BatchResponse> = {}): BatchResponse {
  return {
    id: 'batch-1234abcd',
    workspace_id: 'ws-1',
    task_ids: ['t1'],
    status: 'RUNNING',
    strategy: 'serial',
    max_parallel: 1,
    on_failure: 'continue',
    started_at: null,
    completed_at: null,
    results: { t1: 'IN_PROGRESS' },
    ...overrides,
  };
}

function listResponse(batches: BatchResponse[]): BatchListResponse {
  return { batches, total: batches.length, by_status: {} };
}

// Queue a sequence of list() responses, one per poll tick.
function queueResponses(...responses: BatchListResponse[]) {
  mockList.mockReset();
  responses.forEach((r) => mockList.mockResolvedValueOnce(r));
  // Any further polls repeat the last response.
  if (responses.length > 0) {
    mockList.mockResolvedValue(responses[responses.length - 1]);
  }
}

const INTERVAL = 1000;

beforeEach(() => {
  jest.useFakeTimers();
  jest.clearAllMocks();
  mockGetWorkspacePath.mockReturnValue('/ws');
  mockGetTask.mockResolvedValue({ id: 't1', title: 'Build login form' } as Task);
});

afterEach(() => {
  jest.runOnlyPendingTimers();
  jest.useRealTimers();
});

/** Run the immediate mount poll + flush its async work. */
async function flushPoll() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

/** Advance one polling interval and flush async work. */
async function tick() {
  await act(async () => {
    jest.advanceTimersByTime(INTERVAL);
    await Promise.resolve();
    await Promise.resolve();
  });
}

describe('useBatchNotificationWatcher', () => {
  it('does not notify for batches already terminal on the first poll (baseline)', async () => {
    const addNotification = jest.fn();
    queueResponses(listResponse([batch({ status: 'COMPLETED', results: { t1: 'COMPLETED' } })]));

    renderHook(() => useBatchNotificationWatcher(addNotification, { intervalMs: INTERVAL }));
    await flushPoll();

    expect(addNotification).not.toHaveBeenCalled();
  });

  it('fires batch.completed when a running batch transitions to a terminal state', async () => {
    const addNotification = jest.fn();
    queueResponses(
      listResponse([batch({ status: 'RUNNING', results: { t1: 'IN_PROGRESS' } })]),
      listResponse([batch({ status: 'COMPLETED', results: { t1: 'COMPLETED' } })])
    );

    renderHook(() => useBatchNotificationWatcher(addNotification, { intervalMs: INTERVAL }));
    await flushPoll(); // baseline = RUNNING
    expect(addNotification).not.toHaveBeenCalled();

    await tick(); // now COMPLETED

    expect(addNotification).toHaveBeenCalledTimes(1);
    expect(addNotification).toHaveBeenCalledWith(
      expect.objectContaining({
        type: 'batch.completed',
        batchStatus: 'COMPLETED',
        batchId: 'batch-1234abcd',
      })
    );
  });

  it('fires batch.completed only once across repeated polls', async () => {
    const addNotification = jest.fn();
    queueResponses(
      listResponse([batch({ status: 'RUNNING', results: { t1: 'IN_PROGRESS' } })]),
      listResponse([batch({ status: 'FAILED', results: { t1: 'FAILED' } })])
    );

    renderHook(() => useBatchNotificationWatcher(addNotification, { intervalMs: INTERVAL }));
    await flushPoll();
    await tick(); // FAILED
    await tick(); // still FAILED — must not re-fire

    expect(addNotification).toHaveBeenCalledTimes(1);
    expect(addNotification).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'batch.completed', batchStatus: 'FAILED' })
    );
  });

  it('fires blocker.created with the task title when a task transitions to BLOCKED', async () => {
    const addNotification = jest.fn();
    queueResponses(
      listResponse([batch({ status: 'RUNNING', results: { t1: 'IN_PROGRESS' } })]),
      listResponse([batch({ status: 'RUNNING', results: { t1: 'BLOCKED' } })])
    );

    renderHook(() => useBatchNotificationWatcher(addNotification, { intervalMs: INTERVAL }));
    await flushPoll();
    await tick();

    await waitFor(() =>
      expect(addNotification).toHaveBeenCalledWith(
        expect.objectContaining({
          type: 'blocker.created',
          taskId: 't1',
          message: expect.stringContaining('Build login form'),
        })
      )
    );
  });

  it('does nothing when no workspace is selected', async () => {
    const addNotification = jest.fn();
    mockGetWorkspacePath.mockReturnValue(null);
    queueResponses(listResponse([batch()]));

    renderHook(() => useBatchNotificationWatcher(addNotification, { intervalMs: INTERVAL }));
    await flushPoll();

    expect(mockList).not.toHaveBeenCalled();
    expect(addNotification).not.toHaveBeenCalled();
  });

  it('does not start an overlapping poll while one is still in flight', async () => {
    const addNotification = jest.fn();
    // First list() never resolves during the test window — simulates a slow poll.
    let resolveSlow: (v: BatchListResponse) => void = () => {};
    const slow = new Promise<BatchListResponse>((res) => {
      resolveSlow = res;
    });
    mockList.mockReset();
    mockList.mockReturnValueOnce(slow);
    mockList.mockResolvedValue(listResponse([batch()]));

    renderHook(() => useBatchNotificationWatcher(addNotification, { intervalMs: INTERVAL }));
    await flushPoll(); // immediate poll starts, awaiting `slow`
    await tick(); // interval fires but must be skipped (in-flight)
    await tick();

    // Only the one still-pending call was made; no overlap.
    expect(mockList).toHaveBeenCalledTimes(1);

    // Let the slow poll finish; subsequent ticks resume normally.
    await act(async () => {
      resolveSlow(listResponse([batch()]));
      await Promise.resolve();
      await Promise.resolve();
    });
    await tick();
    expect(mockList.mock.calls.length).toBeGreaterThan(1);
  });

  it('stops polling after unmount', async () => {
    const addNotification = jest.fn();
    queueResponses(listResponse([batch()]));

    const { unmount } = renderHook(() =>
      useBatchNotificationWatcher(addNotification, { intervalMs: INTERVAL })
    );
    await flushPoll();
    const callsBefore = mockList.mock.calls.length;

    unmount();
    await tick();

    expect(mockList.mock.calls.length).toBe(callsBefore);
  });
});
