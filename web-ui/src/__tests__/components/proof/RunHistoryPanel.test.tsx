import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import useSWR from 'swr';
import { RunHistoryPanel } from '@/components/proof/RunHistoryPanel';
import type { ProofRunSummary } from '@/types';

jest.mock('swr');
jest.mock('@/lib/api', () => ({
  proofApi: {
    listRuns: jest.fn(),
  },
}));

const mockUseSWR = useSWR as jest.MockedFunction<typeof useSWR>;

function makeRun(overrides: Partial<ProofRunSummary> = {}): ProofRunSummary {
  return {
    run_id: 'abc12345',
    started_at: '2026-04-09T12:00:00Z',
    completed_at: '2026-04-09T12:00:05Z',
    triggered_by: 'human',
    overall_passed: true,
    duration_ms: 5000,
    vacuous_pass: false,
    ...overrides,
  };
}

const WORKSPACE = '/home/user/project';

describe('RunHistoryPanel', () => {
  afterEach(() => jest.clearAllMocks());

  it('shows loading skeletons while loading', () => {
    mockUseSWR.mockReturnValue({ data: undefined, error: undefined, isLoading: true } as ReturnType<typeof useSWR>);
    render(<RunHistoryPanel workspacePath={WORKSPACE} onSelectRun={jest.fn()} selectedRunId={null} />);
    expect(screen.getAllByRole('generic').some((el) => el.className.includes('animate-pulse'))).toBe(true);
  });

  it('shows error message on fetch failure', () => {
    mockUseSWR.mockReturnValue({ data: undefined, error: new Error('fail'), isLoading: false } as ReturnType<typeof useSWR>);
    render(<RunHistoryPanel workspacePath={WORKSPACE} onSelectRun={jest.fn()} selectedRunId={null} />);
    expect(screen.getByText('Failed to load run history.')).toBeInTheDocument();
  });

  it('shows empty state when no runs', () => {
    mockUseSWR.mockReturnValue({ data: [], error: undefined, isLoading: false } as ReturnType<typeof useSWR>);
    render(<RunHistoryPanel workspacePath={WORKSPACE} onSelectRun={jest.fn()} selectedRunId={null} />);
    expect(screen.getByText('No runs recorded yet.')).toBeInTheDocument();
  });

  it('renders run rows', () => {
    const runs = [makeRun({ run_id: 'run1' }), makeRun({ run_id: 'run2', overall_passed: false })];
    mockUseSWR.mockReturnValue({ data: runs, error: undefined, isLoading: false } as ReturnType<typeof useSWR>);
    render(<RunHistoryPanel workspacePath={WORKSPACE} onSelectRun={jest.fn()} selectedRunId={null} />);
    expect(screen.getAllByText('pass').length + screen.getAllByText('fail').length).toBeGreaterThanOrEqual(1);
  });

  it('calls onSelectRun with run_id when row is clicked', () => {
    const onSelectRun = jest.fn();
    const run = makeRun({ run_id: 'abc12345' });
    mockUseSWR.mockReturnValue({ data: [run], error: undefined, isLoading: false } as ReturnType<typeof useSWR>);
    render(<RunHistoryPanel workspacePath={WORKSPACE} onSelectRun={onSelectRun} selectedRunId={null} />);
    // Find the clickable row
    const rows = screen.getAllByRole('button');
    fireEvent.click(rows[0]);
    expect(onSelectRun).toHaveBeenCalledWith('abc12345');
  });

  it('highlights selected run row', () => {
    const run = makeRun({ run_id: 'abc12345' });
    mockUseSWR.mockReturnValue({ data: [run], error: undefined, isLoading: false } as ReturnType<typeof useSWR>);
    render(<RunHistoryPanel workspacePath={WORKSPACE} onSelectRun={jest.fn()} selectedRunId="abc12345" />);
    const rows = screen.getAllByRole('button');
    expect(rows[0].className).toContain('bg-muted');
  });

  it('labels a vacuous pass distinctly instead of showing it as a pass (#1247)', () => {
    const run = makeRun({ run_id: 'vac1', overall_passed: true, vacuous_pass: true });
    mockUseSWR.mockReturnValue({ data: [run], error: undefined, isLoading: false } as ReturnType<typeof useSWR>);
    render(<RunHistoryPanel workspacePath={WORKSPACE} onSelectRun={jest.fn()} selectedRunId={null} />);
    expect(screen.getByText('vacuous')).toBeInTheDocument();
    expect(screen.queryByText('pass')).not.toBeInTheDocument();
  });

  it('still shows an ordinary pass as pass', () => {
    const run = makeRun({ run_id: 'ok1', overall_passed: true, vacuous_pass: false });
    mockUseSWR.mockReturnValue({ data: [run], error: undefined, isLoading: false } as ReturnType<typeof useSWR>);
    render(<RunHistoryPanel workspacePath={WORKSPACE} onSelectRun={jest.fn()} selectedRunId={null} />);
    expect(screen.getByText('pass')).toBeInTheDocument();
    expect(screen.queryByText('vacuous')).not.toBeInTheDocument();
  });

  it('a failing run is never labelled vacuous', () => {
    const run = makeRun({ run_id: 'bad1', overall_passed: false, vacuous_pass: true });
    mockUseSWR.mockReturnValue({ data: [run], error: undefined, isLoading: false } as ReturnType<typeof useSWR>);
    render(<RunHistoryPanel workspacePath={WORKSPACE} onSelectRun={jest.fn()} selectedRunId={null} />);
    expect(screen.getByText('fail')).toBeInTheDocument();
    expect(screen.queryByText('vacuous')).not.toBeInTheDocument();
  });

  it('explains what a vacuous pass means on hover', () => {
    const run = makeRun({ run_id: 'vac2', overall_passed: true, vacuous_pass: true });
    mockUseSWR.mockReturnValue({ data: [run], error: undefined, isLoading: false } as ReturnType<typeof useSWR>);
    render(<RunHistoryPanel workspacePath={WORKSPACE} onSelectRun={jest.fn()} selectedRunId={null} />);
    expect(screen.getByText('vacuous')).toHaveAttribute(
      'title',
      expect.stringContaining('no gates ran') as unknown as string,
    );
  });

  it('shows "Recent Runs" heading', () => {
    mockUseSWR.mockReturnValue({ data: [], error: undefined, isLoading: false } as ReturnType<typeof useSWR>);
    render(<RunHistoryPanel workspacePath={WORKSPACE} onSelectRun={jest.fn()} selectedRunId={null} />);
    expect(screen.getByText('Recent Runs')).toBeInTheDocument();
  });
});
