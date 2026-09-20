/**
 * Audited merge-gate override from the PR status panel (#1247 AC3).
 *
 * The API and CLI have taken `override` + `override_reason` since #731, but the
 * browser had no way to supply them: the Merge button is *disabled* while
 * requirements are open, so a blocked merge simply dead-ended. Note that means
 * a 409 alone is not the trigger — the user never gets to send the request
 * that would produce one — so the panel needs its own visible override path.
 */

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

const basePRStatus = {
  ci_checks: [{ name: 'tests', status: 'completed', conclusion: 'success' }],
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

const proofStatusWithOpenReqs = {
  total: 1,
  open: 1,
  satisfied: 0,
  waived: 0,
  requirements: [openReq],
};

const cleanProofStatus = {
  total: 0,
  open: 0,
  satisfied: 0,
  waived: 0,
  requirements: [],
};

const setupSWRMock = (prStatus: object | undefined, proofStatus: object | undefined) => {
  mockUseSWR.mockImplementation((key: unknown) => {
    const keyStr = typeof key === 'string' ? key : '';
    if (keyStr.includes('/api/v2/proof/status')) {
      return { data: proofStatus, error: undefined, isLoading: false, mutate: jest.fn() } as any;
    }
    return { data: prStatus, error: undefined, isLoading: false, mutate: jest.fn() } as any;
  });
};

const defaultProps = { prNumber: 42, workspacePath: '/test/workspace' };

const openOverrideDialog = () => {
  fireEvent.click(screen.getByRole('button', { name: /override/i }));
};

describe('PRStatusPanel — merge gate override', () => {
  beforeEach(() => jest.clearAllMocks());

  it('offers an override affordance when PROOF9 blocks the merge', () => {
    setupSWRMock(basePRStatus, proofStatusWithOpenReqs);
    render(<PRStatusPanel {...defaultProps} />);

    expect(screen.getByRole('button', { name: /^merge$/i })).toBeDisabled();
    expect(screen.getByRole('button', { name: /override/i })).toBeEnabled();
  });

  it('offers no override when nothing is blocking', () => {
    setupSWRMock(basePRStatus, cleanProofStatus);
    render(<PRStatusPanel {...defaultProps} />);

    expect(screen.getByRole('button', { name: /^merge$/i })).toBeEnabled();
    expect(screen.queryByRole('button', { name: /override/i })).not.toBeInTheDocument();
  });

  it('lists the requirements being bypassed in the dialog', () => {
    setupSWRMock(basePRStatus, proofStatusWithOpenReqs);
    render(<PRStatusPanel {...defaultProps} />);

    openOverrideDialog();

    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByText('REQ-001')).toBeInTheDocument();
  });

  it('will not submit without a reason', () => {
    setupSWRMock(basePRStatus, proofStatusWithOpenReqs);
    render(<PRStatusPanel {...defaultProps} />);
    openOverrideDialog();

    expect(screen.getByRole('button', { name: /override and merge/i })).toBeDisabled();
    expect(mockMerge).not.toHaveBeenCalled();
  });

  it('sends override and reason once a reason is given', async () => {
    mockMerge.mockResolvedValueOnce({ merged: true } as never);
    setupSWRMock(basePRStatus, proofStatusWithOpenReqs);
    render(<PRStatusPanel {...defaultProps} />);
    openOverrideDialog();

    fireEvent.change(screen.getByLabelText(/reason/i), {
      target: { value: 'hotfix; gate is stale' },
    });
    fireEvent.click(screen.getByRole('button', { name: /override and merge/i }));

    await waitFor(() =>
      expect(mockMerge).toHaveBeenCalledWith('/test/workspace', 42, {
        method: 'squash',
        override: true,
        override_reason: 'hotfix; gate is stale',
      })
    );
  });

  it('rejects a whitespace-only reason', () => {
    setupSWRMock(basePRStatus, proofStatusWithOpenReqs);
    render(<PRStatusPanel {...defaultProps} />);
    openOverrideDialog();

    fireEvent.change(screen.getByLabelText(/reason/i), { target: { value: '   ' } });

    expect(screen.getByRole('button', { name: /override and merge/i })).toBeDisabled();
    expect(mockMerge).not.toHaveBeenCalled();
  });

  it('keeps a failed override visible in the dialog', async () => {
    // A non-superuser reaches this point: require_scope(SCOPE_ADMIN) 403s.
    mockMerge.mockRejectedValueOnce({ detail: 'Forbidden: admin scope required', status_code: 403 });
    setupSWRMock(basePRStatus, proofStatusWithOpenReqs);
    render(<PRStatusPanel {...defaultProps} />);
    openOverrideDialog();

    fireEvent.change(screen.getByLabelText(/reason/i), { target: { value: 'because' } });
    fireEvent.click(screen.getByRole('button', { name: /override and merge/i }));

    await waitFor(() => {
      expect(screen.getByText(/admin scope required/i)).toBeInTheDocument();
    });
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('opens the dialog when a merge races a newly-opened requirement (409)', async () => {
    // The panel's view can go stale between render and click; the server is
    // the authority, and its 409 must not dead-end either.
    mockMerge.mockRejectedValueOnce({
      detail: 'PROOF9 merge gate: 1 requirement(s) block this merge',
      status_code: 409,
    });
    setupSWRMock(basePRStatus, cleanProofStatus);
    render(<PRStatusPanel {...defaultProps} />);

    fireEvent.click(screen.getByRole('button', { name: /^merge$/i }));

    await waitFor(() => expect(screen.getByRole('dialog')).toBeInTheDocument());
  });

  it('does not open the dialog for an unrelated merge failure', async () => {
    mockMerge.mockRejectedValueOnce({ detail: 'GitHub is down', status_code: 502 });
    setupSWRMock(basePRStatus, cleanProofStatus);
    render(<PRStatusPanel {...defaultProps} />);

    fireEvent.click(screen.getByRole('button', { name: /^merge$/i }));

    await waitFor(() => expect(screen.getByText(/GitHub is down/i)).toBeInTheDocument());
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
});
