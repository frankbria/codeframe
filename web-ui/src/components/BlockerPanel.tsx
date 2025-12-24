/**
 * BlockerPanel Component (049-human-in-loop, T017)
 * Displays list of blockers with real-time updates
 * Supports filtering (T068) and sorting (T067)
 */

'use client';

import { useMemo, useState } from 'react';
import type { Blocker } from '../types/blocker';
import { BlockerBadge } from './BlockerBadge';

type BlockerFilter = 'all' | 'sync' | 'async';

interface BlockerPanelProps {
  blockers: Blocker[];
  onBlockerClick?: (blocker: Blocker) => void;
}

function formatTimeAgo(ms: number): string {
  const seconds = Math.floor(ms / 1000);
  const minutes = Math.floor(seconds / 60);
  const hours = Math.floor(minutes / 60);
  const days = Math.floor(hours / 24);

  if (days > 0) return `${days}d ago`;
  if (hours > 0) return `${hours}h ago`;
  if (minutes > 0) return `${minutes}m ago`;
  return 'Just now';
}

function truncateText(text: string, maxLength: number): string {
  if (text.length <= maxLength) return text;
  return text.substring(0, maxLength) + '...';
}

export default function BlockerPanel({ blockers, onBlockerClick }: BlockerPanelProps) {
  // Filter state (T068)
  const [filter, setFilter] = useState<BlockerFilter>('all');

  // Sort blockers: SYNC first, then by created_at DESC (T067)
  const sortedBlockers = useMemo(() => {
    return [...blockers].sort((a, b) => {
      // SYNC blockers come first
      if (a.blocker_type === 'SYNC' && b.blocker_type !== 'SYNC') return -1;
      if (a.blocker_type !== 'SYNC' && b.blocker_type === 'SYNC') return 1;

      // Within same type, sort by created_at DESC (newest first)
      return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
    });
  }, [blockers]);

  // Filter for pending blockers only, then apply type filter (T068)
  const filteredBlockers = useMemo(() => {
    const pending = sortedBlockers.filter(b => b.status === 'PENDING');

    if (filter === 'sync') {
      return pending.filter(b => b.blocker_type === 'SYNC');
    } else if (filter === 'async') {
      return pending.filter(b => b.blocker_type === 'ASYNC');
    }
    return pending;
  }, [sortedBlockers, filter]);

  // Alias for backwards compatibility
  const pendingBlockers = filteredBlockers;

  if (pendingBlockers.length === 0) {
    return (
      <div className="bg-card rounded-lg shadow p-4 border border-border">
        <h2 className="text-lg font-semibold mb-3 text-foreground">
          Blockers <span className="text-sm font-normal text-muted-foreground">(0)</span>
        </h2>
        <div className="text-center py-8 text-muted-foreground">
          <div className="text-4xl mb-2">✅</div>
          <p className="text-sm">No blockers - agents are running smoothly!</p>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-card rounded-lg shadow border border-border">
      <div className="p-4 border-b border-border">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-semibold text-foreground">
            Blockers{' '}
            <span className="text-sm font-normal text-muted-foreground">
              ({pendingBlockers.length})
            </span>
          </h2>
        </div>

        {/* Filter buttons (T068) */}
        <div className="flex gap-2">
          <button
            onClick={() => setFilter('all')}
            className={`px-3 py-1 text-xs font-medium rounded-md transition-colors ${
              filter === 'all'
                ? 'bg-primary text-primary-foreground'
                : 'bg-muted text-foreground hover:bg-muted/80'
            }`}
          >
            All
          </button>
          <button
            onClick={() => setFilter('sync')}
            className={`px-3 py-1 text-xs font-medium rounded-md transition-colors ${
              filter === 'sync'
                ? 'bg-destructive text-destructive-foreground'
                : 'bg-muted text-foreground hover:bg-muted/80'
            }`}
          >
            SYNC
          </button>
          <button
            onClick={() => setFilter('async')}
            className={`px-3 py-1 text-xs font-medium rounded-md transition-colors ${
              filter === 'async'
                ? 'bg-accent text-accent-foreground'
                : 'bg-muted text-foreground hover:bg-muted/80'
            }`}
          >
            ASYNC
          </button>
        </div>
      </div>

      <div className="divide-y divide-border">
        {pendingBlockers.map((blocker) => (
          <button
            key={blocker.id}
            onClick={() => onBlockerClick?.(blocker)}
            className="w-full text-left p-4 hover:bg-muted/50 transition-colors duration-150 focus:outline-none focus:bg-muted/50"
          >
            <div className="flex items-start justify-between gap-3">
              <div className="flex-1 min-w-0">
                {/* Question preview */}
                <p className="text-sm font-medium text-foreground mb-1">
                  {truncateText(blocker.question, 80)}
                </p>

                {/* Agent and task info */}
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <span className="inline-flex items-center gap-1">
                    <span>🤖</span>
                    <span>{blocker.agent_name || blocker.agent_id}</span>
                  </span>
                  {blocker.task_title && (
                    <>
                      <span>•</span>
                      <span className="truncate max-w-[200px]">
                        {blocker.task_title}
                      </span>
                    </>
                  )}
                </div>
              </div>

              {/* Right side: Badge and time */}
              <div className="flex flex-col items-end gap-2 flex-shrink-0">
                <BlockerBadge type={blocker.blocker_type} />
                <span className="text-xs text-muted-foreground whitespace-nowrap">
                  {formatTimeAgo(blocker.time_waiting_ms || 0)}
                </span>
              </div>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
