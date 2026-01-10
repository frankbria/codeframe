/**
 * Agent List Component
 *
 * Displays all agents assigned to a project with their roles, status, and metadata.
 * Supports empty state and integration with agent assignment API.
 *
 * Phase-aware: During planning phase, shows informational message instead of
 * "No agents assigned" since agents haven't been created yet.
 *
 * Phase: Multi-Agent Per Project Architecture (Phase 3)
 * Date: 2025-12-03
 * Updated: 2026-01-10 (Phase-Awareness Pattern)
 */

'use client';

import React, { useEffect, useState, useCallback } from 'react';
import useSWR from 'swr';
import { getAgentsForProject } from '@/api/agentAssignment';
import type { AgentAssignment } from '@/types/agentAssignment';
import type { IssuesResponse } from '@/types/api';
import { AgentAssignmentCard } from './AgentAssignmentCard';
import { isPlanningPhase, getPlanningPhaseMessage } from '@/lib/phaseAwareData';
import { BotIcon, CheckListIcon } from '@hugeicons/react';

interface AgentListProps {
  /** Project ID to fetch agents for */
  projectId: number;
  /** Callback when agent is clicked */
  onAgentClick?: (agentId: string) => void;
  /** Whether to show only active assignments (default: true) */
  showActiveOnly?: boolean;
  /** Refresh interval in milliseconds (default: 30000 = 30s) */
  refreshInterval?: number;
  /**
   * Current project phase. During 'planning' phase, shows informational
   * message instead of "No agents assigned" since agents are created
   * when development begins.
   */
  phase?: string;
  /**
   * Issues data from REST API, used during planning phase to show
   * task count in the phase-aware message.
   */
  issuesData?: IssuesResponse;
}

/**
 * Displays a list of agents assigned to a project.
 *
 * Features:
 * - Fetches agent assignments from API
 * - Shows agent role, status, and assignment metadata
 * - Auto-refreshes every 30 seconds
 * - Phase-aware empty state (planning vs development)
 * - Responsive grid layout
 *
 * @param projectId - Project ID to fetch agents for
 * @param onAgentClick - Callback when agent card is clicked
 * @param showActiveOnly - Filter to show only active assignments (default: true)
 * @param refreshInterval - Auto-refresh interval in milliseconds (default: 30000)
 * @param phase - Current project phase for phase-aware messaging
 * @param issuesData - Issues data for planning phase task count
 */
export function AgentList({
  projectId,
  onAgentClick,
  showActiveOnly = true,
  refreshInterval = 30000,
  phase,
  issuesData,
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
          <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
          <p className="mt-2 text-sm text-muted-foreground">Loading agents...</p>
        </div>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="bg-destructive/10 border border-destructive/20 rounded-lg p-4">
        <div className="flex items-start">
          <span className="text-destructive text-xl mr-2">⚠️</span>
          <div>
            <h3 className="text-sm font-semibold text-destructive">
              Failed to Load Agents
            </h3>
            <p className="mt-1 text-sm text-destructive/80">{error}</p>
            <button
              onClick={handleRefresh}
              className="mt-2 text-sm text-destructive hover:text-destructive/80 underline"
            >
              Try Again
            </button>
          </div>
        </div>
      </div>
    );
  }

  // Empty state - phase-aware messaging
  if (!assignments || assignments.length === 0) {
    // Planning phase: Show informational message (not "No Agents Assigned")
    // This fixes the "late-joining user" bug where users see misleading empty state
    if (isPlanningPhase(phase)) {
      return (
        <div
          className="text-center py-12 bg-primary/5 rounded-lg border border-primary/20"
          data-testid="planning-phase-message"
        >
          <div className="inline-flex items-center justify-center w-16 h-16 bg-primary/10 rounded-full mb-4">
            <BotIcon className="h-8 w-8 text-primary" />
          </div>
          <h3 className="text-lg font-medium text-foreground mb-2">
            Agents Ready for Development
          </h3>
          <p className="text-sm text-muted-foreground max-w-sm mx-auto mb-3">
            {getPlanningPhaseMessage('agent-list', issuesData)}
          </p>
          {issuesData && issuesData.total_tasks > 0 && (
            <div className="inline-flex items-center gap-2 px-3 py-1.5 bg-primary/10 rounded-full text-sm text-primary">
              <CheckListIcon className="h-4 w-4" />
              <span>{issuesData.total_tasks} tasks ready for agent assignment</span>
            </div>
          )}
        </div>
      );
    }

    // Default empty state (development/review phase)
    return (
      <div className="text-center py-12 bg-muted rounded-lg border border-border">
        <div className="inline-flex items-center justify-center w-16 h-16 bg-background rounded-full mb-4">
          <BotIcon className="h-8 w-8 text-muted-foreground" />
        </div>
        <h3 className="text-lg font-medium text-foreground mb-2">
          No Agents Assigned
        </h3>
        <p className="text-sm text-muted-foreground max-w-sm mx-auto">
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
        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-secondary text-secondary-foreground">
          {assignments.length} agent{assignments.length !== 1 ? 's' : ''} assigned
        </span>
        <button
          onClick={handleRefresh}
          className="text-xs text-muted-foreground hover:text-foreground transition-colors"
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
