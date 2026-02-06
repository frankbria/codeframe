'use client';

import { useRef, useEffect, useState, useCallback } from 'react';
import { ArrowDown01Icon } from '@hugeicons/react';
import { Button } from '@/components/ui/button';
import { EventItem } from './EventItem';
import type { ExecutionEvent } from '@/hooks/useTaskStream';

interface EventStreamProps {
  events: ExecutionEvent[];
  workspacePath: string;
  onBlockerAnswered?: () => void;
}

/**
 * Scrollable event stream with auto-scroll behavior.
 *
 * - Default: auto-scrolls to bottom on new events
 * - When user scrolls up: pauses auto-scroll, shows "New events" button
 * - Click button or scroll to bottom: re-enables auto-scroll
 *
 * Uses a single scrollable div (no Radix ScrollArea) so that
 * onScroll and scrollIntoView work on the same container.
 */
export function EventStream({ events, workspacePath, onBlockerAnswered }: EventStreamProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [autoScroll, setAutoScroll] = useState(true);
  const [hasNewEvents, setHasNewEvents] = useState(false);
  const prevEventCountRef = useRef(events.length);

  // Filter out heartbeat events for display
  const displayEvents = events.filter((e) => e.event_type !== 'heartbeat');

  // Detect new events while scrolled up
  useEffect(() => {
    if (events.length > prevEventCountRef.current && !autoScroll) {
      setHasNewEvents(true);
    }
    prevEventCountRef.current = events.length;
  }, [events.length, autoScroll]);

  // Auto-scroll to bottom when new events arrive
  useEffect(() => {
    if (autoScroll && bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [displayEvents.length, autoScroll]);

  // Detect user scroll position
  const handleScroll = useCallback(() => {
    const container = containerRef.current;
    if (!container) return;

    const { scrollTop, scrollHeight, clientHeight } = container;
    const isAtBottom = scrollHeight - scrollTop - clientHeight < 40;

    if (isAtBottom) {
      setAutoScroll(true);
      setHasNewEvents(false);
    } else {
      setAutoScroll(false);
    }
  }, []);

  const scrollToBottom = useCallback(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    setAutoScroll(true);
    setHasNewEvents(false);
  }, []);

  return (
    <div className="relative flex-1 overflow-hidden rounded-lg border">
      <div
        ref={containerRef}
        className="h-full overflow-y-auto p-4"
        onScroll={handleScroll}
      >
        {displayEvents.length === 0 ? (
          <p className="py-8 text-center text-sm text-muted-foreground">
            Waiting for events...
          </p>
        ) : (
          <div className="space-y-0.5">
            {displayEvents.map((event, i) => (
              <EventItem
                key={`${event.timestamp}-${i}`}
                event={event}
                workspacePath={workspacePath}
                onBlockerAnswered={onBlockerAnswered}
              />
            ))}
          </div>
        )}
        {/* Scroll sentinel */}
        <div ref={bottomRef} />
      </div>

      {/* "New events" floating button */}
      {hasNewEvents && (
        <div className="absolute bottom-3 left-1/2 -translate-x-1/2">
          <Button
            variant="secondary"
            size="sm"
            className="h-7 gap-1 rounded-full px-3 text-xs shadow-md"
            onClick={scrollToBottom}
          >
            <ArrowDown01Icon className="h-3.5 w-3.5" />
            New events
          </Button>
        </div>
      )}
    </div>
  );
}
