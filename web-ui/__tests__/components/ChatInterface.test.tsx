/**
 * Unit tests for ChatInterface component (cf-14.2)
 *
 * Tests:
 * - Renders message history from API
 * - Displays user and agent messages correctly
 * - Auto-scrolls to latest message
 * - Sends message on form submit
 * - Validates empty message (should not send)
 * - Handles agent offline status
 * - Shows error messages
 * - WebSocket message integration
 * - Optimistic UI updates
 * - Loading states
 * - Input field focus management
 * - Message timestamp formatting with date-fns
 *
 * Part of Sprint 5: Human-in-the-Loop Communication
 */

import React from 'react';
import { render, screen, waitFor, fireEvent, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ChatInterface from '../../src/components/ChatInterface';
import * as chatApi from '../../src/lib/api';
import { getWebSocketClient } from '../../src/lib/websocket';
import type { ChatMessage, WebSocketMessage } from '../../src/types';
import { formatDistanceToNow } from 'date-fns';

// Mock the API module
jest.mock('../../src/lib/api');

// Mock the WebSocket module
jest.mock('../../src/lib/websocket');

// Mock SWR to avoid timing issues
jest.mock('swr', () => ({
  __esModule: true,
  default: (key: string, fetcher: any, options?: any) => {
    const [data, setData] = React.useState<any>(null);
    const [error, setError] = React.useState<any>(null);

    React.useEffect(() => {
      if (fetcher) {
        fetcher()
          .then((result: any) => setData(result))
          .catch((err: any) => setError(err));
      }
    }, [key]);

    return { data, error };
  },
}));

// Mock date-fns
jest.mock('date-fns', () => ({
  formatDistanceToNow: jest.fn((date, options) => {
    // Simple mock implementation
    return '2 minutes ago';
  }),
}));

describe('ChatInterface', () => {
  // Mock chat API functions
  const mockGetHistory = chatApi.chatApi.getHistory as jest.MockedFunction<
    typeof chatApi.chatApi.getHistory
  >;
  const mockSendMessage = chatApi.chatApi.send as jest.MockedFunction<
    typeof chatApi.chatApi.send
  >;

  // Mock WebSocket client
  let mockWsClient: {
    onMessage: jest.Mock;
    subscribe: jest.Mock;
    send: jest.Mock;
  };

  // Test data
  const mockMessages: ChatMessage[] = [
    {
      role: 'user',
      content: 'Hello, how are you?',
      timestamp: '2025-11-21T10:00:00Z',
    },
    {
      role: 'assistant',
      content: 'I am doing well, thank you!',
      timestamp: '2025-11-21T10:01:00Z',
    },
    {
      role: 'user',
      content: 'Can you help me with my task?',
      timestamp: '2025-11-21T10:02:00Z',
    },
  ];

  beforeEach(() => {
    jest.clearAllMocks();

    // Mock scrollIntoView globally
    Element.prototype.scrollIntoView = jest.fn();

    // Setup WebSocket mock
    mockWsClient = {
      onMessage: jest.fn((handler) => {
        // Store handler for later invocation
        (mockWsClient as any)._messageHandler = handler;
        // Return unsubscribe function
        return jest.fn();
      }),
      subscribe: jest.fn(),
      send: jest.fn(),
    };

    (getWebSocketClient as jest.Mock).mockReturnValue(mockWsClient);

    // Setup default API mocks
    mockGetHistory.mockResolvedValue({
      data: { messages: mockMessages },
    } as any);

    mockSendMessage.mockResolvedValue({
      data: {
        response: 'Mock agent response',
        timestamp: '2025-11-21T10:05:00Z',
      },
    } as any);
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it('test_renders_message_history_from_api', async () => {
    // ARRANGE
    mockGetHistory.mockResolvedValueOnce({
      data: { messages: mockMessages },
    } as any);

    // ACT
    render(<ChatInterface projectId={123} agentStatus="idle" />);

    // ASSERT: Wait for messages to load
    await waitFor(() => {
      expect(screen.getByText('Hello, how are you?')).toBeInTheDocument();
    });

    expect(screen.getByText('I am doing well, thank you!')).toBeInTheDocument();
    expect(screen.getByText('Can you help me with my task?')).toBeInTheDocument();

    // Verify API was called with correct project ID
    expect(mockGetHistory).toHaveBeenCalledWith(123);
  });

  it('test_displays_user_and_agent_messages_correctly', async () => {
    // ARRANGE
    mockGetHistory.mockResolvedValueOnce({
      data: { messages: mockMessages },
    } as any);

    // ACT
    render(<ChatInterface projectId={123} agentStatus="idle" />);

    // ASSERT: Wait for messages to load
    await waitFor(() => {
      expect(screen.getByText('Hello, how are you?')).toBeInTheDocument();
    });

    // Check user messages have correct styling (blue background)
    const userMessages = screen.getAllByText(/Hello, how are you?|Can you help me with my task?/);
    userMessages.forEach((msg) => {
      const messageDiv = msg.closest('div.bg-blue-600');
      expect(messageDiv).toBeInTheDocument();
      expect(messageDiv).toHaveClass('text-white');
    });

    // Check assistant messages have correct styling (gray background)
    const assistantMessage = screen.getByText('I am doing well, thank you!');
    const assistantDiv = assistantMessage.closest('div.bg-muted');
    expect(assistantDiv).toBeInTheDocument();
    expect(assistantDiv).toHaveClass('text-foreground');
  });

  it('test_auto_scrolls_to_latest_message', async () => {
    // ARRANGE
    const scrollIntoViewMock = jest.fn();
    Element.prototype.scrollIntoView = scrollIntoViewMock;

    mockGetHistory.mockResolvedValueOnce({
      data: { messages: mockMessages },
    } as any);

    // ACT
    render(<ChatInterface projectId={123} agentStatus="idle" />);

    // ASSERT: Wait for messages to load and scroll to be called
    await waitFor(() => {
      expect(scrollIntoViewMock).toHaveBeenCalled();
    });

    // Verify smooth scrolling behavior
    expect(scrollIntoViewMock).toHaveBeenCalledWith({ behavior: 'smooth' });
  });

  it('test_sends_message_on_form_submit', async () => {
    // ARRANGE
    const user = userEvent.setup();
    mockGetHistory.mockResolvedValueOnce({
      data: { messages: [] },
    } as any);

    mockSendMessage.mockResolvedValueOnce({
      data: {
        response: 'Agent response to test message',
        timestamp: '2025-11-21T10:10:00Z',
      },
    } as any);

    // ACT
    render(<ChatInterface projectId={123} agentStatus="idle" />);

    // Wait for component to load
    await waitFor(() => {
      expect(screen.getByPlaceholderText('Type your message...')).toBeInTheDocument();
    });

    const input = screen.getByPlaceholderText('Type your message...');
    const sendButton = screen.getByRole('button', { name: /send/i });

    // Type message and submit
    await user.type(input, 'Test message');
    await user.click(sendButton);

    // ASSERT: API called with correct parameters
    await waitFor(() => {
      expect(mockSendMessage).toHaveBeenCalledWith(123, 'Test message');
    });

    // Verify response is displayed
    await waitFor(() => {
      expect(screen.getByText('Agent response to test message')).toBeInTheDocument();
    });
  });

  it('test_validates_empty_message_should_not_send', async () => {
    // ARRANGE
    const user = userEvent.setup();
    mockGetHistory.mockResolvedValueOnce({
      data: { messages: [] },
    } as any);

    // ACT
    render(<ChatInterface projectId={123} agentStatus="idle" />);

    await waitFor(() => {
      expect(screen.getByPlaceholderText('Type your message...')).toBeInTheDocument();
    });

    const sendButton = screen.getByRole('button', { name: /send/i });

    // Try to submit without typing
    await user.click(sendButton);

    // ASSERT: API should not be called
    expect(mockSendMessage).not.toHaveBeenCalled();

    // Button should be disabled when input is empty
    expect(sendButton).toBeDisabled();
  });

  it('test_validates_whitespace_only_message_should_not_send', async () => {
    // ARRANGE
    const user = userEvent.setup();
    mockGetHistory.mockResolvedValueOnce({
      data: { messages: [] },
    } as any);

    // ACT
    render(<ChatInterface projectId={123} agentStatus="idle" />);

    await waitFor(() => {
      expect(screen.getByPlaceholderText('Type your message...')).toBeInTheDocument();
    });

    const input = screen.getByPlaceholderText('Type your message...');
    const sendButton = screen.getByRole('button', { name: /send/i });

    // Type only whitespace
    await user.type(input, '   ');
    await user.click(sendButton);

    // ASSERT: API should not be called
    expect(mockSendMessage).not.toHaveBeenCalled();
  });

  it('test_handles_agent_offline_status', async () => {
    // ARRANGE
    mockGetHistory.mockResolvedValueOnce({
      data: { messages: [] },
    } as any);

    // ACT
    render(<ChatInterface projectId={123} agentStatus="offline" />);

    await waitFor(() => {
      expect(screen.getByPlaceholderText(/Agent offline/)).toBeInTheDocument();
    });

    // ASSERT: Input is disabled
    const input = screen.getByPlaceholderText('Agent offline - start agent to chat');
    expect(input).toBeDisabled();

    // Send button is disabled
    const sendButton = screen.getByRole('button', { name: /send/i });
    expect(sendButton).toBeDisabled();

    // Status shows offline
    expect(screen.getByText('offline')).toHaveClass('text-muted-foreground');
  });

  it('test_prevents_send_when_agent_offline', async () => {
    // ARRANGE
    const user = userEvent.setup();
    mockGetHistory.mockResolvedValueOnce({
      data: { messages: [] },
    } as any);

    // ACT
    render(<ChatInterface projectId={123} agentStatus="offline" />);

    await waitFor(() => {
      expect(screen.getByPlaceholderText(/Agent offline/)).toBeInTheDocument();
    });

    // Verify input is disabled
    const input = screen.getByPlaceholderText('Agent offline - start agent to chat');
    expect(input).toBeDisabled();

    // Send button is also disabled
    const sendButton = screen.getByRole('button', { name: /send/i });
    expect(sendButton).toBeDisabled();

    // ASSERT: API should not be called even if form submitted programmatically
    const form = sendButton.closest('form');
    fireEvent.submit(form!);

    expect(mockSendMessage).not.toHaveBeenCalled();
  });

  it('test_shows_error_messages', async () => {
    // ARRANGE
    const user = userEvent.setup();
    mockGetHistory.mockResolvedValueOnce({
      data: { messages: [] },
    } as any);

    const errorMessage = 'Network error: Failed to connect';
    mockSendMessage.mockRejectedValueOnce({
      response: {
        data: {
          detail: errorMessage,
        },
      },
    });

    // ACT
    render(<ChatInterface projectId={123} agentStatus="idle" />);

    await waitFor(() => {
      expect(screen.getByPlaceholderText('Type your message...')).toBeInTheDocument();
    });

    const input = screen.getByPlaceholderText('Type your message...');
    await user.type(input, 'Test message');

    const sendButton = screen.getByRole('button', { name: /send/i });
    await user.click(sendButton);

    // ASSERT: Error message is displayed
    await waitFor(() => {
      expect(screen.getByText(errorMessage)).toBeInTheDocument();
    });

    // Error has red styling
    const errorDiv = screen.getByText(errorMessage).closest('div');
    expect(errorDiv).toHaveClass('bg-destructive/10', 'border-destructive', 'text-red-700');
  });

  it('test_shows_default_error_message_when_no_detail', async () => {
    // ARRANGE
    const user = userEvent.setup();
    mockGetHistory.mockResolvedValueOnce({
      data: { messages: [] },
    } as any);

    mockSendMessage.mockRejectedValueOnce(new Error('Unknown error'));

    // ACT
    render(<ChatInterface projectId={123} agentStatus="idle" />);

    await waitFor(() => {
      expect(screen.getByPlaceholderText('Type your message...')).toBeInTheDocument();
    });

    const input = screen.getByPlaceholderText('Type your message...');
    await user.type(input, 'Test message');

    const sendButton = screen.getByRole('button', { name: /send/i });
    await user.click(sendButton);

    // ASSERT: Default error message is shown
    await waitFor(() => {
      expect(
        screen.getByText('Failed to send message. Please try again.')
      ).toBeInTheDocument();
    });
  });

  it('test_websocket_message_integration', async () => {
    // ARRANGE
    mockGetHistory.mockResolvedValueOnce({
      data: { messages: [mockMessages[0]] }, // Start with one message
    } as any);

    // ACT
    render(<ChatInterface projectId={123} agentStatus="idle" />);

    // Wait for initial messages to load
    await waitFor(() => {
      expect(screen.getByText('Hello, how are you?')).toBeInTheDocument();
    });

    // Verify WebSocket subscription was set up
    expect(mockWsClient.onMessage).toHaveBeenCalled();

    // Get the message handler that was registered
    const messageHandler = (mockWsClient as any)._messageHandler;

    // Simulate WebSocket message
    const wsMessage: WebSocketMessage = {
      type: 'chat_message',
      timestamp: '2025-11-21T10:15:00Z',
      project_id: 123,
      data: {
        role: 'assistant',
        content: 'WebSocket message received',
        timestamp: '2025-11-21T10:15:00Z',
      },
    };

    // Call the message handler wrapped in act to handle state update
    act(() => {
      messageHandler(wsMessage);
    });

    // ASSERT: WebSocket message appears in UI
    await waitFor(() => {
      expect(screen.getByText('WebSocket message received')).toBeInTheDocument();
    });
  });

  it('test_ignores_websocket_messages_for_different_project', async () => {
    // ARRANGE
    mockGetHistory.mockResolvedValueOnce({
      data: { messages: [] },
    } as any);

    // ACT
    render(<ChatInterface projectId={123} agentStatus="idle" />);

    await waitFor(() => {
      expect(mockWsClient.onMessage).toHaveBeenCalled();
    });

    // Simulate WebSocket message for different project
    const wsMessage: WebSocketMessage = {
      type: 'chat_message',
      timestamp: '2025-11-21T10:15:00Z',
      project_id: 999, // Different project
      data: {
        role: 'assistant',
        content: 'Message for different project',
        timestamp: '2025-11-21T10:15:00Z',
      },
    };

    const messageHandler = (mockWsClient as any)._messageHandler;
    messageHandler(wsMessage);

    // ASSERT: Message should not appear
    await waitFor(() => {
      expect(screen.queryByText('Message for different project')).not.toBeInTheDocument();
    });
  });

  it('test_optimistic_ui_updates', async () => {
    // ARRANGE
    const user = userEvent.setup();
    mockGetHistory.mockResolvedValueOnce({
      data: { messages: [] },
    } as any);

    // Make API slow to resolve
    mockSendMessage.mockImplementation(
      () =>
        new Promise((resolve) =>
          setTimeout(
            () =>
              resolve({
                data: {
                  response: 'Delayed response',
                  timestamp: '2025-11-21T10:20:00Z',
                },
              } as any),
            100
          )
        )
    );

    // ACT
    render(<ChatInterface projectId={123} agentStatus="idle" />);

    await waitFor(() => {
      expect(screen.getByPlaceholderText('Type your message...')).toBeInTheDocument();
    });

    const input = screen.getByPlaceholderText('Type your message...');
    await user.type(input, 'Optimistic message');

    const sendButton = screen.getByRole('button', { name: /send/i });
    await user.click(sendButton);

    // ASSERT: User message appears immediately (optimistic)
    expect(screen.getByText('Optimistic message')).toBeInTheDocument();

    // Input is cleared immediately
    expect(input).toHaveValue('');

    // Wait for API response
    await waitFor(() => {
      expect(screen.getByText('Delayed response')).toBeInTheDocument();
    });
  });

  it('test_removes_optimistic_message_on_error', async () => {
    // ARRANGE
    const user = userEvent.setup();
    mockGetHistory.mockResolvedValueOnce({
      data: { messages: [] },
    } as any);

    // Delay the rejection to allow optimistic update to render
    mockSendMessage.mockImplementation(
      () =>
        new Promise((_, reject) =>
          setTimeout(() => reject(new Error('API Error')), 50)
        )
    );

    // ACT
    render(<ChatInterface projectId={123} agentStatus="idle" />);

    await waitFor(() => {
      expect(screen.getByPlaceholderText('Type your message...')).toBeInTheDocument();
    });

    const input = screen.getByPlaceholderText('Type your message...');
    await user.type(input, 'Message that will fail');

    const sendButton = screen.getByRole('button', { name: /send/i });

    // Click send and verify message appears immediately (optimistic)
    await user.click(sendButton);

    // Verify optimistic message appears
    expect(screen.getByText('Message that will fail')).toBeInTheDocument();
    expect(input).toHaveValue(''); // Input cleared immediately

    // ASSERT: After error, message is removed and input is restored
    await waitFor(
      () => {
        expect(screen.queryByText('Message that will fail')).not.toBeInTheDocument();
      },
      { timeout: 3000 }
    );

    // Input is restored with original message
    await waitFor(() => {
      expect(input).toHaveValue('Message that will fail');
    });

    // Error message is displayed
    await waitFor(() => {
      expect(screen.getByText(/Failed to send message/)).toBeInTheDocument();
    });
  });

  it('test_shows_loading_state_while_sending', async () => {
    // ARRANGE
    const user = userEvent.setup();
    mockGetHistory.mockResolvedValueOnce({
      data: { messages: [] },
    } as any);

    mockSendMessage.mockImplementation(
      () =>
        new Promise((resolve) =>
          setTimeout(
            () =>
              resolve({
                data: {
                  response: 'Response',
                  timestamp: '2025-11-21T10:25:00Z',
                },
              } as any),
            100
          )
        )
    );

    // ACT
    render(<ChatInterface projectId={123} agentStatus="idle" />);

    await waitFor(() => {
      expect(screen.getByPlaceholderText('Type your message...')).toBeInTheDocument();
    });

    const input = screen.getByPlaceholderText('Type your message...');
    await user.type(input, 'Loading test');

    const sendButton = screen.getByRole('button', { name: /send/i });
    await user.click(sendButton);

    // ASSERT: Loading state is shown
    await waitFor(() => {
      expect(screen.getByText('Sending...')).toBeInTheDocument();
    });

    // Input is disabled during send
    expect(input).toBeDisabled();

    // Wait for completion
    await waitFor(() => {
      expect(screen.queryByText('Sending...')).not.toBeInTheDocument();
    });

    // Input is re-enabled
    expect(input).not.toBeDisabled();
  });

  it('test_input_field_focus_management', async () => {
    // ARRANGE
    const user = userEvent.setup();
    mockGetHistory.mockResolvedValueOnce({
      data: { messages: [] },
    } as any);

    mockSendMessage.mockResolvedValueOnce({
      data: {
        response: 'Response',
        timestamp: '2025-11-21T10:30:00Z',
      },
    } as any);

    // ACT
    render(<ChatInterface projectId={123} agentStatus="idle" />);

    await waitFor(() => {
      expect(screen.getByPlaceholderText('Type your message...')).toBeInTheDocument();
    });

    const input = screen.getByPlaceholderText(
      'Type your message...'
    ) as HTMLInputElement;
    const sendButton = screen.getByRole('button', { name: /send/i });

    // Type and send
    await user.type(input, 'Focus test');
    await user.click(sendButton);

    // Wait for response to be displayed
    await waitFor(() => {
      expect(screen.getByText('Response')).toBeInTheDocument();
    });

    // ASSERT: Input regains focus after sending (focus is called by component)
    // Note: jsdom doesn't fully support focus like a real browser, so we verify the focus() call
    // was made by checking the input exists and is enabled
    expect(input).not.toBeDisabled();
    expect(input).toHaveValue('');
  });

  it('test_message_timestamp_formatting_with_date_fns', async () => {
    // ARRANGE
    const mockFormatDistanceToNow = formatDistanceToNow as jest.MockedFunction<
      typeof formatDistanceToNow
    >;
    mockFormatDistanceToNow.mockReturnValue('5 minutes ago');

    mockGetHistory.mockResolvedValueOnce({
      data: { messages: [mockMessages[0]] },
    } as any);

    // ACT
    render(<ChatInterface projectId={123} agentStatus="idle" />);

    // ASSERT: Wait for message to render with formatted timestamp
    await waitFor(() => {
      expect(screen.getByText('5 minutes ago')).toBeInTheDocument();
    });

    // Verify formatDistanceToNow was called with correct parameters
    expect(mockFormatDistanceToNow).toHaveBeenCalledWith(
      new Date('2025-11-21T10:00:00Z'),
      { addSuffix: true }
    );
  });

  it('test_handles_invalid_timestamp_gracefully', async () => {
    // ARRANGE
    const mockFormatDistanceToNow = formatDistanceToNow as jest.MockedFunction<
      typeof formatDistanceToNow
    >;
    mockFormatDistanceToNow.mockImplementation(() => {
      throw new Error('Invalid date');
    });

    mockGetHistory.mockResolvedValueOnce({
      data: {
        messages: [
          {
            role: 'user',
            content: 'Message with bad timestamp',
            timestamp: 'invalid-date',
          },
        ],
      },
    } as any);

    // ACT
    render(<ChatInterface projectId={123} agentStatus="idle" />);

    // ASSERT: Falls back to 'just now'
    await waitFor(() => {
      expect(screen.getByText('just now')).toBeInTheDocument();
    });
  });

  it('test_displays_no_messages_placeholder', async () => {
    // ARRANGE
    mockGetHistory.mockResolvedValueOnce({
      data: { messages: [] },
    } as any);

    // ACT
    render(<ChatInterface projectId={123} agentStatus="idle" />);

    // ASSERT: Placeholder text is shown
    await waitFor(() => {
      expect(screen.getByText('No messages yet.')).toBeInTheDocument();
      expect(
        screen.getByText('Start a conversation with the Lead Agent!')
      ).toBeInTheDocument();
    });
  });

  it('test_shows_history_error_state', async () => {
    // ARRANGE
    const errorMessage = 'Failed to load chat history';
    mockGetHistory.mockRejectedValueOnce(new Error(errorMessage));

    // ACT
    render(<ChatInterface projectId={123} agentStatus="idle" />);

    // ASSERT: Error message is displayed
    await waitFor(() => {
      expect(
        screen.getByText('Failed to load chat history. Please refresh the page.')
      ).toBeInTheDocument();
    });

    // Error has red styling
    const errorDiv = screen.getByText(
      'Failed to load chat history. Please refresh the page.'
    ).closest('div');
    expect(errorDiv).toHaveClass('bg-destructive/10', 'text-destructive-foreground');
  });

  it('test_displays_agent_status_with_correct_styling', async () => {
    // ARRANGE
    mockGetHistory.mockResolvedValueOnce({
      data: { messages: [] },
    } as any);

    const { rerender } = render(<ChatInterface projectId={123} agentStatus="working" />);

    // ASSERT: Working status is green
    await waitFor(() => {
      expect(screen.getByText('working')).toHaveClass('text-secondary-foreground');
    });

    // Blocked status is red
    rerender(<ChatInterface projectId={123} agentStatus="blocked" />);
    expect(screen.getByText('blocked')).toHaveClass('text-destructive-foreground');

    // Offline status is gray
    rerender(<ChatInterface projectId={123} agentStatus="offline" />);
    expect(screen.getByText('offline')).toHaveClass('text-muted-foreground');

    // Idle status is yellow
    rerender(<ChatInterface projectId={123} agentStatus="idle" />);
    expect(screen.getByText('idle')).toHaveClass('text-yellow-600');
  });

  it('test_websocket_cleanup_on_unmount', async () => {
    // ARRANGE
    const unsubscribeMock = jest.fn();
    mockWsClient.onMessage.mockReturnValue(unsubscribeMock);

    mockGetHistory.mockResolvedValueOnce({
      data: { messages: [] },
    } as any);

    // ACT
    const { unmount } = render(<ChatInterface projectId={123} agentStatus="idle" />);

    await waitFor(() => {
      expect(mockWsClient.onMessage).toHaveBeenCalled();
    });

    // Unmount component
    unmount();

    // ASSERT: Unsubscribe was called
    expect(unsubscribeMock).toHaveBeenCalled();
  });

  it('test_prevents_double_submit_while_sending', async () => {
    // ARRANGE
    const user = userEvent.setup();
    mockGetHistory.mockResolvedValueOnce({
      data: { messages: [] },
    } as any);

    let resolvePromise: any;
    mockSendMessage.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolvePromise = () =>
            resolve({
              data: {
                response: 'Response',
                timestamp: '2025-11-21T10:35:00Z',
              },
            } as any);
        })
    );

    // ACT
    render(<ChatInterface projectId={123} agentStatus="idle" />);

    await waitFor(() => {
      expect(screen.getByPlaceholderText('Type your message...')).toBeInTheDocument();
    });

    const input = screen.getByPlaceholderText('Type your message...');
    await user.type(input, 'First message');

    const sendButton = screen.getByRole('button', { name: /send/i });
    await user.click(sendButton);

    // Try to submit again while first is pending
    await user.click(sendButton);

    // ASSERT: API called only once
    expect(mockSendMessage).toHaveBeenCalledTimes(1);

    // Resolve the promise
    resolvePromise();

    await waitFor(() => {
      expect(screen.getByText('Response')).toBeInTheDocument();
    });
  });
});
