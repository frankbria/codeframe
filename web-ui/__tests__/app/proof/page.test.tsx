import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import ProofPage from '@/app/proof/page';

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
    listRequirements: jest.fn(),
    waive: jest.fn(),
  },
}));

jest.mock('@/lib/workspace-storage', () => ({
  getSelectedWorkspacePath: jest.fn(() => '/test/workspace'),
}));

jest.mock('swr', () => ({ __esModule: true, default: jest.fn() }));

import useSWR from 'swr';
import { proofApi } from '@/lib/api';

const mockUseSWR = useSWR as jest.MockedFunction<typeof useSWR>;
const mockWaive = proofApi.waive as jest.MockedFunction<typeof proofApi.waive>;

const openReq = {
  id: 'REQ-001',
  title: 'Test requirement',
  description: 'A test requirement',
  severity: 'high',
  status: 'open',
  glitch_type: 'regression',
  obligations: [],
  evidence_rules: [],
  waiver: null,
  created_at: '2026-01-01T00:00:00Z',
  satisfied_at: null,
  created_by: 'tester',
  source_issue: null,
  related_reqs: [],
  source: 'manual',
};

const waivedReq = {
  ...openReq,
  id: 'REQ-002',
  title: 'Waived requirement',
  status: 'waived',
  waiver: {
    reason: 'Not applicable for this release',
    expires: null,
    manual_checklist: [],
    approved_by: 'frank',
    waived_at: '2026-03-01T12:00:00Z',
  },
};

describe('ProofPage', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    localStorageMock.clear();
    mockUseSWR.mockReturnValue({
      data: {
        requirements: [openReq, waivedReq],
        total: 2,
        by_status: { open: 1, waived: 1, satisfied: 0 },
      },
      error: undefined,
      isLoading: false,
      mutate: jest.fn(),
    } as any);
  });

  describe('waived row visual treatment', () => {
    it('renders waived rows with muted/strikethrough styling', async () => {
      render(<ProofPage />);
      await waitFor(() => screen.getByText('Waived requirement'));

      const waivedRow = screen.getByText('Waived requirement').closest('tr');
      expect(waivedRow).toHaveClass('opacity-60');
    });

    it('does not apply muted styling to open rows', async () => {
      render(<ProofPage />);
      await waitFor(() => screen.getByText('Test requirement'));

      const openRow = screen.getByText('Test requirement').closest('tr');
      expect(openRow).not.toHaveClass('opacity-60');
    });

    it('does not show Waive button for waived requirements', async () => {
      render(<ProofPage />);
      await waitFor(() => screen.getByText('Waived requirement'));

      const buttons = screen.getAllByRole('button', { name: /waive/i });
      // Only one Waive button for the open req
      expect(buttons).toHaveLength(1);
    });
  });

  describe('WaiveDialog — 2-step confirmation flow', () => {
    it('opens the form step when Waive is clicked', async () => {
      render(<ProofPage />);
      await waitFor(() => screen.getByRole('button', { name: /^waive$/i }));

      fireEvent.click(screen.getByRole('button', { name: /^waive$/i }));

      await waitFor(() => {
        expect(screen.getByText(/waive req-001/i)).toBeInTheDocument();
        expect(screen.getByLabelText(/reason/i)).toBeInTheDocument();
        expect(screen.getByRole('button', { name: /continue/i })).toBeInTheDocument();
      });
    });

    it('shows error if Continue is clicked without a reason', async () => {
      render(<ProofPage />);
      await waitFor(() => screen.getByRole('button', { name: /^waive$/i }));
      fireEvent.click(screen.getByRole('button', { name: /^waive$/i }));

      await waitFor(() => screen.getByRole('button', { name: /continue/i }));
      fireEvent.click(screen.getByRole('button', { name: /continue/i }));

      await waitFor(() => {
        expect(screen.getByText(/reason is required/i)).toBeInTheDocument();
      });
    });

    it('advances to confirmation step when reason is provided', async () => {
      render(<ProofPage />);
      await waitFor(() => screen.getByRole('button', { name: /^waive$/i }));
      fireEvent.click(screen.getByRole('button', { name: /^waive$/i }));

      await waitFor(() => screen.getByLabelText(/reason/i));
      fireEvent.change(screen.getByLabelText(/reason/i), {
        target: { value: 'Not needed this cycle' },
      });
      fireEvent.click(screen.getByRole('button', { name: /continue/i }));

      await waitFor(() => {
        expect(screen.getByText(/marked satisfied without evidence/i)).toBeInTheDocument();
        expect(screen.getByRole('button', { name: /confirm waive/i })).toBeInTheDocument();
        expect(screen.getByRole('button', { name: /back/i })).toBeInTheDocument();
      });
    });

    it('shows the entered reason in the confirmation summary', async () => {
      render(<ProofPage />);
      await waitFor(() => screen.getByRole('button', { name: /^waive$/i }));
      fireEvent.click(screen.getByRole('button', { name: /^waive$/i }));

      await waitFor(() => screen.getByLabelText(/reason/i));
      fireEvent.change(screen.getByLabelText(/reason/i), {
        target: { value: 'Accepted risk for v1' },
      });
      fireEvent.click(screen.getByRole('button', { name: /continue/i }));

      await waitFor(() => {
        expect(screen.getByText('Accepted risk for v1')).toBeInTheDocument();
      });
    });

    it('goes back to form when Back is clicked', async () => {
      render(<ProofPage />);
      await waitFor(() => screen.getByRole('button', { name: /^waive$/i }));
      fireEvent.click(screen.getByRole('button', { name: /^waive$/i }));

      await waitFor(() => screen.getByLabelText(/reason/i));
      fireEvent.change(screen.getByLabelText(/reason/i), {
        target: { value: 'Temporary waiver' },
      });
      fireEvent.click(screen.getByRole('button', { name: /continue/i }));

      await waitFor(() => screen.getByRole('button', { name: /back/i }));
      fireEvent.click(screen.getByRole('button', { name: /back/i }));

      await waitFor(() => {
        expect(screen.getByLabelText(/reason/i)).toBeInTheDocument();
        expect(screen.getByDisplayValue('Temporary waiver')).toBeInTheDocument();
      });
    });

    it('calls proofApi.waive and closes on Confirm Waive', async () => {
      mockWaive.mockResolvedValueOnce(undefined as any);
      const mutate = jest.fn();
      mockUseSWR.mockReturnValue({
        data: {
          requirements: [openReq, waivedReq],
          total: 2,
          by_status: { open: 1, waived: 1 },
        },
        error: undefined,
        isLoading: false,
        mutate,
      } as any);

      render(<ProofPage />);
      await waitFor(() => screen.getByRole('button', { name: /^waive$/i }));
      fireEvent.click(screen.getByRole('button', { name: /^waive$/i }));

      await waitFor(() => screen.getByLabelText(/reason/i));
      fireEvent.change(screen.getByLabelText(/reason/i), {
        target: { value: 'Risk accepted' },
      });
      fireEvent.click(screen.getByRole('button', { name: /continue/i }));

      await waitFor(() => screen.getByRole('button', { name: /confirm waive/i }));
      fireEvent.click(screen.getByRole('button', { name: /confirm waive/i }));

      await waitFor(() => {
        expect(mockWaive).toHaveBeenCalledWith('/test/workspace', 'REQ-001', expect.objectContaining({
          reason: 'Risk accepted',
        }));
        expect(mutate).toHaveBeenCalled();
      });
    });
  });
});
