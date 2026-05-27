import React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { StressTestModal } from '@/components/prd/StressTestModal';
import { useStressTestStream } from '@/hooks/useStressTestStream';
import type { UseStressTestStreamReturn } from '@/hooks/useStressTestStream';

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

const mockUseStressTestStream = useStressTestStream as jest.MockedFunction<
  typeof useStressTestStream
>;

const WORKSPACE = '/home/user/project';

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

beforeEach(() => {
  jest.clearAllMocks();
});

describe('StressTestModal', () => {
  it('calls start() when opened', () => {
    const hook = mockHook({ status: 'streaming' });
    render(
      <StressTestModal open onOpenChange={jest.fn()} workspacePath={WORKSPACE} />
    );
    expect(hook.start).toHaveBeenCalled();
  });

  it('shows the analyzing spinner while streaming', () => {
    mockHook({ status: 'streaming', lines: ['✓ Extracted 3 goals'] });
    render(
      <StressTestModal open onOpenChange={jest.fn()} workspacePath={WORKSPACE} />
    );
    expect(screen.getByText('Analyzing PRD...')).toBeInTheDocument();
    expect(screen.getByText('✓ Extracted 3 goals')).toBeInTheDocument();
  });

  it('shows the ambiguity summary on completion', () => {
    mockHook({
      status: 'complete',
      lines: ['✓ Analysis complete — 2 ambiguities found'],
      result: {
        ambiguityCount: 2,
        techSpecMarkdown: '# spec',
        ambiguityReport: 'report',
      },
    });
    render(
      <StressTestModal open onOpenChange={jest.fn()} workspacePath={WORKSPACE} />
    );
    expect(screen.getByText('Found 2 ambiguities')).toBeInTheDocument();
  });

  it('shows a well-specified message when no ambiguities are found', () => {
    mockHook({
      status: 'complete',
      result: {
        ambiguityCount: 0,
        techSpecMarkdown: '# spec',
        ambiguityReport: 'report',
      },
    });
    render(
      <StressTestModal open onOpenChange={jest.fn()} workspacePath={WORKSPACE} />
    );
    expect(
      screen.getByText(/No ambiguities found/i)
    ).toBeInTheDocument();
  });

  it('shows an error message and a working Retry button', async () => {
    const hook = mockHook({
      status: 'error',
      error: 'ANTHROPIC_API_KEY environment variable required.',
    });
    render(
      <StressTestModal open onOpenChange={jest.fn()} workspacePath={WORKSPACE} />
    );

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
      result: { ambiguityCount: 0, techSpecMarkdown: '', ambiguityReport: '' },
    });
    render(
      <StressTestModal open onOpenChange={onOpenChange} workspacePath={WORKSPACE} />
    );

    await userEvent.click(screen.getByRole('button', { name: 'Close' }));
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });
});
