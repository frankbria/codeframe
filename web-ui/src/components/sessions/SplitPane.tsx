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

function readStorage(key: string, fallback: number, min: number, max: number): number {
  const normalizedFallback = clamp(fallback, min, max);
  try {
    const raw = localStorage.getItem(key);
    if (raw !== null) {
      const parsed = Number(raw);
      if (Number.isFinite(parsed)) {
        // Reject collapsed sentinels — restore to valid expanded position
        if (parsed === 0 || parsed === 100) return normalizedFallback;
        return clamp(parsed, min, max);
      }
    }
  } catch {
    // localStorage unavailable (SSR, private browsing, etc.)
  }
  return normalizedFallback;
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
    readStorage(storageKey, defaultSplit, minPanePercent, 100 - minPanePercent),
  );
  const [isLeftCollapsed, setIsLeftCollapsed] = useState(false);
  const [isRightCollapsed, setIsRightCollapsed] = useState(false);
  // null = not yet determined (avoids SSR/hydration flash)
  const [isMobile, setIsMobile] = useState<boolean | null>(null);

  const containerRef = useRef<HTMLDivElement>(null);
  const leftPaneRef = useRef<HTMLDivElement>(null);
  const rightPaneRef = useRef<HTMLDivElement>(null);
  const isDragging = useRef(false);
  const dragMoved = useRef(false);
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

  useEffect(() => {
    applyWidths(splitPct);
  }, [splitPct, applyWidths]);

  // ── Shared commit helper (drag end + keyboard) ────────────────────────

  const commitExpandedSplit = useCallback(
    (next: number) => {
      transitionEnabled.current = false;
      livePercent.current = next;
      lastNonCollapsed.current = next;
      setIsLeftCollapsed(false);
      setIsRightCollapsed(false);
      setSplitPct(next);
      writeStorage(storageKey, next);
    },
    [storageKey],
  );

  // ── Drag logic ────────────────────────────────────────────────────────

  useEffect(() => {
    const onMouseMove = (e: MouseEvent) => {
      if (!isDragging.current || !containerRef.current) return;
      dragMoved.current = true;
      const rect = containerRef.current.getBoundingClientRect();
      const rawPct = ((e.clientX - rect.left) / rect.width) * 100;
      const clamped = clamp(rawPct, minPanePercent, 100 - minPanePercent);
      livePercent.current = clamped;
      if (leftPaneRef.current) leftPaneRef.current.style.width = `${clamped}%`;
      if (rightPaneRef.current) rightPaneRef.current.style.width = `${100 - clamped}%`;
    };

    const onMouseUp = () => {
      if (!isDragging.current) return;
      isDragging.current = false;
      // Only commit if the divider actually moved — plain clicks must not reopen collapsed panes
      if (dragMoved.current) {
        commitExpandedSplit(livePercent.current);
      }
      dragMoved.current = false;
    };

    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('mouseup', onMouseUp);
    return () => {
      document.removeEventListener('mousemove', onMouseMove);
      document.removeEventListener('mouseup', onMouseUp);
    };
  }, [minPanePercent, commitExpandedSplit]);

  const onDividerMouseDown = () => {
    isDragging.current = true;
    dragMoved.current = false;
    livePercent.current = splitPct; // reset so a no-move click never commits a stale value
    transitionEnabled.current = false;
    if (leftPaneRef.current) leftPaneRef.current.style.transition = '';
    if (rightPaneRef.current) rightPaneRef.current.style.transition = '';
  };

  // ── Keyboard resize ───────────────────────────────────────────────────

  const onDividerKeyDown = (e: React.KeyboardEvent) => {
    const step = 5;
    if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
    e.preventDefault();
    // At collapsed sentinels, only allow inward keypress to restore
    if (splitPct === 0) {
      if (e.key === 'ArrowLeft') return; // no-op: already fully left
      commitExpandedSplit(minPanePercent);
      return;
    }
    if (splitPct === 100) {
      if (e.key === 'ArrowRight') return; // no-op: already fully right
      commitExpandedSplit(100 - minPanePercent);
      return;
    }
    const delta = e.key === 'ArrowLeft' ? -step : step;
    commitExpandedSplit(clamp(splitPct + delta, minPanePercent, 100 - minPanePercent));
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
      // Only save a valid expanded position as the restore point
      if (splitPct >= minPanePercent && splitPct <= 100 - minPanePercent) {
        lastNonCollapsed.current = splitPct;
      }
      setIsLeftCollapsed(true);
      setIsRightCollapsed(false);
      setSplitPct(0);
      // Do not write 0 to storage — preserve last valid position for next reload
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
      // Only save a valid expanded position as the restore point
      if (splitPct >= minPanePercent && splitPct <= 100 - minPanePercent) {
        lastNonCollapsed.current = splitPct;
      }
      setIsRightCollapsed(true);
      setIsLeftCollapsed(false);
      setSplitPct(100);
      // Do not write 100 to storage — preserve last valid position for next reload
    }
  };

  // ── Render ────────────────────────────────────────────────────────────

  // Avoid hydration mismatch: render nothing until mobile detection is resolved
  if (isMobile === null) return null;

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

      {/* Divider — role="separator" exposes collapse buttons to AT */}
      <div
        data-testid="split-pane-divider"
        onMouseDown={onDividerMouseDown}
        onKeyDown={onDividerKeyDown}
        role="separator"
        aria-orientation="vertical"
        aria-valuenow={splitPct}
        aria-valuemin={splitPct === 0 ? 0 : minPanePercent}
        aria-valuemax={splitPct === 100 ? 100 : 100 - minPanePercent}
        aria-label="Resize panes"
        tabIndex={0}
        className={cn(
          'relative flex-shrink-0 w-1 bg-border hover:bg-primary cursor-col-resize',
          'flex flex-col items-center justify-center',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
          isMobile && 'hidden',
        )}
      >
        {/* Left collapse button */}
        <button
          type="button"
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
          type="button"
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
