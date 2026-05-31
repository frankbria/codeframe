import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { StressTestModal } from '@/components/prd/StressTestModal';
import { useStressTestStream } from '@/hooks/useStressTestStream';
import type { UseStressTestStreamReturn } from '@/hooks/useStressTestStream';
import { prdApi } from '@/lib/api';
import type { StressTestAmbiguity } from '@/types';

// ResizeObserver is not available in jsdom
global.ResizeObserver = jest.fn().mockImplementation(() => ({
  observe: jest.fn(),
  unobserve: jest.fn(),
  disconnect: jest.fn(),
}));

// Radix ScrollArea Viewport hides children in jsdom — render children directly
jest.mock('@/components/ui/scroll-area', () => ({
  ScrollArea: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  ScrollBar: () => null,
}));

jest.mock('@/hooks/useStressTestStream');
jest.mock('@/lib/api', () => ({
  prdApi: { refineStressTest: jest.fn() },
}));
jest.mock('sonner', () => ({
  toast: { success: jest.fn(), error: jest.fn() },
}));

const mockUseStressTestStream = useStressTestStream as jest.MockedFunction<
  typeof useStressTestStream
>;
const mockRefine = prdApi.refineStressTest as jest.MockedFunction<
  typeof prdApi.refineStressTest
>;

const WORKSPACE = '/home/user/project';
const PRD_ID = 'prd-1';

function ambiguity(
  overrides: Partial<StressTestAmbiguity> = {}
): StressTestAmbiguity {
  return {
    id: 'amb-1',
    label: 'AUTH SCOPE',
    source_node_title: 'User Authentication',
    questions: ['Email/password or OAuth?'],
    recommendation: 'Add an auth section',
    severity: 'blocking',
    resolved_answer: null,
    ...overrides,
  };
}

function mockHook(overrides: Partial<UseStressTestStreamReturn> = {}) {
  const value: UseStressTestStreamReturn = {
    status: 'idle',
    lines: [],
    result: null,
    error: null,
    start: jest.fn(),
    reset: jest.fn(),
    ...overrides,
  };
  mockUseStressTestStream.mockReturnValue(value);
  return value;
}

function renderModal(props: Partial<React.ComponentProps<typeof StressTestModal>> = {}) {
  return render(
    <StressTestModal
      open
      onOpenChange={jest.fn()}
      workspacePath={WORKSPACE}
      prdId={PRD_ID}
      {...props}
    />
  );
}

beforeEach(() => {
  jest.clearAllMocks();
});

describe('StressTestModal', () => {
  it('calls start() when opened', () => {
    const hook = mockHook({ status: 'streaming' });
    renderModal();
    expect(hook.start).toHaveBeenCalled();
  });

  it('shows the analyzing spinner while streaming', () => {
    mockHook({ status: 'streaming', lines: ['✓ Extracted 3 goals'] });
    renderModal();
    expect(screen.getByText('Analyzing PRD...')).toBeInTheDocument();
    expect(screen.getByText('✓ Extracted 3 goals')).toBeInTheDocument();
  });

  it('shows the ambiguity summary on completion', () => {
    mockHook({
      status: 'complete',
      lines: ['✓ Analysis complete — 2 ambiguities found'],
      result: {
        ambiguityCount: 2,
        ambiguities: [],
        techSpecMarkdown: '# spec',
        ambiguityReport: 'report',
      },
    });
    renderModal();
    expect(screen.getByText('Found 2 ambiguities')).toBeInTheDocument();
  });

  it('shows a well-specified message when no ambiguities are found', () => {
    mockHook({
      status: 'complete',
      result: {
        ambiguityCount: 0,
        ambiguities: [],
        techSpecMarkdown: '# spec',
        ambiguityReport: 'report',
      },
    });
    renderModal();
    expect(screen.getByText(/No ambiguities found/i)).toBeInTheDocument();
  });

  it('shows an error message and a working Retry button', async () => {
    const hook = mockHook({
      status: 'error',
      error: 'ANTHROPIC_API_KEY environment variable required.',
    });
    renderModal();

    expect(screen.getByText('Stress test failed')).toBeInTheDocument();
    expect(
      screen.getByText('ANTHROPIC_API_KEY environment variable required.')
    ).toBeInTheDocument();

    // start was called once on open; clicking Retry calls it again.
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(hook.start).toHaveBeenCalledTimes(2);
  });

  it('closes via the Close button after completion', async () => {
    const onOpenChange = jest.fn();
    mockHook({
      status: 'complete',
      result: {
        ambiguityCount: 0,
        ambiguities: [],
        techSpecMarkdown: '',
        ambiguityReport: '',
      },
    });
    renderModal({ onOpenChange });

    await userEvent.click(screen.getByRole('button', { name: 'Close' }));
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  // ── Results view (issue #562) ────────────────────────────────────────────

  it('renders an answerable card per ambiguity with question text', () => {
    mockHook({
      status: 'complete',
      result: {
        ambiguityCount: 1,
        ambiguities: [ambiguity()],
        techSpecMarkdown: '',
        ambiguityReport: '',
      },
    });
    renderModal();

    expect(screen.getByText('AUTH SCOPE')).toBeInTheDocument();
    expect(screen.getByText('Email/password or OAuth?')).toBeInTheDocument();
    expect(
      screen.getByRole('textbox', { name: /Answer for AUTH SCOPE/i })
    ).toBeInTheDocument();
    expect(screen.getByText('0 of 1 answered')).toBeInTheDocument();
  });

  it('disables Refine PRD until all blocking questions are answered', async () => {
    mockHook({
      status: 'complete',
      result: {
        ambiguityCount: 2,
        ambiguities: [
          ambiguity({ id: 'a', label: 'BLOCKER', severity: 'blocking' }),
          ambiguity({ id: 'b', label: 'OPTIONAL', severity: 'warning' }),
        ],
        techSpecMarkdown: '',
        ambiguityReport: '',
      },
    });
    renderModal();

    const refine = screen.getByRole('button', { name: /Refine PRD/i });
    expect(refine).toBeDisabled();

    // Answering only the warning leaves the blocker unanswered → still disabled.
    await userEvent.type(
      screen.getByRole('textbox', { name: /Answer for OPTIONAL/i }),
      'CSV'
    );
    expect(refine).toBeDisabled();

    // Answering the blocker enables refine.
    await userEvent.type(
      screen.getByRole('textbox', { name: /Answer for BLOCKER/i }),
      'Email/password'
    );
    expect(refine).toBeEnabled();
  });

  it('keeps Refine PRD disabled until at least one answer is given (warnings only)', async () => {
    mockHook({
      status: 'complete',
      result: {
        ambiguityCount: 1,
        ambiguities: [ambiguity({ id: 'w', label: 'OPTIONAL', severity: 'warning' })],
        techSpecMarkdown: '',
        ambiguityReport: '',
      },
    });
    renderModal();

    // No blocking questions, but nothing answered yet → still disabled (an
    // empty answers payload would be rejected by the backend).
    const refine = screen.getByRole('button', { name: /Refine PRD/i });
    expect(refine).toBeDisabled();

    await userEvent.type(
      screen.getByRole('textbox', { name: /Answer for OPTIONAL/i }),
      'CSV'
    );
    expect(refine).toBeEnabled();
  });

  it('refines the PRD and reports the new version via onRefined', async () => {
    const onRefined = jest.fn();
    const onOpenChange = jest.fn();
    const newPrd = { id: 'prd-1', version: 2, content: 'updated' };
    mockRefine.mockResolvedValue(newPrd as never);
    mockHook({
      status: 'complete',
      result: {
        ambiguityCount: 1,
        ambiguities: [ambiguity({ id: 'a', label: 'BLOCKER' })],
        techSpecMarkdown: '',
        ambiguityReport: '',
      },
    });
    renderModal({ onRefined, onOpenChange });

    await userEvent.type(
      screen.getByRole('textbox', { name: /Answer for BLOCKER/i }),
      'Email/password with JWT'
    );
    await userEvent.click(screen.getByRole('button', { name: /Refine PRD/i }));

    await waitFor(() => {
      expect(mockRefine).toHaveBeenCalledWith(PRD_ID, WORKSPACE, [
        {
          label: 'BLOCKER',
          questions: ['Email/password or OAuth?'],
          answer: 'Email/password with JWT',
        },
      ]);
    });
    expect(onRefined).toHaveBeenCalledWith(newPrd);
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });
});
