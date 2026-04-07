import { renderHook, act, waitFor } from '@testing-library/react';
import { useProofRun } from '@/hooks/useProofRun';
import { proofApi } from '@/lib/api';

jest.mock('@/lib/api', () => ({
  proofApi: {
    startRun: jest.fn(),
    getRun: jest.fn(),
  },
}));

const mockStartRun = proofApi.startRun as jest.MockedFunction<typeof proofApi.startRun>;
const mockGetRun = proofApi.getRun as jest.MockedFunction<typeof proofApi.getRun>;

const WORKSPACE = '/tmp/test-workspace';

const makeStartRunResponse = (passed = true) => ({
  success: true,
  run_id: 'abc123',
  results: {
    'req-1': [
      { gate: 'unit', satisfied: passed },
      { gate: 'sec', satisfied: true },
    ],
  },
  message: 'Proof run complete: 1 requirement(s) evaluated.',
});

const makeGetRunResponse = (passed = true) => ({
  run_id: 'abc123',
  status: 'complete' as const,
  results: {
    'req-1': [
      { gate: 'unit', satisfied: passed },
      { gate: 'sec', satisfied: true },
    ],
  },
  passed,
  message: 'Proof run complete: 1 requirement(s) evaluated.',
});

beforeEach(() => {
  jest.useFakeTimers();
  jest.clearAllMocks();
});

afterEach(() => {
  jest.useRealTimers();
});

describe('useProofRun', () => {
  it('starts in idle state', () => {
    const { result } = renderHook(() => useProofRun());
    expect(result.current.runState).toBe('idle');
    expect(result.current.gateEntries).toHaveLength(0);
    expect(result.current.passed).toBeNull();
    expect(result.current.errorMessage).toBeNull();
  });

  it('transitions to starting then polling on successful POST', async () => {
    mockStartRun.mockResolvedValue(makeStartRunResponse());
    mockGetRun.mockResolvedValue(makeGetRunResponse());

    const { result } = renderHook(() => useProofRun());

    act(() => {
      result.current.startRun(WORKSPACE);
    });

    expect(result.current.runState).toBe('starting');

    await waitFor(() => expect(result.current.runState).toBe('polling'));
    expect(mockStartRun).toHaveBeenCalledWith(WORKSPACE, { full: true });
    expect(result.current.gateEntries.length).toBeGreaterThan(0);
    expect(result.current.gateEntries.every((e) => e.status === 'running')).toBe(true);
  });

  it('transitions to complete after poll resolves', async () => {
    mockStartRun.mockResolvedValue(makeStartRunResponse(true));
    mockGetRun.mockResolvedValue(makeGetRunResponse(true));

    const { result } = renderHook(() => useProofRun());

    act(() => {
      result.current.startRun(WORKSPACE);
    });

    await waitFor(() => expect(result.current.runState).toBe('polling'));

    // Trigger the 2s poll interval
    await act(async () => {
      jest.advanceTimersByTime(2000);
    });

    await waitFor(() => expect(result.current.runState).toBe('complete'));
    expect(result.current.passed).toBe(true);
    expect(result.current.gateEntries.some((e) => e.status === 'passed')).toBe(true);
  });

  it('sets passed=false when gates fail', async () => {
    mockStartRun.mockResolvedValue(makeStartRunResponse(false));
    mockGetRun.mockResolvedValue(makeGetRunResponse(false));

    const { result } = renderHook(() => useProofRun());

    act(() => {
      result.current.startRun(WORKSPACE);
    });

    await waitFor(() => expect(result.current.runState).toBe('polling'));

    await act(async () => {
      jest.advanceTimersByTime(2000);
    });

    await waitFor(() => expect(result.current.runState).toBe('complete'));
    expect(result.current.passed).toBe(false);
  });

  it('transitions to error state on POST failure', async () => {
    mockStartRun.mockRejectedValue(new Error('Network error'));

    const { result } = renderHook(() => useProofRun());

    act(() => {
      result.current.startRun(WORKSPACE);
    });

    await waitFor(() => expect(result.current.runState).toBe('error'));
    expect(result.current.errorMessage).toContain('Network error');
  });

  it('transitions to error state on poll failure', async () => {
    mockStartRun.mockResolvedValue(makeStartRunResponse());
    mockGetRun.mockRejectedValue(new Error('Poll failed'));

    const { result } = renderHook(() => useProofRun());

    act(() => {
      result.current.startRun(WORKSPACE);
    });

    await waitFor(() => expect(result.current.runState).toBe('polling'));

    await act(async () => {
      jest.advanceTimersByTime(2000);
    });

    await waitFor(() => expect(result.current.runState).toBe('error'));
    expect(result.current.errorMessage).toBeTruthy();
  });

  it('retry() resets state to idle', async () => {
    mockStartRun.mockRejectedValue(new Error('fail'));

    const { result } = renderHook(() => useProofRun());

    act(() => {
      result.current.startRun(WORKSPACE);
    });

    await waitFor(() => expect(result.current.runState).toBe('error'));

    act(() => {
      result.current.retry();
    });

    expect(result.current.runState).toBe('idle');
    expect(result.current.errorMessage).toBeNull();
  });
});
