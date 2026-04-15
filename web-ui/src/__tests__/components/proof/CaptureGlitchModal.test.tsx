import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { CaptureGlitchModal } from '@/components/proof/CaptureGlitchModal';
import { proofApi } from '@/lib/api';
import type { ProofRequirement } from '@/types';

// ── Mocks ────────────────────────────────────────────────────────────────

jest.mock('@/lib/api', () => ({
  proofApi: {
    capture: jest.fn(),
  },
}));

const mockCapture = proofApi.capture as jest.MockedFunction<typeof proofApi.capture>;

// ── Helpers ───────────────────────────────────────────────────────────────

const WORKSPACE = '/home/user/project';

const DEFAULT_PROPS = {
  open: true,
  workspacePath: WORKSPACE,
  onClose: jest.fn(),
  onSuccess: jest.fn(),
};

const MOCK_REQ: ProofRequirement = {
  id: 'REQ-001',
  title: 'Test glitch',
  description: 'Something broke in production',
  severity: 'high',
  source: 'production',
  status: 'open',
  glitch_type: null,
  obligations: [],
  evidence_rules: [],
  waiver: null,
  created_at: '2026-04-09T00:00:00Z',
  satisfied_at: null,
  created_by: 'human',
  source_issue: null,
  related_reqs: [],
};

function setup(props = DEFAULT_PROPS) {
  return render(<CaptureGlitchModal {...props} />);
}

// ── Tests ────────────────────────────────────────────────────────────────

describe('CaptureGlitchModal', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('rendering', () => {
    it('renders slide-over panel with title and description when open', () => {
      setup();
      expect(screen.getByRole('heading', { name: 'Capture Glitch' })).toBeInTheDocument();
      expect(screen.getByText(/Convert a production failure/i)).toBeInTheDocument();
    });

    it('renders all form fields', () => {
      setup();
      expect(screen.getByLabelText(/Description/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/Where was it found/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/Scope/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/Severity/i)).toBeInTheDocument();
    });

    it('does not render an expiry date field (expiry is set at waiver time)', () => {
      setup();
      expect(screen.queryByLabelText(/Expiry/i)).not.toBeInTheDocument();
    });

    it('renders all 9 gate checkboxes', () => {
      setup();
      const gates = ['unit', 'contract', 'e2e', 'visual', 'a11y', 'perf', 'sec', 'demo', 'manual'];
      for (const gate of gates) {
        expect(screen.getByRole('checkbox', { name: gate })).toBeInTheDocument();
      }
    });

    it('renders Cancel and Capture Glitch buttons', () => {
      setup();
      expect(screen.getByRole('button', { name: /Cancel/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /Capture Glitch/i })).toBeInTheDocument();
    });
  });

  describe('validation', () => {
    it('shows error when description is empty on submit', async () => {
      setup();
      fireEvent.click(screen.getByRole('checkbox', { name: 'unit' }));
      fireEvent.click(screen.getByRole('button', { name: /Capture Glitch/i }));
      await waitFor(() => {
        expect(screen.getByText(/Description is required/i)).toBeInTheDocument();
      });
      expect(mockCapture).not.toHaveBeenCalled();
    });

    it('shows error when no gates selected on submit', async () => {
      setup();
      fireEvent.change(screen.getByLabelText(/Description/i), {
        target: { value: 'Something broke' },
      });
      fireEvent.click(screen.getByRole('button', { name: /Capture Glitch/i }));
      await waitFor(() => {
        expect(screen.getByText(/Select at least one gate/i)).toBeInTheDocument();
      });
      expect(mockCapture).not.toHaveBeenCalled();
    });
  });

  describe('submission', () => {
    it('appends selected gates to description and calls onSuccess', async () => {
      mockCapture.mockResolvedValue(MOCK_REQ);
      setup();

      fireEvent.change(screen.getByLabelText(/Description/i), {
        target: { value: 'Something broke in production' },
      });
      fireEvent.click(screen.getByRole('checkbox', { name: 'unit' }));
      fireEvent.click(screen.getByRole('checkbox', { name: 'sec' }));
      fireEvent.click(screen.getByRole('button', { name: /Capture Glitch/i }));

      await waitFor(() => {
        expect(mockCapture).toHaveBeenCalledWith(
          WORKSPACE,
          expect.objectContaining({
            title: 'Something broke in production',
            description: expect.stringMatching(
              /^Something broke in production\n\nRequired gates: (unit, sec|sec, unit)$/
            ),
            severity: 'high',
            source: 'production',
            created_by: 'human',
          })
        );
      });
      await waitFor(() => {
        expect(DEFAULT_PROPS.onSuccess).toHaveBeenCalledWith(MOCK_REQ);
      });
    });

    it('truncates long description to 80 chars for title', async () => {
      mockCapture.mockResolvedValue(MOCK_REQ);
      setup();

      const longDesc = 'A'.repeat(100);
      fireEvent.change(screen.getByLabelText(/Description/i), {
        target: { value: longDesc },
      });
      fireEvent.click(screen.getByRole('checkbox', { name: 'sec' }));
      fireEvent.click(screen.getByRole('button', { name: /Capture Glitch/i }));

      await waitFor(() => {
        expect(mockCapture).toHaveBeenCalledWith(
          WORKSPACE,
          expect.objectContaining({ title: 'A'.repeat(80) })
        );
      });
    });

    it('surfaces backend error detail from axios response on failure', async () => {
      const axiosError = { response: { data: { detail: 'Workspace not found' } } };
      mockCapture.mockRejectedValue(axiosError);
      setup();

      fireEvent.change(screen.getByLabelText(/Description/i), {
        target: { value: 'Something broke' },
      });
      fireEvent.click(screen.getByRole('checkbox', { name: 'demo' }));
      fireEvent.click(screen.getByRole('button', { name: /Capture Glitch/i }));

      await waitFor(() => {
        expect(screen.getByText('Workspace not found')).toBeInTheDocument();
      });
      expect(DEFAULT_PROPS.onSuccess).not.toHaveBeenCalled();
    });

    it('shows fallback error message when axios error has no detail', async () => {
      mockCapture.mockRejectedValue(new Error('Network error'));
      setup();

      fireEvent.change(screen.getByLabelText(/Description/i), {
        target: { value: 'Something broke' },
      });
      fireEvent.click(screen.getByRole('checkbox', { name: 'demo' }));
      fireEvent.click(screen.getByRole('button', { name: /Capture Glitch/i }));

      await waitFor(() => {
        expect(screen.getByText(/Failed to capture glitch/i)).toBeInTheDocument();
      });
    });

    it('shows submitting state while in-flight', async () => {
      let resolve!: (v: ProofRequirement) => void;
      mockCapture.mockReturnValue(new Promise((r) => { resolve = r; }));
      setup();

      fireEvent.change(screen.getByLabelText(/Description/i), {
        target: { value: 'Something broke' },
      });
      fireEvent.click(screen.getByRole('checkbox', { name: 'manual' }));
      fireEvent.click(screen.getByRole('button', { name: /Capture Glitch/i }));

      await waitFor(() => {
        expect(screen.getByText(/Capturing…/i)).toBeInTheDocument();
      });
      resolve(MOCK_REQ);
    });
  });

  describe('cancel', () => {
    it('calls onClose when Cancel is clicked', () => {
      setup();
      fireEvent.click(screen.getByRole('button', { name: /Cancel/i }));
      expect(DEFAULT_PROPS.onClose).toHaveBeenCalled();
    });

    it('calls onClose when the × button is clicked', () => {
      setup();
      fireEvent.click(screen.getByRole('button', { name: /Close/i }));
      expect(DEFAULT_PROPS.onClose).toHaveBeenCalled();
    });
  });

  describe('state reset on reopen', () => {
    it('clears form state when modal is reopened', () => {
      const { rerender } = setup({ ...DEFAULT_PROPS, open: false });
      rerender(<CaptureGlitchModal {...DEFAULT_PROPS} open={true} />);
      expect((screen.getByLabelText(/Description/i) as HTMLTextAreaElement).value).toBe('');
    });
  });

  describe('pre-population from PR', () => {
    const PR_PROPS = {
      ...DEFAULT_PROPS,
      prNumber: 42,
      prTitle: 'Fix login timeout',
      prUrl: 'https://github.com/owner/repo/pull/42',
      initialScope: 'src/auth.py\nsrc/utils.py',
    };

    it('pre-fills description with PR reference when prNumber is provided', () => {
      setup(PR_PROPS);
      const textarea = screen.getByLabelText(/Description/i) as HTMLTextAreaElement;
      expect(textarea.value).toBe('Reported from PR #42: Fix login timeout');
    });

    it('pre-fills scope with initialScope', () => {
      setup(PR_PROPS);
      const textarea = screen.getByLabelText(/Scope/i) as HTMLTextAreaElement;
      expect(textarea.value).toBe('src/auth.py\nsrc/utils.py');
    });

    it('includes source_issue in submission payload', async () => {
      mockCapture.mockResolvedValue(MOCK_REQ);
      setup(PR_PROPS);

      // Fill required fields
      fireEvent.click(screen.getByRole('checkbox', { name: 'unit' }));
      fireEvent.click(screen.getByRole('button', { name: /Capture Glitch/i }));

      await waitFor(() => {
        expect(mockCapture).toHaveBeenCalledWith(
          WORKSPACE,
          expect.objectContaining({
            source_issue: 'https://github.com/owner/repo/pull/42',
          })
        );
      });
    });

    it('does not include source_issue when prUrl is not provided', async () => {
      mockCapture.mockResolvedValue(MOCK_REQ);
      setup();

      fireEvent.change(screen.getByLabelText(/Description/i), {
        target: { value: 'Something broke' },
      });
      fireEvent.click(screen.getByRole('checkbox', { name: 'unit' }));
      fireEvent.click(screen.getByRole('button', { name: /Capture Glitch/i }));

      await waitFor(() => {
        const callArgs = mockCapture.mock.calls[0][1];
        expect(callArgs.source_issue).toBeUndefined();
      });
    });
  });
});
