/**
 * Chat Interface Component (cf-14.2)
 *
 * Real-time chat interface for communicating with Lead Agent.
 * Features:
 * - Message history display with auto-scroll
 * - Message input with send button
 * - WebSocket integration for real-time updates
 * - Loading states and error handling
 */

'use client';

import { useState, useEffect, useRef, memo } from 'react';
import useSWR from 'swr';
import { chatApi } from '@/lib/api';
import { getWebSocketClient } from '@/lib/websocket';
import type { ChatMessage, WebSocketMessage } from '@/types';
import { formatDistanceToNow } from 'date-fns';

interface ChatInterfaceProps {
  projectId: number;
  agentStatus?: 'idle' | 'working' | 'blocked' | 'offline';
}

const ChatInterface = memo(function ChatInterface({ projectId, agentStatus = 'idle' }: ChatInterfaceProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputMessage, setInputMessage] = useState('');
  const [isSending, setIsSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Fetch conversation history
  const { data: historyData, error: historyError } = useSWR(
    `/projects/${projectId}/chat/history`,
    async () => {
      const response = await chatApi.getHistory(projectId);
      return response.data;
    },
    {
      revalidateOnFocus: false,
      revalidateOnReconnect: false,
    }
  );

  // Initialize messages from history
  useEffect(() => {
    if (historyData?.messages) {
      setMessages(historyData.messages as ChatMessage[]);
    }
  }, [historyData]);

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // WebSocket integration for real-time updates
  useEffect(() => {
    const ws = getWebSocketClient();

    const unsubscribe = ws.onMessage((message: WebSocketMessage) => {
      if (message.type === 'chat_message' && message.project_id === projectId) {
        // Add new message to list
        const newMessage: ChatMessage = {
          role: message.data.role,
          content: message.data.content,
          timestamp: message.data.timestamp,
        };
        setMessages((prev) => [...prev, newMessage]);
      }
    });

    return () => {
      unsubscribe();
    };
  }, [projectId]);

  // Handle send message
  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault();

    const trimmedMessage = inputMessage.trim();
    if (!trimmedMessage || isSending) return;

    // Check if agent is available
    if (agentStatus === 'offline') {
      setError('Lead Agent is offline. Please start the agent first.');
      return;
    }

    setIsSending(true);
    setError(null);

    // Optimistically add user message
    const userMessage: ChatMessage = {
      role: 'user',
      content: trimmedMessage,
      timestamp: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMessage]);
    setInputMessage('');

    try {
      // Send to backend
      const response = await chatApi.send(projectId, trimmedMessage);

      // Add assistant response
      const assistantMessage: ChatMessage = {
        role: 'assistant',
        content: response.data.response,
        timestamp: response.data.timestamp,
      };
      setMessages((prev) => [...prev, assistantMessage]);

      // Focus back on input
      inputRef.current?.focus();
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to send message. Please try again.');
      // Remove optimistic user message on error
      setMessages((prev) => prev.slice(0, -1));
      // Restore input
      setInputMessage(trimmedMessage);
    } finally {
      setIsSending(false);
    }
  };

  // Format timestamp for display
  const formatTimestamp = (timestamp: string) => {
    try {
      return formatDistanceToNow(new Date(timestamp), { addSuffix: true });
    } catch {
      return 'just now';
    }
  };

  return (
    <div className="flex flex-col h-full bg-card rounded-lg shadow border border-border">
      {/* Chat Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-border">
        <div>
          <h3 className="text-lg font-semibold text-foreground">Chat with Lead Agent</h3>
          <p className="text-sm text-muted-foreground">
            Status: <span className={`font-medium ${
              agentStatus === 'working' ? 'text-green-600' :
              agentStatus === 'blocked' ? 'text-destructive' :
              agentStatus === 'offline' ? 'text-muted-foreground' :
              'text-yellow-600'
            }`}>{agentStatus}</span>
          </p>
        </div>
      </div>

      {/* Message History */}
      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
        {historyError && (
          <div className="text-center text-sm text-destructive bg-destructive/10 rounded p-3 border border-destructive/20">
            Failed to load chat history. Please refresh the page.
          </div>
        )}

        {messages.length === 0 && !historyError && (
          <div className="text-center text-muted-foreground py-8">
            <p className="text-sm">No messages yet.</p>
            <p className="text-xs mt-1">Start a conversation with the Lead Agent!</p>
          </div>
        )}

        {messages.map((msg, index) => (
          <div
            key={index}
            className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`max-w-[70%] rounded-lg px-4 py-2 ${
                msg.role === 'user'
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-muted text-foreground'
              }`}
            >
              <p className="text-sm whitespace-pre-wrap break-words">{msg.content}</p>
              <p className={`text-xs mt-1 ${
                msg.role === 'user' ? 'text-primary-foreground/70' : 'text-muted-foreground'
              }`}>
                {formatTimestamp(msg.timestamp)}
              </p>
            </div>
          </div>
        ))}

        <div ref={messagesEndRef} />
      </div>

      {/* Error Display */}
      {error && (
        <div className="mx-6 mb-2 px-4 py-2 bg-destructive/10 border border-destructive/20 rounded text-sm text-destructive">
          {error}
        </div>
      )}

      {/* Message Input */}
      <form onSubmit={handleSendMessage} className="px-6 py-4 border-t border-border">
        <div className="flex gap-2">
          <input
            ref={inputRef}
            type="text"
            value={inputMessage}
            onChange={(e) => setInputMessage(e.target.value)}
            placeholder={
              agentStatus === 'offline'
                ? 'Agent offline - start agent to chat'
                : 'Type your message...'
            }
            disabled={isSending || agentStatus === 'offline'}
            className="flex-1 px-4 py-2 border border-input rounded-md focus:outline-none focus:ring-2 focus:ring-primary disabled:bg-muted disabled:cursor-not-allowed text-foreground bg-background"
          />
          <button
            type="submit"
            disabled={!inputMessage.trim() || isSending || agentStatus === 'offline'}
            className="px-6 py-2 bg-primary text-primary-foreground rounded-md hover:bg-primary/90 disabled:bg-muted disabled:text-muted-foreground disabled:cursor-not-allowed transition-colors"
          >
            {isSending ? (
              <span className="flex items-center gap-2">
                <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                  <circle
                    className="opacity-25"
                    cx="12"
                    cy="12"
                    r="10"
                    stroke="currentColor"
                    strokeWidth="4"
                    fill="none"
                  />
                  <path
                    className="opacity-75"
                    fill="currentColor"
                    d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                  />
                </svg>
                Sending...
              </span>
            ) : (
              'Send'
            )}
          </button>
        </div>
      </form>
    </div>
  );
});

ChatInterface.displayName = 'ChatInterface';

export default ChatInterface;
