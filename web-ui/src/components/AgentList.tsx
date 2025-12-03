/**
 * Agent List Component
 *
 * Displays all agents assigned to a project with their roles, status, and metadata.
 * Supports empty state and integration with agent assignment API.
 *
 * Phase: Multi-Agent Per Project Architecture (Phase 3)
 * Date: 2025-12-03
 */

'use client';

import React, { useEffect, useState, useCallback } from 'react';
import useSWR from 'swr';
import { getAgentsForProject } from '@/api/agentAssignment';
import type { AgentAssignment } from '@/types/agentAssignment';
import { AgentAssignmentCard } from './AgentAssignmentCard';

interface AgentListProps {
  /** Project ID to fetch agents for */
  projectId: number;
  /** Callback when agent is clicked */
  onAgentClick?: (agentId: string) => void;
  /** Whether to show only active assignments (default: true) */
  showActiveOnly?: boolean;
  /** Refresh interval in milliseconds (default: 30000 = 30s) */
  refreshInterval?: number;
}

/**
 * Displays a list of agents assigned to a project.
 *
 * Features:
 * - Fetches agent assignments from API
 * - Shows agent role, status, and assignment metadata
 * - Auto-refreshes every 30 seconds
 * - Handles empty state (no agents assigned)
 * - Responsive grid layout
 *
 * @param projectId - Project ID to fetch agents for
 * @param onAgentClick - Callback when agent card is clicked
 * @param showActiveOnly - Filter to show only active assignments (default: true)
 * @param refreshInterval - Auto-refresh interval in milliseconds (default: 30000)
 */
export function AgentList({
  projectId,
  onAgentClick,
  showActiveOnly = true,
  refreshInterval = 30000,
}: AgentListProps) {
  const [error, setError] = useState<string | null>(null);

  // Fetch agent assignments from API
  const {
    data: assignments,
    error: fetchError,
    mutate,
  } = useSWR<AgentAssignment[]>(
    projectId ? `/projects/${projectId}/agents?active=${showActiveOnly}` : null,
    () => getAgentsForProject(projectId, showActiveOnly),
    {
      refreshInterval,
      revalidateOnFocus: false,
      revalidateOnReconnect: true,
    }
  );

  // Handle fetch errors
  useEffect(() => {
    if (fetchError) {
      setError(
        fetchError.message || 'Failed to load agent assignments. Please try again.'
      );
    } else {
      setError(null);
    }
  }, [fetchError]);

  // Handle agent card click
  const handleAgentClick = useCallback(
    (agentId: string) => {
      if (onAgentClick) {
        onAgentClick(agentId);
      }
    },
    [onAgentClick]
  );

  // Refresh assignments manually
  const handleRefresh = useCallback(() => {
    mutate();
  }, [mutate]);

  // Loading state
  if (!assignments && !error) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-center">
          <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
          <p className="mt-2 text-sm text-gray-500">Loading agents...</p>
        </div>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-lg p-4">
        <div className="flex items-start">
          <span className="text-red-600 text-xl mr-2">⚠️</span>
          <div>
            <h3 className="text-sm font-semibold text-red-800">
              Failed to Load Agents
            </h3>
            <p className="mt-1 text-sm text-red-700">{error}</p>
            <button
              onClick={handleRefresh}
              className="mt-2 text-sm text-red-600 hover:text-red-800 underline"
            >
              Try Again
            </button>
          </div>
        </div>
      </div>
    );
  }

  // Empty state
  if (!assignments || assignments.length === 0) {
    return (
      <div className="text-center py-12 bg-gray-50 rounded-lg border border-gray-200">
        <div className="inline-flex items-center justify-center w-16 h-16 bg-gray-200 rounded-full mb-4">
          <span className="text-3xl">🤖</span>
        </div>
        <h3 className="text-lg font-medium text-gray-900 mb-2">
          No Agents Assigned
        </h3>
        <p className="text-sm text-gray-500 max-w-sm mx-auto">
          {showActiveOnly
            ? 'No active agents are currently assigned to this project. Agents will be created automatically when tasks are assigned.'
            : 'No agents have been assigned to this project yet.'}
        </p>
      </div>
    );
  }

  // Success state - render agent cards
  return (
    <div>
      {/* Header with count and refresh button */}
      <div className="flex items-center justify-between mb-4">
        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
          {assignments.length} agent{assignments.length !== 1 ? 's' : ''} assigned
        </span>
        <button
          onClick={handleRefresh}
          className="text-xs text-gray-500 hover:text-gray-700 transition-colors"
          title="Refresh agent list"
        >
          🔄 Refresh
        </button>
      </div>

      {/* Agent cards grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {assignments.map((assignment) => (
          <AgentAssignmentCard
            key={assignment.agent_id}
            assignment={assignment}
            onClick={handleAgentClick}
          />
        ))}
      </div>
    </div>
  );
}

export default React.memo(AgentList);
