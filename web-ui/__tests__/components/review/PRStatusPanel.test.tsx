import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { PRStatusPanel } from '@/components/review/PRStatusPanel';

jest.mock('@/lib/api', () => ({
  prApi: {
    getStatus: jest.fn(),
    merge: jest.fn(),
  },
  proofApi: {
    getStatus: jest.fn(),
  },
}));

jest.mock('@/lib/workspace-storage', () => ({
  getSelectedWorkspacePath: jest.fn(() => '/test/workspace'),
}));

jest.mock('swr', () => ({ __esModule: true, default: jest.fn() }));

import useSWR from 'swr';
import { prApi } from '@/lib/api';

const mockUseSWR = useSWR as jest.MockedFunction<typeof useSWR>;
const mockMerge = prApi.merge as jest.MockedFunction<typeof prApi.merge>;

// ── Fixtures ──────────────────────────────────────────────────────────────────

const successfulCIChecks = [
  { name: 'tests', status: 'completed', conclusion: 'success' },
  { name: 'lint', status: 'completed', conclusion: 'success' },
];

const failingCIChecks = [
  { name: 'tests', status: 'completed', conclusion: 'failure' },
];

const basePRStatus = {
  ci_checks: successfulCIChecks,
  review_status: 'approved',
  merge_state: 'open',
  pr_url: 'https://github.com/test/repo/pull/42',
  pr_number: 42,
};

const openReq = {
  id: 'REQ-001',
  title: 'Fix critical bug',
  status: 'open',
  description: 'A test requirement',
  severity: 'high',
  source: 'manual',
  glitch_type: null,
  obligations: [],
  evidence_rules: [],
  waiver: null,
  created_at: '2026-01-01T00:00:00Z',
  satisfied_at: null,
  created_by: 'tester',
  source_issue: null,
  related_reqs: [],
  scope: null,
};

const cleanProofStatus = {
  total: 0,
  open: 0,
  satisfied: 0,
  waived: 0,
  requirements: [],
};

const proofStatusWithOpenReqs = {
  total: 1,
  open: 1,
  satisfied: 0,
  waived: 0,
  requirements: [openReq],
};

// ── Helpers ───────────────────────────────────────────────────────────────────

const setupSWRMock = (prStatus: object, proofStatus: object) => {
  mockUseSWR.mockImplementation((key: unknown) => {
    const keyStr = typeof key === 'string' ? key : '';
    if (keyStr.includes('/api/v2/proof/status')) {
      return { data: proofStatus, error: undefined, isLoading: false, mutate: jest.fn() } as any;
    }
    return { data: prStatus, error: undefined, isLoading: false, mutate: jest.fn() } as any;
  });
};

const defaultProps = {
  prNumber: 42,
  workspacePath: '/test/workspace',
};

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('PRStatusPanel — PROOF9-gated merge button', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('disables merge button when PROOF9 has open requirements', () => {
    setupSWRMock(basePRStatus, proofStatusWithOpenReqs);
    render(<PRStatusPanel {...defaultProps} />);
    expect(screen.getByRole('button', { name: /^merge$/i })).toBeDisabled();
  });

  it('shows blocking REQ titles inline when PROOF9 has open requirements', () => {
    setupSWRMock(basePRStatus, proofStatusWithOpenReqs);
    render(<PRStatusPanel {...defaultProps} />);
    expect(screen.getByText('Fix critical bug')).toBeInTheDocument();
  });

  it('shows link to /proof page when PROOF9 is blocking', () => {
    setupSWRMock(basePRStatus, proofStatusWithOpenReqs);
    render(<PRStatusPanel {...defaultProps} />);
    expect(screen.getByRole('link', { name: /view all/i })).toHaveAttribute('href', '/proof');
  });

  it('enables merge button when all requirements are cleared and CI passes', () => {
    setupSWRMock(basePRStatus, cleanProofStatus);
    render(<PRStatusPanel {...defaultProps} />);
    expect(screen.getByRole('button', { name: /^merge$/i })).not.toBeDisabled();
  });

  it('shows success banner and removes merge button after successful merge', async () => {
    setupSWRMock(basePRStatus, cleanProofStatus);
    mockMerge.mockResolvedValueOnce({ sha: 'abc123', merged: true, message: 'Merged!' });
    render(<PRStatusPanel {...defaultProps} />);

    fireEvent.click(screen.getByRole('button', { name: /^merge$/i }));

    await waitFor(() => {
      expect(screen.getByText(/merged successfully/i)).toBeInTheDocument();
    });
    expect(screen.queryByRole('button', { name: /merge/i })).not.toBeInTheDocument();
  });

  it('shows error message and re-enables button when merge API call fails', async () => {
    setupSWRMock(basePRStatus, cleanProofStatus);
    mockMerge.mockRejectedValueOnce({ detail: 'Cannot merge: conflicts detected' });
    render(<PRStatusPanel {...defaultProps} />);

    fireEvent.click(screen.getByRole('button', { name: /^merge$/i }));

    await waitFor(() => {
      expect(screen.getByText(/cannot merge/i)).toBeInTheDocument();
    });
    expect(screen.getByRole('button', { name: /^merge$/i })).toBeInTheDocument();
  });

  it('disables merge button and shows loading text while merge is in-flight', async () => {
    setupSWRMock(basePRStatus, cleanProofStatus);
    let resolveMerge!: (val: unknown) => void;
    const mergePromise = new Promise((resolve) => {
      resolveMerge = resolve;
    });
    mockMerge.mockReturnValueOnce(mergePromise as any);
    render(<PRStatusPanel {...defaultProps} />);

    fireEvent.click(screen.getByRole('button', { name: /^merge$/i }));

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /merging/i })).toBeDisabled();
    });

    resolveMerge({ sha: 'abc', merged: true, message: 'ok' });
  });

  it('shows CI blocking message when CI checks are failing', () => {
    setupSWRMock({ ...basePRStatus, ci_checks: failingCIChecks }, cleanProofStatus);
    render(<PRStatusPanel {...defaultProps} />);
    expect(screen.getByText(/ci checks failing/i)).toBeInTheDocument();
  });

  it('shows both CI and PROOF9 blocking messages when both are blocking', () => {
    setupSWRMock({ ...basePRStatus, ci_checks: failingCIChecks }, proofStatusWithOpenReqs);
    render(<PRStatusPanel {...defaultProps} />);
    expect(screen.getByText(/ci checks failing/i)).toBeInTheDocument();
    expect(screen.getByText('Fix critical bug')).toBeInTheDocument();
  });
});
