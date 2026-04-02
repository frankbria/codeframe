import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import ProofDetailPage from '@/app/proof/[req_id]/page';

// Mock localStorage
const localStorageMock = (() => {
  let store: Record<string, string> = {};
  return {
    getItem: (key: string) => store[key] || null,
    setItem: (key: string, value: string) => { store[key] = value; },
    removeItem: (key: string) => { delete store[key]; },
    clear: () => { store = {}; },
  };
})();
Object.defineProperty(window, 'localStorage', { value: localStorageMock });

jest.mock('@/lib/api', () => ({
  proofApi: {
    getRequirement: jest.fn(),
    getEvidence: jest.fn(),
    waive: jest.fn(),
  },
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

  const setupSWR = (req: typeof baseReq) => {
    mockUseSWR.mockImplementation((key: any) => {
      if (typeof key === 'string' && key.includes('/evidence')) {
        return { data: mockEvidenceResponse, error: undefined, isLoading: false, mutate: jest.fn() } as any;
      }
      return { data: req, error: undefined, isLoading: false, mutate: jest.fn() } as any;
    });
  };

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
        expect(mockWaive).toHaveBeenCalledWith('/test/workspace', 'REQ-001', expect.objectContaining({
          reason: 'Accepted risk',
        }));
        expect(mutate).toHaveBeenCalled();
      });
    });
  });
});
