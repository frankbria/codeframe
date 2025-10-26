/**
 * Main Dashboard Component
 */

'use client';

import { useEffect, useState } from 'react';
import useSWR from 'swr';
import { projectsApi, agentsApi, blockersApi, activityApi } from '@/lib/api';
import { getWebSocketClient } from '@/lib/websocket';
import type { Project, Agent, Blocker, ActivityItem, WebSocketMessage, Task, TaskStatus, AgentStatus } from '@/types';
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
  const [wsConnected, setWsConnected] = useState(false);
  const [showChat, setShowChat] = useState(false);
  const [showPRD, setShowPRD] = useState(false);

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

  // Local state for real-time updates (cf-45)
  const [tasks, setTasks] = useState<Task[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [activity, setActivity] = useState<ActivityItem[]>([]);
  const [projectProgress, setProjectProgress] = useState<any>(null);

  // Initialize local state from API data
  useEffect(() => {
    if (agentsData) {
      setAgents(agentsData);
    }
  }, [agentsData]);

  useEffect(() => {
    if (activityData) {
      setActivity(activityData);
    }
  }, [activityData]);

  // WebSocket connection (cf-45)
  useEffect(() => {
    const ws = getWebSocketClient();
    ws.connect();
    ws.subscribe(projectId);

    const unsubscribe = ws.onMessage((message: WebSocketMessage) => {
      // Only process messages for this project
      if (message.project_id && message.project_id !== projectId) {
        return;
      }

      // Handle different message types
      switch (message.type) {
        case 'task_status_changed':
          // Update task status in real-time
          if (message.task_id && message.status) {
            setTasks((prev) =>
              prev.map((task) =>
                task.id === message.task_id
                  ? { ...task, status: message.status as TaskStatus, progress: message.progress }
                  : task
              )
            );
          }
          break;

        case 'agent_status_changed':
          // Update agent status in real-time
          if (message.agent_id && message.status) {
            setAgents((prev) =>
              prev.map((agent) =>
                agent.id === message.agent_id
                  ? {
                      ...agent,
                      status: message.status as AgentStatus,
                      current_task: message.current_task,
                      progress: message.progress,
                    }
                  : agent
              )
            );
          }
          break;

        case 'test_result':
          // Add test result to activity feed
          if (message.task_id) {
            const passed = message.passed ?? 0;
            const total = message.total ?? 0;
            const testMessage =
              message.status === 'passed'
                ? `✅ All tests passed (${passed}/${total})`
                : `⚠️ Tests ${message.status} (${passed}/${total} passed)`;

            setActivity((prev) => [
              {
                timestamp: message.timestamp,
                type: 'test_result',
                agent: 'test-runner',
                message: testMessage,
              },
              ...prev.slice(0, 49), // Keep only 50 items
            ]);
          }
          break;

        case 'commit_created':
          // Add commit to activity feed
          if (message.commit_hash && message.commit_message) {
            const commitHash = message.commit_hash.substring(0, 7);
            setActivity((prev) => [
              {
                timestamp: message.timestamp,
                type: 'commit_created',
                agent: 'backend-worker',
                message: `📝 ${message.commit_message} (${commitHash})`,
              },
              ...prev.slice(0, 49),
            ]);
          }
          break;

        case 'activity_update':
          // Add activity to feed
          if (message.message) {
            const activityMessage = message.message;
            setActivity((prev) => [
              {
                timestamp: message.timestamp,
                type: message.activity_type || 'activity',
                agent: message.agent || 'system',
                message: activityMessage,
              },
              ...prev.slice(0, 49),
            ]);
          }
          break;

        case 'progress_update':
          // Update project progress
          if (message.completed_tasks !== undefined && message.total_tasks !== undefined) {
            setProjectProgress({
              completed_tasks: message.completed_tasks,
              total_tasks: message.total_tasks,
              percentage: message.percentage,
            });
            mutateProject(); // Also refresh full project data
          }
          break;

        case 'correction_attempt':
          // Add correction attempt to activity feed
          if (message.task_id) {
            const attemptNum = message.attempt_number ?? 0;
            const maxAttempts = message.max_attempts ?? 3;
            const errorSummary = message.error_summary ?? 'unknown error';

            const correctionMessage =
              message.status === 'success'
                ? `✅ Self-correction successful (attempt ${attemptNum}/${maxAttempts})`
                : message.status === 'in_progress'
                ? `🔄 Self-correction attempt ${attemptNum}/${maxAttempts}...`
                : `⚠️ Correction attempt ${attemptNum} failed: ${errorSummary}`;

            setActivity((prev) => [
              {
                timestamp: message.timestamp,
                type: 'correction_attempt',
                agent: 'backend-worker',
                message: correctionMessage,
              },
              ...prev.slice(0, 49),
            ]);
          }
          break;

        case 'agent_created':
          // Add new agent to state
          if (message.agent_id && message.agent_type) {
            setAgents((prev) => {
              // Check if agent already exists
              if (prev.some(a => a.id === message.agent_id)) {
                return prev;
              }
              // Add new agent
              return [
                ...prev,
                {
                  id: message.agent_id,
                  type: message.agent_type,
                  status: 'idle' as AgentStatus,
                  provider: 'anthropic',
                  maturity: 'D1',
                  current_task: undefined,
                  blocker: undefined,
                  context_tokens: 0,
                  tasks_completed: 0,
                },
              ];
            });

            // Add to activity feed
            setActivity((prev) => [
              {
                timestamp: message.timestamp,
                type: 'agent_created',
                agent: 'system',
                message: `🤖 Created ${message.agent_type} agent (${message.agent_id})`,
              },
              ...prev.slice(0, 49),
            ]);
          }
          break;

        case 'agent_retired':
          // Remove agent from state
          if (message.agent_id) {
            setAgents((prev) => prev.filter(a => a.id !== message.agent_id));

            // Add to activity feed
            setActivity((prev) => [
              {
                timestamp: message.timestamp,
                type: 'agent_retired',
                agent: 'system',
                message: `👋 Retired agent ${message.agent_id}`,
              },
              ...prev.slice(0, 49),
            ]);
          }
          break;

        case 'task_assigned':
          // Update task and agent state when task is assigned
          if (message.task_id && message.agent_id) {
            // Update task status
            setTasks((prev) =>
              prev.map((task) =>
                task.id === message.task_id
                  ? { ...task, status: 'in_progress' as TaskStatus, agent_id: message.agent_id }
                  : task
              )
            );

            // Update agent status
            setAgents((prev) =>
              prev.map((agent) =>
                agent.id === message.agent_id
                  ? {
                      ...agent,
                      status: 'working' as AgentStatus,
                      current_task: { id: message.task_id, title: message.task_title || `Task #${message.task_id}` },
                    }
                  : agent
              )
            );

            // Add to activity feed
            setActivity((prev) => [
              {
                timestamp: message.timestamp,
                type: 'task_assigned',
                agent: message.agent_id || 'system',
                message: `📋 Assigned task #${message.task_id} to ${message.agent_id}`,
              },
              ...prev.slice(0, 49),
            ]);
          }
          break;

        case 'task_blocked':
          // Update task status to blocked
          if (message.task_id) {
            setTasks((prev) =>
              prev.map((task) =>
                task.id === message.task_id
                  ? { ...task, status: 'blocked' as TaskStatus, blocked_by: message.blocked_by }
                  : task
              )
            );

            // Add to activity feed
            const blockedByText = message.blocked_by
              ? ` (waiting for ${Array.isArray(message.blocked_by) ? message.blocked_by.join(', ') : message.blocked_by})`
              : '';
            setActivity((prev) => [
              {
                timestamp: message.timestamp,
                type: 'task_blocked',
                agent: 'system',
                message: `🚫 Task #${message.task_id} blocked${blockedByText}`,
              },
              ...prev.slice(0, 49),
            ]);
          }
          break;

        case 'task_unblocked':
          // Update task status from blocked to pending/ready
          if (message.task_id) {
            setTasks((prev) =>
              prev.map((task) =>
                task.id === message.task_id
                  ? { ...task, status: 'pending' as TaskStatus, blocked_by: undefined }
                  : task
              )
            );

            // Add to activity feed
            setActivity((prev) => [
              {
                timestamp: message.timestamp,
                type: 'task_unblocked',
                agent: 'system',
                message: `✅ Task #${message.task_id} unblocked and ready`,
              },
              ...prev.slice(0, 49),
            ]);
          }
          break;

        case 'status_update':
          mutateProject();
          break;

        case 'blocker_resolved':
          mutateBlockers();
          break;

        default:
          // Ignore unknown message types
          break;
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
                CodeFRAME - {projectData.name}
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
              agentStatus={agentsData?.find((a) => a.type === 'lead')?.status}
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
            {(agents.length > 0 || (agentsData && agentsData.length > 0)) && (
              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                {agents.length > 0 ? agents.length : agentsData?.length || 0} agents active
              </span>
            )}
          </div>
          
          {(agents.length > 0 || (agentsData && agentsData.length > 0)) ? (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {(agents.length > 0 ? agents : agentsData || []).map((agent) => (
                <AgentCard
                  key={agent.id}
                  agent={{
                    id: agent.id,
                    type: agent.type,
                    status: agent.status === 'working' ? 'busy' : agent.status === 'blocked' ? 'blocked' : 'idle',
                    currentTask: agent.current_task?.id,
                    tasksCompleted: 0, // TODO: Track in backend
                    blockedBy: agent.blocker ? [0] : undefined, // TODO: Parse blocker IDs
                  }}
                  onAgentClick={(agentId) => console.log('Agent clicked:', agentId)}
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
            {(activity.length > 0 ? activity : activityData || []).map((item, index) => (
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

      {/* PRD Modal (cf-26) */}
      <PRDModal
        isOpen={showPRD}
        onClose={() => setShowPRD(false)}
        prdData={prdData || null}
      />
    </div>
  );
}