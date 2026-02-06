'use client';

import { useEffect, useRef } from 'react';
import { ArtificialIntelligence01Icon } from '@hugeicons/react';
import type { DiscoveryMessage } from '@/types';

interface DiscoveryTranscriptProps {
  messages: DiscoveryMessage[];
  isThinking: boolean;
}

export function DiscoveryTranscript({
  messages,
  isThinking,
}: DiscoveryTranscriptProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom on new messages or thinking state change
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages.length, isThinking]);

  return (
    <div className="flex-1 space-y-4 overflow-y-auto px-4 py-4">
      {messages.map((msg, i) => (
        <div
          key={i}
          className={`flex gap-3 ${msg.role === 'user' ? 'flex-row-reverse' : 'flex-row'}`}
        >
          {/* Avatar */}
          {msg.role === 'assistant' && (
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary/10">
              <ArtificialIntelligence01Icon className="h-4 w-4 text-primary" />
            </div>
          )}

          {/* Bubble */}
          <div
            className={`max-w-[80%] rounded-lg px-3 py-2 text-sm leading-relaxed ${
              msg.role === 'user'
                ? 'bg-primary text-primary-foreground'
                : 'bg-muted text-foreground'
            }`}
          >
            {msg.content}
          </div>
        </div>
      ))}

      {/* Thinking indicator */}
      {isThinking && (
        <div className="flex gap-3">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary/10">
            <ArtificialIntelligence01Icon className="h-4 w-4 text-primary" />
          </div>
          <div className="rounded-lg bg-muted px-3 py-2">
            <div className="flex gap-1">
              <span className="h-2 w-2 animate-bounce rounded-full bg-muted-foreground/50 [animation-delay:0ms]" />
              <span className="h-2 w-2 animate-bounce rounded-full bg-muted-foreground/50 [animation-delay:150ms]" />
              <span className="h-2 w-2 animate-bounce rounded-full bg-muted-foreground/50 [animation-delay:300ms]" />
            </div>
          </div>
        </div>
      )}

      <div ref={bottomRef} />
    </div>
  );
}
