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

const BLOCKERS = [{ id: 'REQ-001', title: 'Fix critical bug' }];

/** The only way to reach the dialog: attempt the merge and let the server refuse. */
const triggerGate409 = async (blocking = BLOCKERS) => {
  mockMerge.mockRejectedValueOnce({
    detail: 'PROOF9 merge gate: 1 requirement(s) block this merge',
    status_code: 409,
    blocking_requirements: blocking,
  });
  fireEvent.click(screen.getByRole('button', { name: /^merge$/i }));
  await waitFor(() => expect(screen.getByRole('dialog')).toBeInTheDocument());
};

describe('PRStatusPanel — merge gate override', () => {
  beforeEach(() => jest.clearAllMocks());

  it('lets the merge be attempted even with workspace-wide open requirements', () => {
    // The server scopes the gate to the PR's files; this panel cannot.
    // Disabling here blocked PRs the server would have merged and pushed the
    // user into an audited override for a bypass that never happened (#1247).
    setupSWRMock(basePRStatus, proofStatusWithOpenReqs);
    render(<PRStatusPanel {...defaultProps} />);

    expect(screen.getByRole('button', { name: /^merge$/i })).toBeEnabled();
  });

  it('offers no override until the server actually refuses', () => {
    setupSWRMock(basePRStatus, proofStatusWithOpenReqs);
    render(<PRStatusPanel {...defaultProps} />);

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /override and merge/i })).not.toBeInTheDocument();
  });

  it('lists the requirements the SERVER named, not the panel\'s own list', async () => {
    // The gate also blocks tamper-detected SATISFIED requirements, which
    // /proof/status never reports as open. Rendering the panel's list would
    // show the wrong set — or nothing at all.
    setupSWRMock(basePRStatus, cleanProofStatus);
    render(<PRStatusPanel {...defaultProps} />);

    await triggerGate409([{ id: 'REQ-TAMPER', title: 'evidence no longer verifies' }]);

    expect(screen.getByText('REQ-TAMPER')).toBeInTheDocument();
    expect(screen.getByText(/evidence no longer verifies/)).toBeInTheDocument();
  });

  it('will not submit without a reason', async () => {
    setupSWRMock(basePRStatus, proofStatusWithOpenReqs);
    render(<PRStatusPanel {...defaultProps} />);
    await triggerGate409();

    expect(screen.getByRole('button', { name: /override and merge/i })).toBeDisabled();
    expect(mockMerge).toHaveBeenCalledTimes(1); // the blocked attempt only
  });

  it('sends override and reason once a reason is given', async () => {
    setupSWRMock(basePRStatus, proofStatusWithOpenReqs);
    render(<PRStatusPanel {...defaultProps} />);
    await triggerGate409();
    mockMerge.mockResolvedValueOnce({ merged: true } as never);

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

  it('rejects a whitespace-only reason', async () => {
    setupSWRMock(basePRStatus, proofStatusWithOpenReqs);
    render(<PRStatusPanel {...defaultProps} />);
    await triggerGate409();

    fireEvent.change(screen.getByLabelText(/reason/i), { target: { value: '   ' } });

    expect(screen.getByRole('button', { name: /override and merge/i })).toBeDisabled();
    expect(mockMerge).toHaveBeenCalledTimes(1); // the blocked attempt only
  });

  it('keeps a failed override visible in the dialog', async () => {
    // A non-superuser reaches this point: require_scope(SCOPE_ADMIN) 403s.
    setupSWRMock(basePRStatus, proofStatusWithOpenReqs);
    render(<PRStatusPanel {...defaultProps} />);
    await triggerGate409();
    mockMerge.mockRejectedValueOnce({ detail: 'Forbidden: admin scope required', status_code: 403 });

    fireEvent.change(screen.getByLabelText(/reason/i), { target: { value: 'because' } });
    fireEvent.click(screen.getByRole('button', { name: /override and merge/i }));

    await waitFor(() => {
      expect(screen.getByText(/admin scope required/i)).toBeInTheDocument();
    });
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('treats a GitHub 409 as a merge error, not a gate block', async () => {
    // GitHub returns 409 for its own conflicts (head branch modified, merge
    // conflict) and pr_v2 propagates upstream statuses verbatim. Keying the
    // override on the status code alone offered a bypass for a conflict no
    // override can clear, with an empty blocker list, hiding the real error.
    // The PROOF9 409 is the one that names what it blocks.
    mockMerge.mockRejectedValueOnce({
      detail: 'GitHub API error: Head branch was modified. Review and try the merge again.',
      status_code: 409,
    });
    setupSWRMock(basePRStatus, cleanProofStatus);
    render(<PRStatusPanel {...defaultProps} />);

    fireEvent.click(screen.getByRole('button', { name: /^merge$/i }));

    await waitFor(() =>
      expect(screen.getByText(/head branch was modified/i)).toBeInTheDocument()
    );
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('treats a 409 with an empty blocker list as a merge error too', async () => {
    mockMerge.mockRejectedValueOnce({
      detail: 'Some other conflict',
      status_code: 409,
      blocking_requirements: [],
    });
    setupSWRMock(basePRStatus, cleanProofStatus);
    render(<PRStatusPanel {...defaultProps} />);

    fireEvent.click(screen.getByRole('button', { name: /^merge$/i }));

    await waitFor(() => expect(screen.getByText(/some other conflict/i)).toBeInTheDocument());
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
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
