/**
 * BlockerPanel Component (049-human-in-loop, T017)
 * Displays list of blockers with real-time updates
 */

'use client';

import { useMemo } from 'react';
import type { Blocker } from '../types/blocker';
import { BlockerBadge } from './BlockerBadge';

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

  // Filter for pending blockers only
  const pendingBlockers = useMemo(() => {
    return sortedBlockers.filter(b => b.status === 'PENDING');
  }, [sortedBlockers]);

  if (pendingBlockers.length === 0) {
    return (
      <div className="bg-white rounded-lg shadow p-4">
        <h2 className="text-lg font-semibold mb-3 text-gray-800">
          Blockers <span className="text-sm font-normal text-gray-500">(0)</span>
        </h2>
        <div className="text-center py-8 text-gray-500">
          <div className="text-4xl mb-2">✅</div>
          <p className="text-sm">No blockers - agents are running smoothly!</p>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-lg shadow">
      <div className="p-4 border-b border-gray-200">
        <h2 className="text-lg font-semibold text-gray-800">
          Blockers{' '}
          <span className="text-sm font-normal text-gray-500">
            ({pendingBlockers.length})
          </span>
        </h2>
      </div>

      <div className="divide-y divide-gray-200">
        {pendingBlockers.map((blocker) => (
          <button
            key={blocker.id}
            onClick={() => onBlockerClick?.(blocker)}
            className="w-full text-left p-4 hover:bg-gray-50 transition-colors duration-150 focus:outline-none focus:bg-gray-50"
          >
            <div className="flex items-start justify-between gap-3">
              <div className="flex-1 min-w-0">
                {/* Question preview */}
                <p className="text-sm font-medium text-gray-900 mb-1">
                  {truncateText(blocker.question, 80)}
                </p>

                {/* Agent and task info */}
                <div className="flex items-center gap-2 text-xs text-gray-500">
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
                <span className="text-xs text-gray-500 whitespace-nowrap">
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
