/**
 * Tests for AgentTerminal's stream-ticket WS URL construction (issue #745).
 *
 * useTerminalSocket is mocked entirely, so these tests capture the `buildUrl`
 * function AgentTerminal passes it and invoke it directly to assert the
 * resolved URL — mirroring how useTerminalSocket itself calls it fresh on
 * every (re)connect attempt.
 *
 * The xterm mounting effect is not under test (jsdom can't drive a real
 * terminal); @xterm/* are mocked to inert stubs so the component renders.
 */
import { render } from '@testing-library/react';
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

function lastOptions() {
  const calls = mockUseTerminalSocket.mock.calls;
  return calls[calls.length - 1][0];
}

function lastBuildUrl(): () => Promise<string | null> {
  return lastOptions().buildUrl;
}

describe('AgentTerminal stream-ticket buildUrl (issue #745)', () => {
  it('passes enabled=true and connectionKey=sessionId', () => {
    mockFetchStreamTicket.mockResolvedValue('tick-abc');
    render(<AgentTerminal sessionId="sess-1" />);

    expect(lastOptions().enabled).toBe(true);
    expect(lastOptions().connectionKey).toBe('sess-1');
  });

  it('buildUrl resolves a ?ticket= URL (never ?token=)', async () => {
    mockFetchStreamTicket.mockResolvedValue('tick-abc');
    render(<AgentTerminal sessionId="sess-1" />);

    const url = await lastBuildUrl()();
    expect(url).toBe('ws://localhost:8000/ws/sessions/sess-1/terminal?ticket=tick-abc');
    expect(url).not.toContain('token=');
  });

  it('buildUrl URL-encodes the ticket', async () => {
    mockFetchStreamTicket.mockResolvedValue('t&?=x');
    render(<AgentTerminal sessionId="sess-1" />);

    const url = await lastBuildUrl()();
    expect(url).toBe(
      `ws://localhost:8000/ws/sessions/sess-1/terminal?ticket=${encodeURIComponent('t&?=x')}`
    );
  });

  it('buildUrl falls back to a bare URL (no ticket param) when the ticket fetch resolves null', async () => {
    mockFetchStreamTicket.mockResolvedValue(null);
    render(<AgentTerminal sessionId="sess-1" />);

    const url = await lastBuildUrl()();
    expect(url).toBe('ws://localhost:8000/ws/sessions/sess-1/terminal');
  });

  it('buildUrl mints a fresh ticket on every invocation (single-use tickets)', async () => {
    mockFetchStreamTicket.mockResolvedValueOnce('tick-1').mockResolvedValueOnce('tick-2');
    render(<AgentTerminal sessionId="sess-1" />);
    const buildUrl = lastBuildUrl();

    await expect(buildUrl()).resolves.toContain('tick-1');
    await expect(buildUrl()).resolves.toContain('tick-2');
    expect(mockFetchStreamTicket).toHaveBeenCalledTimes(2);
  });

  it('fetches a fresh ticket for a fresh buildUrl when sessionId changes', async () => {
    mockFetchStreamTicket.mockResolvedValueOnce('tick-1').mockResolvedValueOnce('tick-2');
    const { rerender } = render(<AgentTerminal sessionId="sess-1" />);
    await expect(lastBuildUrl()()).resolves.toBe(
      'ws://localhost:8000/ws/sessions/sess-1/terminal?ticket=tick-1'
    );

    rerender(<AgentTerminal sessionId="sess-2" />);
    expect(lastOptions().connectionKey).toBe('sess-2');
    await expect(lastBuildUrl()()).resolves.toBe(
      'ws://localhost:8000/ws/sessions/sess-2/terminal?ticket=tick-2'
    );
    expect(mockFetchStreamTicket).toHaveBeenCalledTimes(2);
  });
});
