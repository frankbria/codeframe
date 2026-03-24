'use client';

import { useRef, useEffect, useState, useCallback } from 'react';
import { ArrowDown01Icon, ArrowRight01Icon } from '@hugeicons/react';
import { Button } from '@/components/ui/button';
import { EventItem } from './EventItem';
import type { ExecutionEvent } from '@/hooks/useTaskStream';

interface EventStreamProps {
  events: ExecutionEvent[];
  workspacePath: string;
  onBlockerAnswered?: () => void;
}

// ── Event grouping ──────────────────────────────────────────────────────

type EventGroup =
  | { type: 'event'; event: ExecutionEvent }
  | { type: 'read_group'; count: number; files: string[]; timestamp: string; events: ExecutionEvent[] }
  | { type: 'edit_group'; count: number; files: string[]; timestamp: string };

function extractFilename(msg: string): string {
  const m = msg.match(/file:\s*(.+)/i);
  return m ? (m[1].split('/').pop() ?? m[1]) : msg;
}

function isReadEvent(e: ExecutionEvent): boolean {
  if (e.event_type !== 'progress') return false;
  return /^reading file:/i.test((e as { message?: string }).message ?? '');
}

function isEditEvent(e: ExecutionEvent): boolean {
  if (e.event_type !== 'progress') return false;
  return /^(creating|editing|deleting) file:/i.test((e as { message?: string }).message ?? '');
}

function groupEvents(events: ExecutionEvent[]): EventGroup[] {
  const groups: EventGroup[] = [];
  let readBuf: ExecutionEvent[] = [];
  let editBuf: ExecutionEvent[] = [];

  function flushRead() {
    if (!readBuf.length) return;
    const files = readBuf.map((e) => extractFilename((e as { message?: string }).message ?? ''));
    groups.push({ type: 'read_group', count: readBuf.length, files, timestamp: readBuf[0].timestamp, events: [...readBuf] });
    readBuf = [];
  }

  function flushEdit() {
    if (!editBuf.length) return;
    if (editBuf.length === 1) {
      groups.push({ type: 'event', event: editBuf[0] });
    } else {
      const files = editBuf.map((e) => extractFilename((e as { message?: string }).message ?? ''));
      groups.push({ type: 'edit_group', count: editBuf.length, files, timestamp: editBuf[0].timestamp });
    }
    editBuf = [];
  }

  for (const event of events) {
    if (isReadEvent(event)) {
      flushEdit();
      readBuf.push(event);
    } else if (isEditEvent(event)) {
      flushRead();
      editBuf.push(event);
    } else {
      flushRead();
      flushEdit();
      groups.push({ type: 'event', event });
    }
  }
  flushRead();
  flushEdit();
  return groups;
}

// ── Group row components ────────────────────────────────────────────────

function ReadGroupRow({
  group,
  workspacePath,
}: {
  group: Extract<EventGroup, { type: 'read_group' }>;
  workspacePath: string;
}) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div>
      <button
        className="flex w-full items-center gap-2 rounded px-1 py-1 text-left text-xs text-muted-foreground hover:bg-muted/40"
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
        aria-label={`${expanded ? 'Collapse' : 'Expand'} ${group.count} file read events`}
      >
        <ArrowRight01Icon
          className={`h-3 w-3 shrink-0 transition-transform ${expanded ? 'rotate-90' : ''}`}
        />
        <span className="font-mono text-[11px]">
          {new Date(group.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
        </span>
        <span>
          Read {group.count} file{group.count !== 1 ? 's' : ''}
          {group.count <= 4 && `: ${group.files.join(', ')}`}
        </span>
      </button>
      {expanded && (
        <div className="ml-4 space-y-0.5 border-l pl-3">
          {group.events.map((e, i) => (
            <EventItem key={`${e.timestamp}-${i}`} event={e} workspacePath={workspacePath} />
          ))}
        </div>
      )}
    </div>
  );
}

function EditGroupRow({ group }: { group: Extract<EventGroup, { type: 'edit_group' }> }) {
  return (
    <div className="flex items-baseline gap-2 py-1.5">
      <span className="shrink-0 font-mono text-[11px] text-muted-foreground">
        {new Date(group.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
      </span>
      <span className="rounded bg-blue-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase leading-none text-blue-800 dark:bg-blue-900/40 dark:text-blue-300">
        edit
      </span>
      <p className="text-sm">
        Modified {group.count} files: {group.files.join(', ')}
      </p>
    </div>
  );
}

// ── Main EventStream ────────────────────────────────────────────────────

/**
 * Scrollable event stream with auto-scroll and smart grouping.
 *
 * Smart view (default): groups consecutive file reads into collapsible rows
 * and summarises consecutive file edits into a single line.
 * Raw log: toggle via "Show all events" button to see every event unmodified.
 */
export function EventStream({ events, workspacePath, onBlockerAnswered }: EventStreamProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [autoScroll, setAutoScroll] = useState(true);
  const [hasNewEvents, setHasNewEvents] = useState(false);
  const [showAll, setShowAll] = useState(false);
  const prevEventCountRef = useRef(events.length);

  // Filter out heartbeat events for display
  const displayEvents = events.filter((e) => e.event_type !== 'heartbeat');
  const groups = groupEvents(displayEvents);

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
      {/* Header: stream label + view toggle */}
      <div className="flex items-center justify-between border-b px-4 py-2">
        <span className="text-xs font-medium text-muted-foreground">Event stream</span>
        <button
          className="text-xs text-muted-foreground hover:text-foreground"
          onClick={() => setShowAll((v) => !v)}
        >
          {showAll ? 'Smart view' : 'Show all events'}
        </button>
      </div>

      <div
        ref={containerRef}
        className="h-[calc(100%-37px)] overflow-y-auto p-4"
        onScroll={handleScroll}
        role="log"
        aria-live="polite"
        aria-label="Execution event stream"
      >
        {displayEvents.length === 0 ? (
          <p className="py-8 text-center text-sm text-muted-foreground">
            Waiting for events...
          </p>
        ) : showAll ? (
          // Raw log — every event unmodified
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
        ) : (
          // Smart view — grouped
          <div className="space-y-0.5">
            {groups.map((group, i) => {
              if (group.type === 'event') {
                return (
                  <EventItem
                    key={`${group.event.timestamp}-${i}`}
                    event={group.event}
                    workspacePath={workspacePath}
                    onBlockerAnswered={onBlockerAnswered}
                  />
                );
              }
              if (group.type === 'read_group') {
                return <ReadGroupRow key={`rg-${i}`} group={group} workspacePath={workspacePath} />;
              }
              return <EditGroupRow key={`eg-${i}`} group={group} />;
            })}
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
