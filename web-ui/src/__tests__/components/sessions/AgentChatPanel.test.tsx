import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AgentChatPanel } from '@/components/sessions/AgentChatPanel';
import { useAgentChat } from '@/hooks/useAgentChat';
import type { AgentChatState, ChatMessage } from '@/types';

jest.mock('@/hooks/useAgentChat');

const mockUseAgentChat = useAgentChat as jest.MockedFunction<typeof useAgentChat>;

// ── Helpers ─────────────────────────────────────────────────────────────

function makeMessage(overrides: Partial<ChatMessage>): ChatMessage {
  return {
    id: Math.random().toString(36).slice(2),
    role: 'assistant',
    content: 'Hello',
    createdAt: new Date().toISOString(),
    ...overrides,
  };
}

function makeState(overrides: Partial<AgentChatState> = {}): AgentChatState {
  return {
    messages: [],
    status: 'idle',
    costUsd: 0,
    inputTokens: 0,
    outputTokens: 0,
    error: null,
    connected: true,
    ...overrides,
  };
}

const mockSendMessage = jest.fn();
const mockInterrupt = jest.fn();
const mockClearMessages = jest.fn();

function setupMock(state: AgentChatState) {
  mockUseAgentChat.mockReturnValue({
    state,
    sendMessage: mockSendMessage,
    interrupt: mockInterrupt,
    clearMessages: mockClearMessages,
  });
}

// ── Tests ────────────────────────────────────────────────────────────────

describe('AgentChatPanel', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  // ── Empty state ──────────────────────────────────────────────────────

  it('shows empty state when there are no messages', () => {
    setupMock(makeState());
    render(<AgentChatPanel sessionId="sess-1" />);
    expect(screen.getByText('Start a conversation with your agent')).toBeInTheDocument();
  });

  it('does not show empty state when messages exist', () => {
    setupMock(makeState({ messages: [makeMessage({ role: 'user', content: 'Hi' })] }));
    render(<AgentChatPanel sessionId="sess-1" />);
    expect(screen.queryByText('Start a conversation with your agent')).not.toBeInTheDocument();
    expect(screen.getByText('Hi')).toBeInTheDocument();
  });

  // ── All 7 message roles ──────────────────────────────────────────────

  it('renders user message with correct role styling', () => {
    setupMock(makeState({ messages: [makeMessage({ role: 'user', content: 'User msg' })] }));
    render(<AgentChatPanel sessionId="sess-1" />);
    expect(screen.getByText('User msg')).toBeInTheDocument();
  });

  it('renders assistant message', () => {
    setupMock(makeState({ messages: [makeMessage({ role: 'assistant', content: 'Assistant msg' })] }));
    render(<AgentChatPanel sessionId="sess-1" />);
    expect(screen.getByText('Assistant msg')).toBeInTheDocument();
  });

  it('renders tool_use card collapsed by default with tool name', () => {
    setupMock(makeState({
      messages: [makeMessage({
        role: 'tool_use',
        content: '',
        toolName: 'read_file',
        toolInput: { path: 'src/index.ts' },
      })],
    }));
    render(<AgentChatPanel sessionId="sess-1" />);
    expect(screen.getByText(/read_file/)).toBeInTheDocument();
    // JSON body should not be visible when collapsed
    expect(screen.queryByText(/"path"/)).not.toBeInTheDocument();
  });

  it('expands tool_use card when clicked', () => {
    setupMock(makeState({
      messages: [makeMessage({
        role: 'tool_use',
        content: '',
        toolName: 'read_file',
        toolInput: { path: 'src/index.ts' },
      })],
    }));
    render(<AgentChatPanel sessionId="sess-1" />);
    const toggle = screen.getByRole('button', { name: /expand/i });
    fireEvent.click(toggle);
    expect(screen.getByText(/"path"/)).toBeInTheDocument();
  });

  it('renders tool_result with first 200 chars visible', () => {
    const longContent = 'x'.repeat(300);
    setupMock(makeState({
      messages: [makeMessage({ role: 'tool_result', content: longContent })],
    }));
    render(<AgentChatPanel sessionId="sess-1" />);
    expect(screen.getByText(/^x{200}$/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /show more/i })).toBeInTheDocument();
  });

  it('expands tool_result when Show more clicked', () => {
    const longContent = 'y'.repeat(300);
    setupMock(makeState({
      messages: [makeMessage({ role: 'tool_result', content: longContent })],
    }));
    render(<AgentChatPanel sessionId="sess-1" />);
    fireEvent.click(screen.getByRole('button', { name: /show more/i }));
    expect(screen.getByText(new RegExp(`y{300}`))).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /show less/i })).toBeInTheDocument();
  });

  it('renders thinking block with content', () => {
    setupMock(makeState({
      messages: [makeMessage({ role: 'thinking', content: 'I need to check this' })],
    }));
    render(<AgentChatPanel sessionId="sess-1" />);
    expect(screen.getByText('I need to check this')).toBeInTheDocument();
  });

  it('renders system message', () => {
    setupMock(makeState({
      messages: [makeMessage({ role: 'system', content: 'Session started' })],
    }));
    render(<AgentChatPanel sessionId="sess-1" />);
    expect(screen.getByText('Session started')).toBeInTheDocument();
  });

  it('renders error card', () => {
    setupMock(makeState({
      messages: [makeMessage({ role: 'error', content: 'Something went wrong' })],
    }));
    render(<AgentChatPanel sessionId="sess-1" />);
    expect(screen.getByText('Something went wrong')).toBeInTheDocument();
  });

  // ── Streaming cursor ─────────────────────────────────────────────────

  it('shows streaming cursor on last assistant message when status is streaming', () => {
    const msgs = [makeMessage({ role: 'assistant', content: 'Typing...' })];
    setupMock(makeState({ messages: msgs, status: 'streaming' }));
    render(<AgentChatPanel sessionId="sess-1" />);
    expect(screen.getByTestId('streaming-cursor')).toBeInTheDocument();
  });

  it('does not show streaming cursor when status is idle', () => {
    const msgs = [makeMessage({ role: 'assistant', content: 'Done' })];
    setupMock(makeState({ messages: msgs, status: 'idle' }));
    render(<AgentChatPanel sessionId="sess-1" />);
    expect(screen.queryByTestId('streaming-cursor')).not.toBeInTheDocument();
  });

  // ── Input bar ────────────────────────────────────────────────────────

  it('input textarea is enabled when status is idle', () => {
    setupMock(makeState({ status: 'idle' }));
    render(<AgentChatPanel sessionId="sess-1" />);
    expect(screen.getByRole('textbox', { name: /message/i })).not.toBeDisabled();
  });

  it('input textarea is disabled while thinking', () => {
    setupMock(makeState({ status: 'thinking' }));
    render(<AgentChatPanel sessionId="sess-1" />);
    expect(screen.getByRole('textbox', { name: /message/i })).toBeDisabled();
  });

  it('input textarea is disabled while streaming', () => {
    setupMock(makeState({ status: 'streaming' }));
    render(<AgentChatPanel sessionId="sess-1" />);
    expect(screen.getByRole('textbox', { name: /message/i })).toBeDisabled();
  });

  it('calls sendMessage and clears input on Enter', async () => {
    setupMock(makeState({ status: 'idle' }));
    render(<AgentChatPanel sessionId="sess-1" />);
    const textarea = screen.getByRole('textbox', { name: /message/i });
    await userEvent.type(textarea, 'Hello agent');
    fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false });
    expect(mockSendMessage).toHaveBeenCalledWith('Hello agent');
    expect(textarea).toHaveValue('');
  });

  it('does not send on Shift+Enter', async () => {
    setupMock(makeState({ status: 'idle' }));
    render(<AgentChatPanel sessionId="sess-1" />);
    const textarea = screen.getByRole('textbox', { name: /message/i });
    await userEvent.type(textarea, 'Hello');
    fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: true });
    expect(mockSendMessage).not.toHaveBeenCalled();
  });

  it('calls sendMessage when Send button clicked', async () => {
    setupMock(makeState({ status: 'idle' }));
    render(<AgentChatPanel sessionId="sess-1" />);
    const textarea = screen.getByRole('textbox', { name: /message/i });
    await userEvent.type(textarea, 'Send this');
    fireEvent.click(screen.getByRole('button', { name: /send message/i }));
    expect(mockSendMessage).toHaveBeenCalledWith('Send this');
  });

  it('does not call sendMessage when input is empty', () => {
    setupMock(makeState({ status: 'idle' }));
    render(<AgentChatPanel sessionId="sess-1" />);
    fireEvent.click(screen.getByRole('button', { name: /send message/i }));
    expect(mockSendMessage).not.toHaveBeenCalled();
  });

  // ── Interrupt button ─────────────────────────────────────────────────

  it('shows interrupt button during thinking', () => {
    setupMock(makeState({ status: 'thinking' }));
    render(<AgentChatPanel sessionId="sess-1" />);
    expect(screen.getByRole('button', { name: /interrupt agent/i })).toBeInTheDocument();
  });

  it('shows interrupt button during streaming', () => {
    setupMock(makeState({ status: 'streaming' }));
    render(<AgentChatPanel sessionId="sess-1" />);
    expect(screen.getByRole('button', { name: /interrupt agent/i })).toBeInTheDocument();
  });

  it('hides interrupt button when idle', () => {
    setupMock(makeState({ status: 'idle' }));
    render(<AgentChatPanel sessionId="sess-1" />);
    expect(screen.queryByRole('button', { name: /interrupt agent/i })).not.toBeInTheDocument();
  });

  it('calls interrupt when interrupt button clicked', () => {
    setupMock(makeState({ status: 'thinking' }));
    render(<AgentChatPanel sessionId="sess-1" />);
    fireEvent.click(screen.getByRole('button', { name: /interrupt agent/i }));
    expect(mockInterrupt).toHaveBeenCalled();
  });

  // ── Header ───────────────────────────────────────────────────────────

  it('shows cost in header', () => {
    setupMock(makeState({ costUsd: 0.0031 }));
    render(<AgentChatPanel sessionId="sess-1" />);
    expect(screen.getByText('$0.0031')).toBeInTheDocument();
  });

  it('shows green status dot when connected and idle', () => {
    setupMock(makeState({ status: 'idle', connected: true }));
    render(<AgentChatPanel sessionId="sess-1" />);
    const dot = screen.getByRole('status', { hidden: true });
    expect(dot).toHaveClass('bg-green-500');
  });

  it('shows yellow status dot when connecting', () => {
    setupMock(makeState({ status: 'connecting', connected: false }));
    render(<AgentChatPanel sessionId="sess-1" />);
    const dot = screen.getByRole('status', { hidden: true });
    expect(dot).toHaveClass('bg-yellow-400');
  });

  it('shows red status dot when disconnected', () => {
    setupMock(makeState({ status: 'disconnected', connected: false }));
    render(<AgentChatPanel sessionId="sess-1" />);
    const dot = screen.getByRole('status', { hidden: true });
    expect(dot).toHaveClass('bg-red-500');
  });

  // ── Accessibility ────────────────────────────────────────────────────

  it('message log has role=log and aria-live=polite', () => {
    setupMock(makeState());
    render(<AgentChatPanel sessionId="sess-1" />);
    const log = screen.getByRole('log');
    expect(log).toHaveAttribute('aria-live', 'polite');
  });

  it('tool_use toggle button has aria-expanded', () => {
    setupMock(makeState({
      messages: [makeMessage({ role: 'tool_use', content: '', toolName: 'read_file', toolInput: {} })],
    }));
    render(<AgentChatPanel sessionId="sess-1" />);
    const toggle = screen.getByRole('button', { name: /expand/i });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
  });
});
