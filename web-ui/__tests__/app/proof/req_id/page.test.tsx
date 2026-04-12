import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import ProofDetailPage from '@/app/proof/[req_id]/page';
import { localStorageMock } from '../../../utils/test-helpers';

jest.mock('@/lib/api', () => ({
  proofApi: {
    getRequirement: jest.fn(),
    getEvidence: jest.fn(),
    getRunDetail: jest.fn(),
    waive: jest.fn(),
  },
}));

jest.mock('react-markdown', () => ({
  __esModule: true,
  default: ({ children }: { children: string }) => <p data-testid="markdown">{children}</p>,
}));

jest.mock('@/lib/workspace-storage', () => ({
  getSelectedWorkspacePath: jest.fn(() => '/test/workspace'),
}));

jest.mock('next/navigation', () => ({
  useParams: jest.fn(() => ({ req_id: 'REQ-001' })),
  useRouter: jest.fn(() => ({ push: jest.fn() })),
  usePathname: jest.fn(() => '/proof/REQ-001'),
  useSearchParams: jest.fn(() => new URLSearchParams()),
}));

jest.mock('swr', () => ({ __esModule: true, default: jest.fn() }));

import useSWR from 'swr';
import { proofApi } from '@/lib/api';

const mockUseSWR = useSWR as jest.MockedFunction<typeof useSWR>;
const mockWaive = proofApi.waive as jest.MockedFunction<typeof proofApi.waive>;

const baseReq = {
  id: 'REQ-001',
  title: 'Login must work with MFA',
  description: 'Ensure MFA flow is tested',
  severity: 'high',
  status: 'open',
  glitch_type: 'regression',
  obligations: [],
  evidence_rules: [],
  waiver: null,
  created_at: '2026-01-15T10:00:00Z',
  satisfied_at: null,
  created_by: 'frank',
  source_issue: null,
  related_reqs: [],
  source: 'manual',
  scope: null,
};

const waivedReq = {
  ...baseReq,
  status: 'waived',
  waiver: {
    reason: 'MFA not in scope for this sprint',
    expires: '2026-06-01',
    manual_checklist: [],
    approved_by: 'alice',
    waived_at: '2026-03-10T09:00:00Z',
  },
};

const mockEvidenceResponse = [];

describe('ProofDetailPage', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    localStorageMock.clear();
  });

  const setupSWR = (req: typeof baseReq, evidence: unknown[] = []) => {
    mockUseSWR.mockImplementation((key: any) => {
      if (typeof key === 'string' && key.includes('/runs/') && key.includes('/evidence')) {
        // Run detail endpoint
        return { data: { evidence: [] }, error: undefined, isLoading: false, mutate: jest.fn() } as any;
      }
      if (typeof key === 'string' && key.includes('/evidence')) {
        return { data: evidence, error: undefined, isLoading: false, mutate: jest.fn() } as any;
      }
      return { data: req, error: undefined, isLoading: false, mutate: jest.fn() } as any;
    });
  };

  describe('description rendering', () => {
    it('renders description via ReactMarkdown', async () => {
      setupSWR(baseReq);
      render(<ProofDetailPage />);
      await waitFor(() => {
        expect(screen.getByTestId('markdown')).toBeInTheDocument();
        expect(screen.getByTestId('markdown')).toHaveTextContent('Ensure MFA flow is tested');
      });
    });
  });

  describe('where found / scope', () => {
    it('shows "Where found" when scope has non-empty fields', async () => {
      const reqWithScope = {
        ...baseReq,
        scope: { routes: ['/login'], components: ['MFAForm'], apis: [], files: [], tags: [] },
      };
      setupSWR(reqWithScope as any);
      render(<ProofDetailPage />);
      await waitFor(() => {
        expect(screen.getByText(/where found:/i)).toBeInTheDocument();
        expect(screen.getByText(/\/login/i)).toBeInTheDocument();
      });
    });

    it('does not show "Where found" when scope is null', async () => {
      setupSWR(baseReq);
      render(<ProofDetailPage />);
      await waitFor(() => screen.getByText('Login must work with MFA'));
      expect(screen.queryByText(/where found:/i)).not.toBeInTheDocument();
    });
  });

  describe('obligations with latest run', () => {
    it('shows Latest Run column header when obligations exist', async () => {
      const reqWithObs = {
        ...baseReq,
        obligations: [{ gate: 'unit', status: 'pending' }],
      };
      setupSWR(reqWithObs as any);
      render(<ProofDetailPage />);
      await waitFor(() => {
        expect(screen.getByText('Latest Run')).toBeInTheDocument();
      });
    });

    it('reflects latest gate run result in obligation status', async () => {
      const reqWithObs = {
        ...baseReq,
        obligations: [{ gate: 'unit', status: 'pending' }],
      };
      const evidence = [
        { req_id: 'REQ-001', gate: 'unit', satisfied: true, run_id: 'run-abc', artifact_path: '', artifact_checksum: '', timestamp: '2026-01-15T12:00:00Z' },
      ];
      setupSWR(reqWithObs as any, evidence);
      render(<ProofDetailPage />);
      await waitFor(() => {
        // Obligation status should show 'satisfied' (derived from latest run, not ob.status)
        expect(screen.getByText('satisfied')).toBeInTheDocument();
        // run-abc appears in obligations Latest Run column AND evidence history — both tables should show it
        expect(screen.getAllByText('run-abc').length).toBeGreaterThanOrEqual(2);
      });
    });

    it('shows — for Latest Run when no evidence exists for that gate', async () => {
      const reqWithObs = {
        ...baseReq,
        obligations: [{ gate: 'sec', status: 'pending' }],
      };
      setupSWR(reqWithObs as any, []);
      render(<ProofDetailPage />);
      await waitFor(() => {
        expect(screen.getAllByText('—').length).toBeGreaterThan(0);
      });
    });
  });

  describe('evidence empty state CTA', () => {
    it('renders "Run Gates" link when there is no evidence', async () => {
      setupSWR(baseReq, []);
      render(<ProofDetailPage />);
      await waitFor(() => {
        expect(screen.getByText(/no gate runs yet/i)).toBeInTheDocument();
        expect(screen.getByRole('link', { name: /run gates/i })).toBeInTheDocument();
      });
    });

    it('links to /review from the empty state CTA', async () => {
      setupSWR(baseReq, []);
      render(<ProofDetailPage />);
      await waitFor(() => {
        const link = screen.getByRole('link', { name: /run gates/i });
        expect(link).toHaveAttribute('href', '/review');
      });
    });
  });

  describe('waiver audit trail', () => {
    it('shows waiver reason in the waiver section', async () => {
      setupSWR(waivedReq as any);
      render(<ProofDetailPage />);

      await waitFor(() => {
        expect(screen.getByText('MFA not in scope for this sprint')).toBeInTheDocument();
      });
    });

    it('shows approved_by in the waiver section', async () => {
      setupSWR(waivedReq as any);
      render(<ProofDetailPage />);

      await waitFor(() => {
        expect(screen.getByText(/alice/i)).toBeInTheDocument();
      });
    });

    it('shows waived_at timestamp when present', async () => {
      setupSWR(waivedReq as any);
      render(<ProofDetailPage />);

      await waitFor(() => {
        // The timestamp is formatted via toLocaleString or similar
        expect(screen.getByText(/waived:/i)).toBeInTheDocument();
      });
    });

    it('does not show waived_at section when absent', async () => {
      const reqWithoutTimestamp = {
        ...waivedReq,
        waiver: { ...waivedReq.waiver, waived_at: undefined },
      };
      setupSWR(reqWithoutTimestamp as any);
      render(<ProofDetailPage />);

      await waitFor(() => screen.getByText('MFA not in scope for this sprint'));
      expect(screen.queryByText(/waived:/i)).not.toBeInTheDocument();
    });

    it('shows "No waiver on file" when requirement is open', async () => {
      setupSWR(baseReq);
      render(<ProofDetailPage />);

      await waitFor(() => {
        expect(screen.getByText(/no waiver on file/i)).toBeInTheDocument();
      });
    });
  });

  describe('WaiveDialog — 2-step confirmation flow', () => {
    it('opens form step when Waive button is clicked', async () => {
      setupSWR(baseReq);
      render(<ProofDetailPage />);

      await waitFor(() => screen.getByRole('button', { name: /waive this requirement/i }));
      fireEvent.click(screen.getByRole('button', { name: /waive this requirement/i }));

      await waitFor(() => {
        expect(screen.getByLabelText(/reason/i)).toBeInTheDocument();
        expect(screen.getByRole('button', { name: /continue/i })).toBeInTheDocument();
      });
    });

    it('shows confirmation warning after filling reason', async () => {
      setupSWR(baseReq);
      render(<ProofDetailPage />);

      await waitFor(() => screen.getByRole('button', { name: /waive this requirement/i }));
      fireEvent.click(screen.getByRole('button', { name: /waive this requirement/i }));

      await waitFor(() => screen.getByLabelText(/reason/i));
      fireEvent.change(screen.getByLabelText(/reason/i), {
        target: { value: 'Deferred to Q2' },
      });
      fireEvent.click(screen.getByRole('button', { name: /continue/i }));

      await waitFor(() => {
        expect(screen.getByText(/marked satisfied without evidence/i)).toBeInTheDocument();
        expect(screen.getByRole('button', { name: /confirm waive/i })).toBeInTheDocument();
      });
    });

    it('submits waiver from confirmation step', async () => {
      const mutate = jest.fn();
      mockUseSWR.mockImplementation((key: any) => {
        if (typeof key === 'string' && key.includes('/evidence')) {
          return { data: [], error: undefined, isLoading: false, mutate: jest.fn() } as any;
        }
        return { data: baseReq, error: undefined, isLoading: false, mutate } as any;
      });
      mockWaive.mockResolvedValueOnce(undefined as any);

      render(<ProofDetailPage />);
      await waitFor(() => screen.getByRole('button', { name: /waive this requirement/i }));
      fireEvent.click(screen.getByRole('button', { name: /waive this requirement/i }));

      await waitFor(() => screen.getByLabelText(/reason/i));
      fireEvent.change(screen.getByLabelText(/reason/i), {
        target: { value: 'Accepted risk' },
      });
      fireEvent.click(screen.getByRole('button', { name: /continue/i }));

      await waitFor(() => screen.getByRole('button', { name: /confirm waive/i }));
      fireEvent.click(screen.getByRole('button', { name: /confirm waive/i }));

      await waitFor(() => {
        expect(mockWaive).toHaveBeenCalledWith('/test/workspace', 'REQ-001', {
          reason: 'Accepted risk',
          expires: null,
          manual_checklist: [],
          approved_by: '',
        });
        expect(mutate).toHaveBeenCalled();
      });
    });
  });
});
