/**
 * Main Dashboard Component
 */

'use client';

import { useEffect, useState } from 'react';
import useSWR from 'swr';
import { projectsApi, agentsApi, blockersApi, activityApi } from '@/lib/api';
import { getWebSocketClient } from '@/lib/websocket';
import type { Project, Agent, Blocker, ActivityItem, WebSocketMessage } from '@/types';

interface DashboardProps {
  projectId: number;
}

export default function Dashboard({ projectId }: DashboardProps) {
  const [wsConnected, setWsConnected] = useState(false);

  // Fetch project status
  const { data: projectData, mutate: mutateProject } = useSWR(
    `/projects/${projectId}/status`,
    () => projectsApi.getStatus(projectId).then((res) => res.data)
  );

  // Fetch agents
  const { data: agentsData } = useSWR(
    `/projects/${projectId}/agents`,
    () => agentsApi.list(projectId).then((res) => res.data.agents)
  );

  // Fetch blockers
  const { data: blockersData, mutate: mutateBlockers } = useSWR(
    `/projects/${projectId}/blockers`,
    () => blockersApi.list(projectId).then((res) => res.data.blockers)
  );

  // Fetch activity
  const { data: activityData } = useSWR(
    `/projects/${projectId}/activity`,
    () => activityApi.list(projectId, 10).then((res) => res.data.activity)
  );

  // WebSocket connection
  useEffect(() => {
    const ws = getWebSocketClient();
    ws.connect();
    ws.subscribe(projectId);

    const unsubscribe = ws.onMessage((message: WebSocketMessage) => {
      if (message.type === 'status_update') {
        mutateProject();
      } else if (message.type === 'blocker_resolved') {
        mutateBlockers();
      }
      setWsConnected(true);
    });

    return () => {
      unsubscribe();
      ws.disconnect();
    };
  }, [projectId, mutateProject, mutateBlockers]);

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
                CodeFRAME - {projectData.project_name}
              </h1>
              <div className="flex items-center gap-4 mt-1">
                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
                  {projectData.status.toUpperCase()}
                </span>
                <span className="text-sm text-gray-500">
                  Phase: {projectData.phase} (Step {projectData.workflow_step}/15)
                </span>
                {wsConnected && (
                  <span className="inline-flex items-center gap-1 text-xs text-gray-500">
                    <span className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></span>
                    Live
                  </span>
                )}
              </div>
            </div>
            <div className="flex gap-2">
              <button className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700">
                Chat with Lead
              </button>
              <button className="px-4 py-2 border border-gray-300 rounded-md hover:bg-gray-50">
                Pause
              </button>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 py-8 sm:px-6 lg:px-8">
        {/* Progress Section */}
        <div className="bg-white rounded-lg shadow p-6 mb-6">
          <h2 className="text-lg font-semibold mb-4">Progress</h2>
          <div className="space-y-2">
            <div className="flex justify-between text-sm">
              <span>
                {projectData.progress.completed_tasks} / {projectData.progress.total_tasks} tasks
              </span>
              <span>{projectData.progress.percentage}%</span>
            </div>
            <div className="w-full bg-gray-200 rounded-full h-4">
              <div
                className="bg-blue-600 h-4 rounded-full transition-all"
                style={{ width: `${projectData.progress.percentage}%` }}
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

        {/* Agents Section */}
        <div className="bg-white rounded-lg shadow p-6 mb-6">
          <h2 className="text-lg font-semibold mb-4">🤖 Agent Status</h2>
          <div className="space-y-4">
            {agentsData?.map((agent) => (
              <div key={agent.id} className="border-l-4 border-gray-300 pl-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span
                      className={`w-3 h-3 rounded-full ${
                        agent.status === 'working'
                          ? 'bg-green-500'
                          : agent.status === 'blocked'
                          ? 'bg-red-500'
                          : 'bg-yellow-500'
                      }`}
                    ></span>
                    <span className="font-medium">
                      {agent.type.charAt(0).toUpperCase() + agent.type.slice(1)} Agent
                    </span>
                    <span className="text-xs text-gray-500">({agent.provider})</span>
                    <span className="text-xs px-2 py-0.5 bg-gray-100 rounded">
                      Maturity: {agent.maturity}
                    </span>
                  </div>
                  <span className="text-sm text-gray-500">
                    Status: {agent.status === 'working' ? '▶' : agent.status === 'blocked' ? '⏸' : '⏳'}{' '}
                    {agent.status}
                  </span>
                </div>
                {agent.current_task && (
                  <div className="mt-2 text-sm text-gray-600">
                    Task #{agent.current_task.id}: {agent.current_task.title}
                    {agent.progress !== undefined && (
                      <span className="ml-2 text-gray-500">({agent.progress}%)</span>
                    )}
                  </div>
                )}
                {agent.blocker && (
                  <div className="mt-1 text-sm text-red-600">⚠️ {agent.blocker}</div>
                )}
                {agent.context_tokens && (
                  <div className="mt-1 text-xs text-gray-500">
                    Context: {(agent.context_tokens / 1000).toFixed(0)}K tokens
                  </div>
                )}
              </div>
            ))}
          </div>
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
            {activityData?.map((item, index) => (
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
            ))}
          </div>
        </div>
      </main>
    </div>
  );
}
