import { renderHook, waitFor } from '@testing-library/react';
import useSWR from 'swr';
import { usePipelineStatus } from '@/hooks/usePipelineStatus';
import { getSelectedWorkspacePath } from '@/lib/workspace-storage';

jest.mock('swr');
jest.mock('@/lib/workspace-storage');

const mockUseSWR = useSWR as jest.MockedFunction<typeof useSWR>;
const mockGetWorkspacePath = getSelectedWorkspacePath as jest.MockedFunction<
  typeof getSelectedWorkspacePath
>;

// Helper to set up SWR mocks for a given scenario, keyed by URL prefix
function mockSWRCalls({
  prd,
  tasks,
  proof,
  review,
}: {
  prd?: { data?: unknown; isLoading?: boolean };
  tasks?: { data?: unknown; isLoading?: boolean };
  proof?: { data?: unknown; isLoading?: boolean };
  review?: { data?: unknown; isLoading?: boolean };
}) {
  mockUseSWR.mockImplementation((key: unknown, ..._rest: unknown[]) => {
    const keyStr = typeof key === 'string' ? key : '';
    let scenario: { data?: unknown; isLoading?: boolean } = {};
    if (keyStr.includes('/pipeline/prd')) scenario = prd ?? {};
    else if (keyStr.includes('/pipeline/tasks')) scenario = tasks ?? {};
    else if (keyStr.includes('/pipeline/proof')) scenario = proof ?? {};
    else if (keyStr.includes('/pipeline/review')) scenario = review ?? {};

    return {
      data: scenario.data ?? undefined,
      isLoading: scenario.isLoading ?? false,
      error: undefined,
      isValidating: false,
      mutate: jest.fn(),
    } as ReturnType<typeof useSWR>;
  });
}

describe('usePipelineStatus', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockGetWorkspacePath.mockReturnValue('/test/workspace');
  });

  it('returns all phases incomplete when no data yet', () => {
    mockSWRCalls({
      prd: { isLoading: true },
      tasks: { isLoading: true },
      proof: { isLoading: true },
      review: { isLoading: true },
    });

    const { result } = renderHook(() => usePipelineStatus());
    expect(result.current.think.isComplete).toBe(false);
    expect(result.current.build.isComplete).toBe(false);
    expect(result.current.prove.isComplete).toBe(false);
    expect(result.current.ship.isComplete).toBe(false);
  });

  it('think phase complete when PRD data returned', () => {
    mockSWRCalls({
      prd: { data: { id: 'prd-1', content: 'some content' } },
      tasks: { data: { tasks: [], total: 0, by_status: { DONE: 0, MERGED: 0 } } },
      proof: { data: { total: 0, open: 0, satisfied: 0, waived: 0 } },
      review: { data: { files_changed: 5 } },
    });

    const { result } = renderHook(() => usePipelineStatus());
    expect(result.current.think.isComplete).toBe(true);
  });

  it('think phase incomplete when PRD endpoint returns no data (404)', () => {
    mockSWRCalls({
      prd: { data: undefined },
      tasks: { data: { tasks: [], total: 0, by_status: { DONE: 0, MERGED: 0 } } },
      proof: { data: { total: 0, open: 0, satisfied: 0, waived: 0 } },
      review: { data: { files_changed: 5 } },
    });

    const { result } = renderHook(() => usePipelineStatus());
    expect(result.current.think.isComplete).toBe(false);
  });

  it('build phase complete when at least one task is DONE', () => {
    mockSWRCalls({
      prd: { data: undefined },
      tasks: {
        data: {
          tasks: [],
          total: 3,
          by_status: { BACKLOG: 1, READY: 1, IN_PROGRESS: 0, DONE: 1, BLOCKED: 0, FAILED: 0, MERGED: 0 },
        },
      },
      proof: { data: { total: 0, open: 0, satisfied: 0, waived: 0 } },
      review: { data: { files_changed: 5 } },
    });

    const { result } = renderHook(() => usePipelineStatus());
    expect(result.current.build.isComplete).toBe(true);
  });

  it('build phase complete when at least one task is MERGED', () => {
    mockSWRCalls({
      prd: { data: undefined },
      tasks: {
        data: {
          tasks: [],
          total: 2,
          by_status: { BACKLOG: 0, READY: 0, IN_PROGRESS: 0, DONE: 0, BLOCKED: 0, FAILED: 0, MERGED: 1 },
        },
      },
      proof: { data: { total: 0, open: 0, satisfied: 0, waived: 0 } },
      review: { data: { files_changed: 5 } },
    });

    const { result } = renderHook(() => usePipelineStatus());
    expect(result.current.build.isComplete).toBe(true);
  });

  it('build phase incomplete when no tasks are done or merged', () => {
    mockSWRCalls({
      prd: { data: undefined },
      tasks: {
        data: {
          tasks: [],
          total: 2,
          by_status: { BACKLOG: 2, READY: 0, IN_PROGRESS: 0, DONE: 0, BLOCKED: 0, FAILED: 0, MERGED: 0 },
        },
      },
      proof: { data: { total: 0, open: 0, satisfied: 0, waived: 0 } },
      review: { data: { files_changed: 5 } },
    });

    const { result } = renderHook(() => usePipelineStatus());
    expect(result.current.build.isComplete).toBe(false);
  });

  it('prove phase complete when proof has requirements and none open', () => {
    mockSWRCalls({
      prd: { data: undefined },
      tasks: { data: { tasks: [], total: 0, by_status: { DONE: 0, MERGED: 0 } } },
      proof: { data: { total: 3, open: 0, satisfied: 3, waived: 0 } },
      review: { data: { files_changed: 5 } },
    });

    const { result } = renderHook(() => usePipelineStatus());
    expect(result.current.prove.isComplete).toBe(true);
  });

  it('prove phase incomplete when open requirements remain', () => {
    mockSWRCalls({
      prd: { data: undefined },
      tasks: { data: { tasks: [], total: 0, by_status: { DONE: 0, MERGED: 0 } } },
      proof: { data: { total: 3, open: 1, satisfied: 2, waived: 0 } },
      review: { data: { files_changed: 5 } },
    });

    const { result } = renderHook(() => usePipelineStatus());
    expect(result.current.prove.isComplete).toBe(false);
  });

  it('prove phase incomplete when total is 0 (no proof requirements)', () => {
    mockSWRCalls({
      prd: { data: undefined },
      tasks: { data: { tasks: [], total: 0, by_status: { DONE: 0, MERGED: 0 } } },
      proof: { data: { total: 0, open: 0, satisfied: 0, waived: 0 } },
      review: { data: { files_changed: 5 } },
    });

    const { result } = renderHook(() => usePipelineStatus());
    expect(result.current.prove.isComplete).toBe(false);
  });

  it('ship phase complete when files_changed is 0', () => {
    mockSWRCalls({
      prd: { data: undefined },
      tasks: { data: { tasks: [], total: 0, by_status: { DONE: 0, MERGED: 0 } } },
      proof: { data: { total: 0, open: 0, satisfied: 0, waived: 0 } },
      review: { data: { files_changed: 0 } },
    });

    const { result } = renderHook(() => usePipelineStatus());
    expect(result.current.ship.isComplete).toBe(true);
  });

  it('ship phase incomplete when there are uncommitted changes', () => {
    mockSWRCalls({
      prd: { data: undefined },
      tasks: { data: { tasks: [], total: 0, by_status: { DONE: 0, MERGED: 0 } } },
      proof: { data: { total: 0, open: 0, satisfied: 0, waived: 0 } },
      review: { data: { files_changed: 3 } },
    });

    const { result } = renderHook(() => usePipelineStatus());
    expect(result.current.ship.isComplete).toBe(false);
  });

  it('returns isLoading true while any phase is loading', () => {
    mockSWRCalls({
      prd: { isLoading: true },
      tasks: { isLoading: false },
      proof: { isLoading: false },
      review: { isLoading: false },
    });

    const { result } = renderHook(() => usePipelineStatus());
    expect(result.current.think.isLoading).toBe(true);
    expect(result.current.build.isLoading).toBe(false);
  });

  it('returns null SWR keys when no workspace selected', () => {
    mockGetWorkspacePath.mockReturnValue(null);
    mockSWRCalls({
      prd: { data: undefined },
      tasks: { data: undefined },
      proof: { data: undefined },
      review: { data: undefined },
    });

    const { result } = renderHook(() => usePipelineStatus());
    // All incomplete when no workspace
    expect(result.current.think.isComplete).toBe(false);
    expect(result.current.build.isComplete).toBe(false);
    expect(result.current.prove.isComplete).toBe(false);
    expect(result.current.ship.isComplete).toBe(false);
  });
});
