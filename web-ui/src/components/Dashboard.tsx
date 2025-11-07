/**
 * Main Dashboard Component
 */

'use client';

import { useEffect, useState, useMemo, useCallback } from 'react';
import useSWR from 'swr';
import { projectsApi, blockersApi } from '@/lib/api';
import { useAgentState } from '@/hooks/useAgentState';
import type { Project, Blocker, WebSocketMessage } from '@/types';
import type { PRDResponse, IssuesResponse } from '@/types/api';
import ChatInterface from './ChatInterface';
import PRDModal from './PRDModal';
import TaskTreeView from './TaskTreeView';
import DiscoveryProgress from './DiscoveryProgress';
import AgentCard from './AgentCard';

interface DashboardProps {
  projectId: number;
}

export default function Dashboard({ projectId }: DashboardProps) {
  // Use centralized agent state from Context (Phase 5.2)
  const { agents, tasks, activity, projectProgress, wsConnected } = useAgentState();

  const [showChat, setShowChat] = useState(false);
  const [showPRD, setShowPRD] = useState(false);

  // Memoize filtered agent lists for performance (T111)
  const activeAgents = useMemo(
    () => agents.filter(a => a.status === 'working' || a.status === 'blocked'),
    [agents]
  );

  const idleAgents = useMemo(
    () => agents.filter(a => a.status === 'idle'),
    [agents]
  );

  // Stable callback for agent click handler (T112)
  const handleAgentClick = useCallback((agentId: string) => {
    console.log('Agent clicked:', agentId);
  }, []);

  // Fetch project status
  const { data: projectData, mutate: mutateProject } = useSWR(
    `/projects/${projectId}/status`,
    () => projectsApi.getStatus(projectId).then((res) => res.data)
  );

  // Fetch blockers
  const { data: blockersData, mutate: mutateBlockers } = useSWR(
    `/projects/${projectId}/blockers`,
    () => blockersApi.list(projectId).then((res) => res.data.blockers)
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

      <main className="max-w-7xl mx-auto px-4 py-8 sm:px-6 lg:px-8">
        {/* Discovery Progress (cf-17.2) */}
        <DiscoveryProgress projectId={projectId} />

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

        {/* Blockers Section */}
        {blockersData && blockersData.length > 0 && (
          <div className="bg-white rounded-lg shadow p-6 mb-6">
            <h2 className="text-lg font-semibold mb-4">⚠️ Pending Questions</h2>
            <div className="space-y-4">
              {blockersData.map((blocker) => (
                <div
                  key={blocker.id}
                  className={`border-l-4 pl-4 ${
                    blocker.severity === 'sync' ? 'border-red-500' : 'border-yellow-500'
                  }`}
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <span
                          className={`text-xs px-2 py-0.5 rounded ${
                            blocker.severity === 'sync'
                              ? 'bg-red-100 text-red-800'
                              : 'bg-yellow-100 text-yellow-800'
                          }`}
                        >
                          {blocker.severity.toUpperCase()}
                        </span>
                        <span className="text-sm text-gray-500">Task #{blocker.task_id}</span>
                      </div>
                      <p className="mt-2 text-gray-900">{blocker.question}</p>
                      <p className="mt-1 text-sm text-gray-500">Reason: {blocker.reason}</p>
                      {blocker.blocking_agents && blocker.blocking_agents.length > 0 && (
                        <p className="mt-1 text-sm text-gray-500">
                          Blocking: {blocker.blocking_agents.join(', ')}
                        </p>
                      )}
                    </div>
                    <button className="ml-4 px-3 py-1 bg-blue-600 text-white text-sm rounded hover:bg-blue-700">
                      Answer Now
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

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
                    {item.type === 'tests_passed' && '🧪'}
                    {item.type === 'blocker_created' && '⚠️'}
                    {item.type === 'blocker_resolved' && '✓'}
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
      </main>

      {/* PRD Modal (cf-26) */}
      <PRDModal
        isOpen={showPRD}
        onClose={() => setShowPRD(false)}
        prdData={prdData || null}
      />
    </div>
  );
}