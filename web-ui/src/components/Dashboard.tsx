/**
 * Main Dashboard Component
 */

'use client';

import { useEffect, useState, useMemo, useCallback } from 'react';
import useSWR from 'swr';
import { projectsApi, blockersApi } from '@/lib/api';
import { useAgentState } from '@/hooks/useAgentState';
import type { Project, WebSocketMessage } from '@/types';
import type { Blocker } from '@/types/blocker';
import type { PRDResponse, IssuesResponse } from '@/types/api';
import type { DashboardTab } from '@/types/dashboard';
import { getWebSocketClient } from '@/lib/websocket';
import ChatInterface from './ChatInterface';
import PRDModal from './PRDModal';
import TaskTreeView from './TaskTreeView';
import DiscoveryProgress from './DiscoveryProgress';
import AgentCard from './AgentCard';
import BlockerPanel from './BlockerPanel';
import { BlockerModal } from './BlockerModal';
import ReviewResultsPanel from './review/ReviewResultsPanel';
import { LintTrendChart } from './lint/LintTrendChart';
import { ContextPanel } from './context/ContextPanel';
import { SessionStatus } from './SessionStatus';

interface DashboardProps {
  projectId: number;
}

/**
 * Render the main dashboard UI for a given project, including Overview and Context tabs.
 *
 * The component orchestrates data fetching (project status, blockers, PRD, issues), derives
 * agent lists, and renders progress, issues, agents, blockers, recent activity, and context
 * views. It also subscribes to real-time events to refresh blockers and open review panels.
 *
 * @param projectId - The numeric ID of the project to display
 * @returns The dashboard's rendered React element
 */
export default function Dashboard({ projectId }: DashboardProps) {
  // Tab state management (T008 - Feature 013)
  const [activeTab, setActiveTab] = useState<DashboardTab>('overview');
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);

  // Use centralized agent state from Context (Phase 5.2)
  const { agents, tasks, activity, projectProgress, wsConnected } = useAgentState();

  const [showChat, setShowChat] = useState(false);
  const [showPRD, setShowPRD] = useState(false);
  const [selectedBlocker, setSelectedBlocker] = useState<Blocker | null>(null);
  const [selectedTaskForReview, setSelectedTaskForReview] = useState<number | null>(null);

  // Memoize filtered agent lists for performance (T111)
  const activeAgents = useMemo(
    () => agents.filter(a => a.status === 'working' || a.status === 'blocked'),
    [agents]
  );

  const idleAgents = useMemo(
    () => agents.filter(a => a.status === 'idle'),
    [agents]
  );

  // Stable callback for agent click handler (T112, T032-T033 - Feature 013)
  const handleAgentClick = useCallback((agentId: string) => {
    // Navigate to Context tab and select the clicked agent
    setSelectedAgentId(agentId);
    setActiveTab('context');
  }, []);

  // Fetch project status
  const { data: projectData, mutate: mutateProject } = useSWR(
    `/projects/${projectId}/status`,
    () => projectsApi.getStatus(projectId).then((res) => res.data)
  );

  // Fetch blockers
  const { data: blockersData, mutate: mutateBlockers } = useSWR(
    `/projects/${projectId}/blockers`,
    () => blockersApi.list(projectId).then((res) => res.data?.blockers || [])
  );

  // Fetch PRD data (cf-26)
  const { data: prdData } = useSWR<PRDResponse>(
    `/projects/${projectId}/prd`,
    () => projectsApi.getPRD(projectId).then((res) => res.data),
    { shouldRetryOnError: false }
  );

  // Fetch issues/tasks data (cf-26)
  const { data: issuesData } = useSWR<IssuesResponse>(
    `/projects/${projectId}/issues`,
    () => projectsApi.getIssues(projectId).then((res) => res.data),
    { shouldRetryOnError: false }
  );

  // WebSocket connection and real-time updates are now handled by AgentStateProvider (Phase 5.2)
  // All WebSocket message handling, state updates, and reconnection logic moved to Provider

  // WebSocket handler for blocker lifecycle events (T018, T033, T034, 049-human-in-loop)
  useEffect(() => {
    const ws = getWebSocketClient();

    const handleBlockerEvent = (message: any) => {
      if (message.type === 'blocker_created' || message.type === 'blocker_resolved' || message.type === 'blocker_expired') {
        // Refresh blockers list when blocker events occur
        mutateBlockers();
      }

      // Handle agent_resumed event (T033, T034)
      if (message.type === 'agent_resumed') {
        // Agent status card will be automatically updated by AgentStateProvider
        // Add activity feed entry for agent resume (T034)
        console.log(`Agent ${message.agent_id} resumed after blocker ${message.blocker_id} resolved`);
      }

      // Handle review events (T059, Sprint 9 Phase 3)
      if (message.type === 'review_approved' ||
          message.type === 'review_changes_requested' ||
          message.type === 'review_rejected') {
        // Auto-open review panel when review completes
        if (message.task_id) {
          setSelectedTaskForReview(message.task_id);
        }
      }
    };

    // onMessage returns a cleanup function that removes the handler
    const unsubscribe = ws.onMessage(handleBlockerEvent);

    return () => {
      unsubscribe();
    };
  }, [mutateBlockers]);

  if (!projectData) {
    return <div className="p-8 text-center">Loading...</div>;
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-4 py-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold text-gray-900">
                CodeFRAME - {projectData.name}
              </h1>
              <div className="flex items-center gap-4 mt-1">
                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
                  {projectData.status.toUpperCase()}
                </span>
                <span className="text-sm text-gray-500">
                  Phase: {projectData.phase} (Step {projectData.workflow_step}/15)
                </span>
                {/* Connection status from AgentStateProvider */}
                {wsConnected ? (
                  <span className="inline-flex items-center gap-1 text-xs text-green-600">
                    <span className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></span>
                    Connected
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 text-xs text-red-600">
                    <span className="w-2 h-2 bg-red-500 rounded-full"></span>
                    Disconnected
                  </span>
                )}
              </div>
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => setShowPRD(true)}
                className="px-4 py-2 border border-gray-300 rounded-md hover:bg-gray-50 transition-colors"
              >
                View PRD
              </button>
              <button
                onClick={() => setShowChat(!showChat)}
                className={`px-4 py-2 rounded-md transition-colors ${
                  showChat
                    ? 'bg-blue-700 text-white hover:bg-blue-800'
                    : 'bg-blue-600 text-white hover:bg-blue-700'
                }`}
              >
                {showChat ? 'Hide Chat' : 'Chat with Lead'}
              </button>
              <button className="px-4 py-2 border border-gray-300 rounded-md hover:bg-gray-50">
                Pause
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* Tab Navigation (T009 - Feature 013) */}
      <div className="bg-white border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <nav className="-mb-px flex space-x-8" role="tablist" aria-label="Dashboard tabs">
            <button
              role="tab"
              aria-selected={activeTab === 'overview'}
              aria-controls="overview-panel"
              onClick={() => setActiveTab('overview')}
              className={`py-4 px-1 border-b-2 font-medium text-sm transition-colors ${
                activeTab === 'overview'
                  ? 'border-blue-600 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              }`}
            >
              Overview
            </button>
            <button
              role="tab"
              aria-selected={activeTab === 'context'}
              aria-controls="context-panel"
              onClick={() => setActiveTab('context')}
              className={`py-4 px-1 border-b-2 font-medium text-sm transition-colors ${
                activeTab === 'context'
                  ? 'border-blue-600 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              }`}
            >
              Context
            </button>
          </nav>
        </div>
      </div>

      <main className="max-w-7xl mx-auto px-4 py-8 sm:px-6 lg:px-8">
        {/* Overview Tab Panel (T010 - Feature 013) */}
        {activeTab === 'overview' && (
          <div role="tabpanel" id="overview-panel" aria-labelledby="overview-tab">
            {/* Discovery Progress (cf-17.2) */}
            <DiscoveryProgress projectId={projectId} />

            {/* Session Status (T029, 014-session-lifecycle) */}
            <div className="mb-6">
              <SessionStatus projectId={projectId} />
            </div>

            {/* Chat Interface (cf-14.2) */}
            {showChat && (
              <div className="mb-6" style={{ height: '500px' }}>
                <ChatInterface
                  projectId={projectId}
                  agentStatus={agents.find((a) => a.type === 'lead')?.status}
                />
              </div>
            )}

            {/* Progress Section */}
            <div className="bg-white rounded-lg shadow p-6 mb-6">
              <h2 className="text-lg font-semibold mb-4">Progress</h2>
              <div className="space-y-2">
                <div className="flex justify-between text-sm">
                  <span>
                    {(projectProgress || projectData.progress).completed_tasks} /{' '}
                    {(projectProgress || projectData.progress).total_tasks} tasks
                  </span>
                  <span>{(projectProgress || projectData.progress).percentage}%</span>
                </div>
                <div className="w-full bg-gray-200 rounded-full h-4">
                  <div
                    className="bg-blue-600 h-4 rounded-full transition-all duration-500"
                    style={{ width: `${(projectProgress || projectData.progress).percentage}%` }}
                  ></div>
                </div>
              </div>

              {projectData.time_tracking && (
                <div className="grid grid-cols-2 gap-4 mt-4 text-sm">
                  <div>
                    <span className="text-gray-500">Elapsed:</span>{' '}
                    <span className="font-medium">
                      {projectData.time_tracking.elapsed_hours.toFixed(1)}h
                    </span>
                  </div>
                  <div>
                    <span className="text-gray-500">Remaining:</span>{' '}
                    <span className="font-medium">
                      ~{projectData.time_tracking.estimated_remaining_hours.toFixed(1)}h
                    </span>
                  </div>
                </div>
              )}

              {projectData.cost_tracking && (
                <div className="mt-4 text-sm border-t pt-4">
                  <div className="flex justify-between">
                    <span className="text-gray-500">
                      Tokens: {(projectData.cost_tracking.input_tokens / 1000000).toFixed(1)}M input,{' '}
                      {(projectData.cost_tracking.output_tokens / 1000).toFixed(0)}K output
                    </span>
                    <span className="font-medium">
                      Est. cost: ${projectData.cost_tracking.estimated_cost.toFixed(2)}
                    </span>
                  </div>
                </div>
              )}
            </div>

            {/* Issues & Tasks Section (cf-26) */}
            <div className="bg-white rounded-lg shadow p-6 mb-6">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-semibold">🎯 Issues & Tasks</h2>
                {issuesData && (
                  <span className="text-sm text-gray-500">
                    {issuesData.total_issues} issues, {issuesData.total_tasks} tasks
                  </span>
                )}
              </div>
              <TaskTreeView issues={issuesData?.issues || []} />
            </div>

            {/* Agents Section */}
            <div className="bg-white rounded-lg shadow p-6 mb-6">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-semibold">🤖 Multi-Agent Pool</h2>
                {agents.length > 0 && (
                  <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                    {agents.length} agents active
                  </span>
                )}
              </div>
              
              {agents.length > 0 ? (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                  {agents.map((agent) => (
                    <AgentCard
                      key={agent.id}
                      agent={{
                        id: agent.id,
                        type: agent.type,
                        status: agent.status === 'working' ? 'busy' : agent.status === 'blocked' ? 'blocked' : 'idle',
                        currentTask: agent.current_task?.id,
                        tasksCompleted: agent.tasks_completed || 0,
                        blockedBy: agent.blocker ? [0] : undefined,
                      }}
                      onAgentClick={handleAgentClick}
                    />
                  ))}
                </div>
              ) : (
                <div className="text-center py-8 text-gray-500">
                  No agents active yet. Agents will be created automatically when tasks are assigned.
                </div>
              )}
            </div>

            {/* Blockers Section (T020, 049-human-in-loop) */}
            <div className="mb-6">
              <BlockerPanel
                blockers={(blockersData || []) as unknown as Blocker[]}
                onBlockerClick={(blocker) => setSelectedBlocker(blocker)}
              />
            </div>

            {/* Review Results Section (T065, Sprint 9 Phase 3) */}
            {selectedTaskForReview && (
              <div className="mb-6">
                <ReviewResultsPanel
                  taskId={selectedTaskForReview}
                  onClose={() => setSelectedTaskForReview(null)}
                />
              </div>
            )}

            {/* Lint Quality Trend (T124, Sprint 9 Phase 5) */}
            <div className="mb-6">
              <LintTrendChart
                projectId={projectId}
                days={7}
                refreshInterval={30000}
              />
            </div>

            {/* Recent Activity */}
            <div className="bg-white rounded-lg shadow p-6">
              <h2 className="text-lg font-semibold mb-4">📝 Recent Activity</h2>
              <div className="space-y-2">
                {activity.length > 0 ? (
                  activity.map((item, index) => (
                    <div key={index} className="flex items-start gap-3 text-sm">
                      <span className="text-gray-400 min-w-[60px]">
                        {new Date(item.timestamp).toLocaleTimeString()}
                      </span>
                      <span className="flex-1">
                        {item.type === 'task_completed' && '✅'}
                        {item.type === 'test_result' && '🧪'}
                        {item.type === 'task_blocked' && '⚠️'}
                        {item.type === 'task_unblocked' && '✓'}
                        {item.type === 'agent_created' && '🤖'}
                        {item.type === 'agent_retired' && '👋'}
                        {item.type === 'commit_created' && '💾'}
                        {' '}
                        <span className="font-medium">{item.agent}:</span> {item.message}
                      </span>
                    </div>
                  ))
                ) : (
                  <div className="text-center py-4 text-gray-500">
                    No recent activity
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Context Tab Panel (T011 - Feature 013) */}
        {activeTab === 'context' && (
          <div role="tabpanel" id="context-panel" aria-labelledby="context-tab">
            <div className="bg-white rounded-lg shadow p-6">
              {/* Agent Selector (T016-T019 - Feature 013) */}
              <div className="mb-6">
                <label
                  htmlFor="agent-selector"
                  className="block text-sm font-medium text-gray-700 mb-2"
                >
                  Select Agent
                </label>
                <select
                  id="agent-selector"
                  aria-label="Select agent"
                  value={selectedAgentId || ''}
                  onChange={(e) => setSelectedAgentId(e.target.value || null)}
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                >
                  <option value="">-- Select an agent --</option>
                  {agents.map((agent) => (
                    <option key={agent.id} value={agent.id}>
                      {agent.type} ({agent.status})
                    </option>
                  ))}
                </select>
              </div>

              {/* ContextPanel (T024-T027 - Feature 013) */}
              {selectedAgentId ? (
                <ContextPanel
                  agentId={selectedAgentId}
                  projectId={projectId}
                  refreshInterval={5000}
                />
              ) : (
                <div className="text-center py-12 text-gray-500">
                  <p className="text-lg mb-2">Select an agent to view context</p>
                  <p className="text-sm">
                    Context items show what's in agent memory (HOT/WARM/COLD tiers)
                  </p>
                </div>
              )}
            </div>
          </div>
        )}
      </main>

      {/* PRD Modal (cf-26) */}
      <PRDModal
        isOpen={showPRD}
        onClose={() => setShowPRD(false)}
        prdData={prdData || null}
      />

      {/* Blocker Resolution Modal (T025, 049-human-in-loop) */}
      <BlockerModal
        isOpen={selectedBlocker !== null}
        blocker={selectedBlocker}
        onClose={() => setSelectedBlocker(null)}
        onResolved={() => mutateBlockers()}
      />
    </div>
  );
}