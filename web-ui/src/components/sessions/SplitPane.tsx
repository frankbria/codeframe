'use client';

import { useRef, useEffect, useState, useCallback } from 'react';
import { ArrowLeft01Icon, ArrowRight01Icon } from '@hugeicons/react';
import { cn } from '@/lib/utils';

// ── Types ────────────────────────────────────────────────────────────────

interface SplitPaneProps {
  left: React.ReactNode;
  right: React.ReactNode;
  defaultSplit?: number;
  minPanePercent?: number;
  storageKey?: string;
  className?: string;
}

// ── Helpers ──────────────────────────────────────────────────────────────

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

function readStorage(key: string, fallback: number): number {
  try {
    const raw = localStorage.getItem(key);
    if (raw !== null) {
      const parsed = parseFloat(raw);
      if (!isNaN(parsed)) return parsed;
    }
  } catch {
    // localStorage unavailable (SSR, private browsing, etc.)
  }
  return fallback;
}

function writeStorage(key: string, value: number): void {
  try {
    localStorage.setItem(key, String(value));
  } catch {
    // ignore
  }
}

// ── Component ────────────────────────────────────────────────────────────

export function SplitPane({
  left,
  right,
  defaultSplit = 45,
  minPanePercent = 15,
  storageKey = 'split-pane-position',
  className,
}: SplitPaneProps) {
  const [splitPct, setSplitPct] = useState<number>(() =>
    readStorage(storageKey, defaultSplit),
  );
  const [isLeftCollapsed, setIsLeftCollapsed] = useState(false);
  const [isRightCollapsed, setIsRightCollapsed] = useState(false);
  const [isMobile, setIsMobile] = useState(false);

  const containerRef = useRef<HTMLDivElement>(null);
  const leftPaneRef = useRef<HTMLDivElement>(null);
  const rightPaneRef = useRef<HTMLDivElement>(null);
  const isDragging = useRef(false);
  const livePercent = useRef(splitPct);
  const lastNonCollapsed = useRef(splitPct);
  const transitionEnabled = useRef(false);

  // ── Mobile detection ──────────────────────────────────────────────────

  useEffect(() => {
    const mq = window.matchMedia('(min-width: 768px)');
    setIsMobile(!mq.matches);
    const handler = (e: { matches: boolean }) => setIsMobile(!e.matches);
    mq.addEventListener('change', handler);
    return () => mq.removeEventListener('change', handler);
  }, []);

  // ── Sync DOM width refs when splitPct or transition state changes ──────

  const applyWidths = useCallback(
    (pct: number) => {
      if (!leftPaneRef.current || !rightPaneRef.current) return;
      const transition = transitionEnabled.current ? 'width 200ms ease' : '';
      leftPaneRef.current.style.transition = transition;
      rightPaneRef.current.style.transition = transition;
      leftPaneRef.current.style.width = `${pct}%`;
      rightPaneRef.current.style.width = `${100 - pct}%`;
    },
    [],
  );

  // Apply widths whenever splitPct changes (collapse/expand triggers re-render)
  useEffect(() => {
    applyWidths(splitPct);
  }, [splitPct, applyWidths]);

  // ── Drag logic ────────────────────────────────────────────────────────

  useEffect(() => {
    const onMouseMove = (e: MouseEvent) => {
      if (!isDragging.current || !containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      const rawPct = ((e.clientX - rect.left) / rect.width) * 100;
      const clamped = clamp(rawPct, minPanePercent, 100 - minPanePercent);
      livePercent.current = clamped;
      // Direct DOM mutation — no setState during mousemove
      if (leftPaneRef.current) leftPaneRef.current.style.width = `${clamped}%`;
      if (rightPaneRef.current) rightPaneRef.current.style.width = `${100 - clamped}%`;
    };

    const onMouseUp = () => {
      if (!isDragging.current) return;
      isDragging.current = false;
      const committed = livePercent.current;
      lastNonCollapsed.current = committed;
      setSplitPct(committed);
      writeStorage(storageKey, committed);
    };

    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('mouseup', onMouseUp);
    return () => {
      document.removeEventListener('mousemove', onMouseMove);
      document.removeEventListener('mouseup', onMouseUp);
    };
  }, [minPanePercent, storageKey]);

  const onDividerMouseDown = () => {
    isDragging.current = true;
    transitionEnabled.current = false;
    // Remove transitions immediately so drag is instant
    if (leftPaneRef.current) leftPaneRef.current.style.transition = '';
    if (rightPaneRef.current) rightPaneRef.current.style.transition = '';
  };

  // ── Collapse logic ────────────────────────────────────────────────────

  const collapseLeft = () => {
    transitionEnabled.current = true;
    if (isLeftCollapsed) {
      const restore = lastNonCollapsed.current;
      setIsLeftCollapsed(false);
      setSplitPct(restore);
      writeStorage(storageKey, restore);
    } else {
      lastNonCollapsed.current = splitPct;
      setIsLeftCollapsed(true);
      setIsRightCollapsed(false);
      setSplitPct(0);
      writeStorage(storageKey, 0);
    }
  };

  const collapseRight = () => {
    transitionEnabled.current = true;
    if (isRightCollapsed) {
      const restore = lastNonCollapsed.current;
      setIsRightCollapsed(false);
      setSplitPct(restore);
      writeStorage(storageKey, restore);
    } else {
      lastNonCollapsed.current = splitPct;
      setIsRightCollapsed(true);
      setIsLeftCollapsed(false);
      setSplitPct(100);
      writeStorage(storageKey, 100);
    }
  };

  // ── Render ────────────────────────────────────────────────────────────

  return (
    <div
      ref={containerRef}
      data-testid="split-pane-container"
      className={cn(
        'flex w-full h-full',
        isMobile ? 'flex-col' : 'flex-row',
        className,
      )}
    >
      {/* Left pane */}
      <div
        ref={leftPaneRef}
        data-testid="split-pane-left"
        style={isMobile ? undefined : { width: `${splitPct}%` }}
        className={cn(
          'overflow-hidden flex-shrink-0',
          isMobile && 'h-[60%] w-full',
        )}
      >
        {left}
      </div>

      {/* Divider */}
      <div
        data-testid="split-pane-divider"
        onMouseDown={onDividerMouseDown}
        className={cn(
          'relative flex-shrink-0 w-1 bg-border hover:bg-primary cursor-col-resize',
          'flex flex-col items-center justify-center',
          isMobile && 'hidden',
        )}
        aria-hidden="true"
      >
        {/* Left collapse button */}
        <button
          data-testid="collapse-left"
          onClick={collapseLeft}
          className={cn(
            'absolute left-0 top-1/2 -translate-y-1/2',
            'flex items-center justify-center',
            'w-4 h-8 rounded-r bg-border hover:bg-primary',
            'text-muted-foreground hover:text-primary-foreground',
            'transition-colors',
          )}
          aria-label={isLeftCollapsed ? 'Expand left pane' : 'Collapse left pane'}
        >
          {isLeftCollapsed ? (
            <ArrowRight01Icon className="h-3 w-3" />
          ) : (
            <ArrowLeft01Icon className="h-3 w-3" />
          )}
        </button>

        {/* Right collapse button */}
        <button
          data-testid="collapse-right"
          onClick={collapseRight}
          className={cn(
            'absolute right-0 top-1/2 -translate-y-1/2',
            'flex items-center justify-center',
            'w-4 h-8 rounded-l bg-border hover:bg-primary',
            'text-muted-foreground hover:text-primary-foreground',
            'transition-colors',
          )}
          aria-label={isRightCollapsed ? 'Expand right pane' : 'Collapse right pane'}
        >
          {isRightCollapsed ? (
            <ArrowLeft01Icon className="h-3 w-3" />
          ) : (
            <ArrowRight01Icon className="h-3 w-3" />
          )}
        </button>
      </div>

      {/* Right pane */}
      <div
        ref={rightPaneRef}
        data-testid="split-pane-right"
        style={isMobile ? undefined : { width: `${100 - splitPct}%` }}
        className={cn(
          'overflow-hidden flex-shrink-0',
          isMobile && 'h-[40%] w-full',
        )}
      >
        {right}
      </div>
    </div>
  );
}
