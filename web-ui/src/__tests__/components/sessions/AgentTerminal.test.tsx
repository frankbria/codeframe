/**
 * Tests for AgentTerminal's stream-ticket WS URL construction (issue #745).
 *
 * The xterm mounting effect is not under test (jsdom can't drive a real
 * terminal); @xterm/* are mocked to inert stubs so the component renders.
 */
import { render, waitFor } from '@testing-library/react';
import { AgentTerminal } from '@/components/sessions/AgentTerminal';
import { fetchStreamTicket } from '@/lib/api';
import { useTerminalSocket } from '@/hooks/useTerminalSocket';

jest.mock('@/lib/api', () => ({
  fetchStreamTicket: jest.fn(),
}));

jest.mock('@/hooks/useTerminalSocket', () => ({
  useTerminalSocket: jest.fn(() => ({
    status: 'connecting',
    sendInput: jest.fn(),
    sendResize: jest.fn(),
  })),
}));

jest.mock('@xterm/xterm', () => ({
  Terminal: jest.fn(() => ({
    loadAddon: jest.fn(),
    open: jest.fn(),
    onData: jest.fn(() => ({ dispose: jest.fn() })),
    dispose: jest.fn(),
    write: jest.fn(),
    cols: 80,
    rows: 24,
  })),
}));

jest.mock('@xterm/addon-fit', () => ({
  FitAddon: jest.fn(() => ({ fit: jest.fn() })),
}));

const mockFetchStreamTicket = fetchStreamTicket as jest.MockedFunction<typeof fetchStreamTicket>;
const mockUseTerminalSocket = useTerminalSocket as jest.MockedFunction<typeof useTerminalSocket>;

beforeAll(() => {
  global.ResizeObserver = jest.fn(() => ({
    observe: jest.fn(),
    unobserve: jest.fn(),
    disconnect: jest.fn(),
  })) as unknown as typeof ResizeObserver;
});

beforeEach(() => {
  jest.clearAllMocks();
});

function lastSocketUrl(): string | null {
  const calls = mockUseTerminalSocket.mock.calls;
  return calls[calls.length - 1][0].url;
}

describe('AgentTerminal stream-ticket URL (issue #745)', () => {
  it('starts with a null URL while the ticket fetch is in flight', () => {
    mockFetchStreamTicket.mockReturnValue(new Promise(() => {}));
    render(<AgentTerminal sessionId="sess-1" />);
    expect(lastSocketUrl()).toBeNull();
  });

  it('passes a ?ticket= URL (never ?token=) once the ticket resolves', async () => {
    mockFetchStreamTicket.mockResolvedValue('tick-abc');
    render(<AgentTerminal sessionId="sess-1" />);

    await waitFor(() =>
      expect(lastSocketUrl()).toBe('ws://localhost:8000/ws/sessions/sess-1/terminal?ticket=tick-abc')
    );
    expect(lastSocketUrl()).not.toContain('token=');
  });

  it('URL-encodes the ticket', async () => {
    mockFetchStreamTicket.mockResolvedValue('t&?=x');
    render(<AgentTerminal sessionId="sess-1" />);

    await waitFor(() =>
      expect(lastSocketUrl()).toBe(
        `ws://localhost:8000/ws/sessions/sess-1/terminal?ticket=${encodeURIComponent('t&?=x')}`
      )
    );
  });

  it('falls back to a bare URL (no ticket param) when the fetch resolves null', async () => {
    mockFetchStreamTicket.mockResolvedValue(null);
    render(<AgentTerminal sessionId="sess-1" />);

    await waitFor(() =>
      expect(lastSocketUrl()).toBe('ws://localhost:8000/ws/sessions/sess-1/terminal')
    );
  });

  it('fetches a fresh ticket when sessionId changes', async () => {
    mockFetchStreamTicket.mockResolvedValueOnce('tick-1').mockResolvedValueOnce('tick-2');
    const { rerender } = render(<AgentTerminal sessionId="sess-1" />);
    await waitFor(() => expect(lastSocketUrl()).toContain('tick-1'));

    rerender(<AgentTerminal sessionId="sess-2" />);
    await waitFor(() =>
      expect(lastSocketUrl()).toBe('ws://localhost:8000/ws/sessions/sess-2/terminal?ticket=tick-2')
    );
    expect(mockFetchStreamTicket).toHaveBeenCalledTimes(2);
  });
});
