/**
 * Agent Assignment Card Component
 *
 * Displays an individual agent's assignment details including role, status,
 * and assignment metadata for the multi-agent per project architecture.
 *
 * Phase: Multi-Agent Per Project Architecture (Phase 3)
 * Date: 2025-12-03
 */

'use client';

import React from 'react';
import type { AgentAssignment } from '@/types/agentAssignment';

interface AgentAssignmentCardProps {
  /** Agent assignment data */
  assignment: AgentAssignment;
  /** Callback when card is clicked */
  onClick?: (agentId: string) => void;
}

/**
 * Displays a single agent's assignment with role, status, and metadata.
 *
 * Features:
 * - Shows agent type, provider, and maturity level
 * - Displays role badge (e.g., "primary_backend", "code_reviewer")
 * - Status indicator with color coding
 * - Current task display (if working)
 * - Assignment timestamp
 * - Clickable for navigation to agent context view
 *
 * @param assignment - Agent assignment data from API
 * @param onClick - Callback when card is clicked
 */
const AgentAssignmentCardComponent: React.FC<AgentAssignmentCardProps> = ({
  assignment,
  onClick,
}) => {
  // Status color mapping
  const statusColors: Record<string, string> = {
    idle: 'bg-green-100 border-green-500 text-green-800',
    working: 'bg-yellow-100 border-yellow-500 text-yellow-800',
    blocked: 'bg-red-100 border-red-500 text-red-800',
    offline: 'bg-gray-100 border-gray-400 text-gray-600',
  };

  // Status indicator dot color
  const statusDotColors: Record<string, string> = {
    idle: 'bg-green-500',
    working: 'bg-yellow-500',
    blocked: 'bg-red-500',
    offline: 'bg-gray-400',
  };

  // Agent type badge colors
  const agentTypeBadges: Record<
    string,
    { bg: string; text: string; icon: string }
  > = {
    lead: { bg: 'bg-purple-100', text: 'text-purple-800', icon: '👑' },
    backend: { bg: 'bg-blue-100', text: 'text-blue-800', icon: '⚙️' },
    'backend-worker': { bg: 'bg-blue-100', text: 'text-blue-800', icon: '⚙️' },
    frontend: { bg: 'bg-pink-100', text: 'text-pink-800', icon: '🎨' },
    'frontend-specialist': {
      bg: 'bg-pink-100',
      text: 'text-pink-800',
      icon: '🎨',
    },
    test: { bg: 'bg-emerald-100', text: 'text-emerald-800', icon: '🧪' },
    'test-engineer': {
      bg: 'bg-emerald-100',
      text: 'text-emerald-800',
      icon: '🧪',
    },
    review: { bg: 'bg-indigo-100', text: 'text-indigo-800', icon: '🔍' },
  };

  const agentTypeBadge = agentTypeBadges[assignment.type] || {
    bg: 'bg-gray-100',
    text: 'text-gray-800',
    icon: '🤖',
  };

  // Format agent type for display
  const formatAgentType = (type: string): string => {
    if (!type) return 'Unknown';
    if (type.includes('-')) {
      return type
        .split('-')
        .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
        .join(' ');
    }
    return type.charAt(0).toUpperCase() + type.slice(1);
  };

  // Format role for display
  const formatRole = (role: string): string => {
    if (!role) return 'No Role';
    return role
      .split('_')
      .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
      .join(' ');
  };

  // Format timestamp
  const formatTimestamp = (timestamp: string | null): string => {
    if (!timestamp) return 'N/A';
    try {
      const date = new Date(timestamp);
      const now = new Date();
      const diffMs = now.getTime() - date.getTime();
      const diffMins = Math.floor(diffMs / 60000);
      const diffHours = Math.floor(diffMins / 60);
      const diffDays = Math.floor(diffHours / 24);

      if (diffMins < 1) return 'Just now';
      if (diffMins < 60) return `${diffMins}m ago`;
      if (diffHours < 24) return `${diffHours}h ago`;
      if (diffDays < 7) return `${diffDays}d ago`;
      return date.toLocaleDateString();
    } catch {
      return 'Invalid date';
    }
  };

  // Status text
  const statusText: Record<string, string> = {
    idle: 'Idle',
    working: 'Working',
    blocked: 'Blocked',
    offline: 'Offline',
  };

  const currentStatus = assignment.status || 'offline';
  const statusColor = statusColors[currentStatus] || statusColors.offline;
  const statusDot = statusDotColors[currentStatus] || statusDotColors.offline;

  return (
    <div
      className={`relative rounded-lg border-2 p-4 transition-all duration-200 hover:shadow-md cursor-pointer ${statusColor}`}
      onClick={() => onClick?.(assignment.agent_id)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          onClick?.(assignment.agent_id);
        }
      }}
    >
      {/* Agent Header */}
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2 flex-1 min-w-0">
          {/* Status Indicator Dot */}
          <div
            className={`w-3 h-3 rounded-full ${statusDot} ${
              currentStatus === 'working' ? 'animate-pulse' : ''
            }`}
            title={statusText[currentStatus]}
          />

          {/* Agent ID */}
          <h3
            className="font-semibold text-sm truncate"
            title={assignment.agent_id}
          >
            {assignment.agent_id}
          </h3>
        </div>

        {/* Status Badge */}
        <span className="px-2 py-0.5 rounded text-xs font-medium whitespace-nowrap ml-2">
          {statusText[currentStatus]}
        </span>
      </div>

      {/* Agent Type Badge */}
      <div className="mb-3">
        <span
          className={`inline-flex items-center gap-1 px-2 py-1 rounded text-xs font-medium ${agentTypeBadge.bg} ${agentTypeBadge.text}`}
        >
          <span>{agentTypeBadge.icon}</span>
          <span>{formatAgentType(assignment.type)}</span>
        </span>
      </div>

      {/* Role Badge */}
      <div className="mb-3">
        <div className="text-xs text-gray-600 mb-1">Role:</div>
        <span className="inline-flex items-center px-2 py-1 rounded text-xs font-medium bg-white bg-opacity-70">
          {formatRole(assignment.role)}
        </span>
      </div>

      {/* Provider & Maturity Level */}
      {(assignment.provider || assignment.maturity_level) && (
        <div className="mb-3 p-2 bg-white bg-opacity-50 rounded">
          {assignment.provider && (
            <div className="text-xs">
              <span className="text-gray-600">Provider:</span>{' '}
              <span className="font-medium">{assignment.provider}</span>
            </div>
          )}
          {assignment.maturity_level && (
            <div className="text-xs mt-1">
              <span className="text-gray-600">Maturity:</span>{' '}
              <span className="font-medium capitalize">
                {assignment.maturity_level}
              </span>
            </div>
          )}
        </div>
      )}

      {/* Current Task (if working) */}
      {currentStatus === 'working' && assignment.current_task_id && (
        <div className="mb-3 p-2 bg-white bg-opacity-50 rounded">
          <div className="text-xs text-gray-600 mb-1">Current Task:</div>
          <div className="text-sm font-medium">
            Task #{assignment.current_task_id}
          </div>
        </div>
      )}

      {/* Last Activity */}
      {assignment.last_heartbeat && (
        <div className="mb-3 p-2 bg-white bg-opacity-50 rounded">
          <div className="text-xs text-gray-600 mb-1">Last Activity:</div>
          <div className="text-xs font-medium">
            {formatTimestamp(assignment.last_heartbeat)}
          </div>
        </div>
      )}

      {/* Assignment Info */}
      <div className="flex items-center justify-between pt-3 border-t border-current border-opacity-20">
        <span className="text-xs text-gray-600">Assigned</span>
        <span className="text-xs font-medium">
          {formatTimestamp(assignment.assigned_at)}
        </span>
      </div>

      {/* Active Indicator */}
      {assignment.is_active && (
        <div className="mt-2 text-xs text-center font-medium">
          ✓ Active Assignment
        </div>
      )}
    </div>
  );
};

// Memoize component to prevent unnecessary re-renders
export const AgentAssignmentCard = React.memo(
  AgentAssignmentCardComponent,
  (prevProps, nextProps) => {
    // Only re-render if assignment changed
    const prev = prevProps.assignment;
    const next = nextProps.assignment;

    return (
      prev.agent_id === next.agent_id &&
      prev.status === next.status &&
      prev.role === next.role &&
      prev.current_task_id === next.current_task_id &&
      prev.last_heartbeat === next.last_heartbeat &&
      prev.is_active === next.is_active
    );
  }
);

AgentAssignmentCard.displayName = 'AgentAssignmentCard';

export default AgentAssignmentCard;
