'use client';

import { useRef, useEffect, useState, useCallback } from 'react';
import {
  ArtificialIntelligence01Icon,
  ArrowRight01Icon,
  Alert01Icon,
  Idea01Icon,
  Cancel01Icon,
  SentIcon,
} from '@hugeicons/react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { useAgentChat } from '@/hooks/useAgentChat';
import type { ChatMessage, AgentChatStatus } from '@/types';

// ── Types ────────────────────────────────────────────────────────────────

interface AgentChatPanelProps {
  sessionId: string;
  className?: string;
}

// ── Status dot ───────────────────────────────────────────────────────────

function statusDotClass(status: AgentChatStatus): string {
  if (status === 'connecting') return 'bg-yellow-400';
  if (status === 'error' || status === 'disconnected') return 'bg-red-500';
  return 'bg-green-500';
}

function statusLabel(status: AgentChatStatus): string {
  if (status === 'connecting') return 'Status: connecting';
  if (status === 'error') return 'Status: error';
  if (status === 'disconnected') return 'Status: disconnected';
  return 'Status: connected';
}

// ── Per-role renderers ────────────────────────────────────────────────────

function UserBubble({ message }: { message: ChatMessage }) {
  return (
    <div className="flex flex-row-reverse">
      <div className="max-w-[80%] rounded-lg bg-primary px-3 py-2 text-sm text-primary-foreground leading-relaxed">
        {message.content}
      </div>
    </div>
  );
}

function AssistantBubble({
  message,
  isLast,
  status,
}: {
  message: ChatMessage;
  isLast: boolean;
  status: AgentChatStatus;
}) {
  return (
    <div className="flex flex-row gap-3">
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary/10">
        <ArtificialIntelligence01Icon className="h-4 w-4 text-primary" />
      </div>
      <div className="max-w-[80%] rounded-lg bg-muted px-3 py-2 text-sm text-foreground leading-relaxed">
        {message.content}
        {isLast && status === 'streaming' && (
          <span
            data-testid="streaming-cursor"
            className="inline-block w-0.5 h-4 bg-current animate-pulse ml-0.5 align-middle"
            aria-hidden="true"
          />
        )}
      </div>
    </div>
  );
}

function ToolUseCard({ message }: { message: ChatMessage }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="rounded-lg border bg-muted/30 text-sm">
      <button
        className="flex w-full items-center gap-2 px-3 py-2 text-left hover:bg-muted/40 rounded-lg"
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
        aria-label={`${expanded ? 'Collapse' : 'Expand'} tool call: ${message.toolName ?? 'tool'}`}
      >
        <ArrowRight01Icon
          className={`h-3 w-3 shrink-0 transition-transform ${expanded ? 'rotate-90' : ''}`}
        />
        <span className="font-mono text-xs text-muted-foreground">{message.toolName ?? 'tool'}</span>
      </button>
      {expanded && message.toolInput !== undefined && (
        <pre className="text-xs overflow-x-auto bg-muted/50 rounded-b-lg p-2 mt-0 border-t">
          {JSON.stringify(message.toolInput, null, 2)}
        </pre>
      )}
    </div>
  );
}

function ToolResultCard({ message }: { message: ChatMessage }) {
  const [expanded, setExpanded] = useState(false);
  const isTruncated = message.content.length > 200;
  const displayContent = expanded ? message.content : message.content.slice(0, 200);

  return (
    <div className="rounded-lg border bg-muted/20 text-sm">
      <pre className="text-xs overflow-x-auto px-3 py-2 whitespace-pre-wrap break-all">
        {displayContent}
      </pre>
      {isTruncated && (
        <div className="px-3 pb-2">
          <Button
            variant="ghost"
            size="sm"
            className="h-6 px-2 text-xs"
            onClick={() => setExpanded((v) => !v)}
            aria-label={expanded ? 'Show less' : 'Show more'}
          >
            {expanded ? 'Show less' : 'Show more'}
          </Button>
        </div>
      )}
    </div>
  );
}

function ThinkingBlock({ message }: { message: ChatMessage }) {
  return (
    <div className="flex gap-2 border-l-2 border-muted-foreground/30 pl-3 italic text-sm text-muted-foreground">
      <Idea01Icon className="h-4 w-4 shrink-0 mt-0.5" aria-hidden="true" />
      <span>{message.content}</span>
    </div>
  );
}

function SystemLine({ message }: { message: ChatMessage }) {
  return (
    <p className="text-center text-xs text-muted-foreground py-1">{message.content}</p>
  );
}

function ErrorCard({ message }: { message: ChatMessage }) {
  return (
    <div className="flex gap-2 rounded-lg border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive">
      <Alert01Icon className="h-4 w-4 shrink-0 mt-0.5" aria-hidden="true" />
      <span>{message.content}</span>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center h-full gap-3 text-muted-foreground">
      <ArtificialIntelligence01Icon className="h-10 w-10 opacity-40" aria-hidden="true" />
      <p className="text-sm">Start a conversation with your agent</p>
    </div>
  );
}

function MessageRow({
  message,
  isLast,
  status,
}: {
  message: ChatMessage;
  isLast: boolean;
  status: AgentChatStatus;
}) {
  switch (message.role) {
    case 'user':
      return <UserBubble message={message} />;
    case 'assistant':
      return <AssistantBubble message={message} isLast={isLast} status={status} />;
    case 'tool_use':
      return <ToolUseCard message={message} />;
    case 'tool_result':
      return <ToolResultCard message={message} />;
    case 'thinking':
      return <ThinkingBlock message={message} />;
    case 'system':
      return <SystemLine message={message} />;
    case 'error':
      return <ErrorCard message={message} />;
    default:
      return null;
  }
}

// ── Main component ────────────────────────────────────────────────────────

export function AgentChatPanel({ sessionId, className }: AgentChatPanelProps) {
  const { state, sendMessage, interrupt } = useAgentChat(sessionId);
  const { messages, status, costUsd } = state;

  const [value, setValue] = useState('');
  const [autoScroll, setAutoScroll] = useState(true);

  const containerRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const isBusy = status === 'thinking' || status === 'streaming';

  // Track last message so streaming content updates (same array length) also trigger scroll
  const lastMessage = messages[messages.length - 1];

  // Auto-scroll on new messages and on in-place streaming updates to the last message
  useEffect(() => {
    if (autoScroll && bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [autoScroll, lastMessage?.id, lastMessage?.content]);

  const handleScroll = useCallback(() => {
    const container = containerRef.current;
    if (!container) return;
    const { scrollTop, scrollHeight, clientHeight } = container;
    setAutoScroll(scrollHeight - scrollTop - clientHeight < 40);
  }, []);

  const handleSend = useCallback(() => {
    const trimmed = value.trim();
    if (!trimmed || isBusy) return;
    sendMessage(trimmed);
    setValue('');
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  }, [value, isBusy, sendMessage]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    },
    [handleSend]
  );

  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setValue(e.target.value);
    const el = e.target;
    el.style.height = 'auto';
    el.style.height = `${el.scrollHeight}px`;
  };

  return (
    <div className={`flex h-full flex-col rounded-lg border bg-card ${className ?? ''}`}>
      {/* Header */}
      <div className="flex items-center justify-between border-b px-4 py-3">
        <div className="flex items-center gap-2">
          <span
            role="status"
            aria-label={statusLabel(status)}
            className={`h-2.5 w-2.5 rounded-full ${statusDotClass(status)}`}
          />
          <Badge variant="secondary" className="text-xs">
            claude-sonnet-4-6
          </Badge>
        </div>
        <span className="font-mono text-xs text-muted-foreground">
          ${costUsd.toFixed(4)}
        </span>
      </div>

      {/* Message list */}
      <div
        ref={containerRef}
        onScroll={handleScroll}
        role="log"
        aria-live="polite"
        aria-label="Agent chat messages"
        className="flex-1 overflow-y-auto px-4 py-4 space-y-3"
      >
        {messages.length === 0 ? (
          <EmptyState />
        ) : (
          messages.map((msg, i) => (
            <MessageRow
              key={msg.id}
              message={msg}
              isLast={i === messages.length - 1}
              status={status}
            />
          ))
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input bar */}
      <div className="border-t bg-background px-4 py-3">
        <div className="flex items-end gap-2">
          {isBusy && (
            <Button
              variant="outline"
              size="sm"
              onClick={interrupt}
              aria-label="Interrupt agent"
            >
              <Cancel01Icon className="h-4 w-4 mr-1" />
              Interrupt
            </Button>
          )}
          <textarea
            ref={textareaRef}
            value={value}
            onChange={handleInput}
            onKeyDown={handleKeyDown}
            disabled={isBusy}
            placeholder="Message your agent... (Enter to send)"
            rows={1}
            aria-label="Message input"
            style={{ maxHeight: '9rem' }}
            className="flex-1 resize-none rounded-md border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
          />
          <Button
            size="icon"
            onClick={handleSend}
            disabled={isBusy || !value.trim()}
            aria-label="Send message"
            className="shrink-0"
          >
            <SentIcon className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  );
}
