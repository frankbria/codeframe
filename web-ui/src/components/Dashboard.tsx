/**
 * Main Dashboard Component
 */

'use client';

import { useEffect, useState, useMemo, useCallback, useRef } from 'react';
import Link from 'next/link';
import useSWR from 'swr';
import { projectsApi, blockersApi } from '@/lib/api';
import { getTaskReviews } from '@/api/reviews';
import { useAgentState } from '@/hooks/useAgentState';
import type { Blocker } from '@/types/blocker';
import type { PRDResponse, IssuesResponse } from '@/types/api';
import type { DashboardTab } from '@/types/dashboard';
import type { ReviewResult } from '@/types/reviews';
import { getWebSocketClient } from '@/lib/websocket';
import ChatInterface from './ChatInterface';
import PRDModal from './PRDModal';
import TaskTreeView from './TaskTreeView';
import DiscoveryProgress from './DiscoveryProgress';
import AgentCard from './AgentCard';
import AgentList from './AgentList';
import BlockerPanel from './BlockerPanel';
import { BlockerModal } from './BlockerModal';
import ReviewResultsPanel from './review/ReviewResultsPanel';
import { LintTrendChart } from './lint/LintTrendChart';
import { ContextPanel } from './context/ContextPanel';
import { SessionStatus } from './SessionStatus';
import CheckpointList from './checkpoints/CheckpointList';
import CostDashboard from './metrics/CostDashboard';
import ReviewSummary from './reviews/ReviewSummary';
import { QualityGatesPanel } from './quality-gates';
import QualityGatesPanelFallback from './quality-gates/QualityGatesPanelFallback';
import ErrorBoundary from './ErrorBoundary';
import TaskStats from './tasks/TaskStats';
import PhaseProgress from './PhaseProgress';

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

  // Review data state (Sprint 10)
  const [reviewData, setReviewData] = useState<ReviewResult | null>(null);
  const [reviewLoading, setReviewLoading] = useState(false);

  // Quality Gates Panel error boundary state
  const [qualityGatesPanelKey, setQualityGatesPanelKey] = useState<number>(0);
  const [showQualityGatesPanel, setShowQualityGatesPanel] = useState<boolean>(true);
  const lastRetryTimeRef = useRef<number>(0);

  // Memoize filtered agent lists for performance (T111)
  const _activeAgents = useMemo(
    () => agents.filter(a => a.status === 'working' || a.status === 'blocked'),
    [agents]
  );

  const _idleAgents = useMemo(
    () => agents.filter(a => a.status === 'idle'),
    [agents]
  );

  // Stable callback for agent click handler (T112, T032-T033 - Feature 013)
  const handleAgentClick = useCallback((agentId: string) => {
    // Navigate to Context tab and select the clicked agent
    setSelectedAgentId(agentId);
    setActiveTab('context');
  }, []);

  // Quality Gates Panel error boundary handlers
  const handleQualityGatesRetry = useCallback(() => {
    const now = Date.now();
    const DEBOUNCE_DELAY_MS = 500; // 500ms debounce to prevent rapid re-mounting

    // Check if enough time has passed since last retry
    if (now - lastRetryTimeRef.current < DEBOUNCE_DELAY_MS) {
      console.debug('[Quality Gates Panel] Retry debounced (too soon)');
      return;
    }

    // Update last retry time
    lastRetryTimeRef.current = now;

    // Increment key to force re-mount of ErrorBoundary and its children
    setQualityGatesPanelKey(prev => prev + 1);
  }, []);

  const handleQualityGatesDismiss = useCallback(() => {
    // Hide the Quality Gates Panel
    setShowQualityGatesPanel(false);
  }, []);

  const handleQualityGatesError = useCallback((error: Error, errorInfo: React.ErrorInfo) => {
    // Log error to console for debugging
    console.error('[Quality Gates Panel] Error caught by boundary:', error);
    console.error('[Quality Gates Panel] Component stack:', errorInfo.componentStack);
    console.error('[Quality Gates Panel] Timestamp:', new Date().toISOString());
    // In production, consider sending to error tracking service (e.g., Sentry)
  }, []);

  // Memoize fallback component to prevent re-creation on every Dashboard render
  const qualityGatesFallback = useMemo(() => (
    <div className="mb-6">
      <QualityGatesPanelFallback
        onRetry={handleQualityGatesRetry}
        onDismiss={handleQualityGatesDismiss}
      />
    </div>
  ), [handleQualityGatesRetry, handleQualityGatesDismiss]);

  // Fetch project status
  const { data: projectData } = useSWR(
    `/projects/${projectId}/status`,
    () => projectsApi.getStatus(projectId).then((res) => res.data)
  );

  // Fetch blockers
  const { data: blockersData, mutate: mutateBlockers } = useSWR(
    `/projects/${projectId}/blockers`,
    () => blockersApi.list(projectId).then((res) => res.data?.blockers || [])
  );

  // Fetch PRD data (cf-26)
  const { data: prdData, mutate: mutatePRD } = useSWR<PRDResponse>(
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

  // Fetch review data for latest completed task (Sprint 10)
  useEffect(() => {
    async function loadLatestReview() {
      const completedTasks = tasks.filter(t => t.status === 'completed');
      if (completedTasks.length === 0) {
        setReviewData(null);
        return;
      }

      setReviewLoading(true);
      try {
        // Fetch reviews for the first completed task
        const taskId = completedTasks[0].id;
        const data = await getTaskReviews(taskId);
        setReviewData(data);
      } catch (err) {
        console.error('Failed to load reviews:', err);
        setReviewData(null);
      } finally {
        setReviewLoading(false);
      }
    }

    loadLatestReview();
  }, [tasks]);

  // WebSocket connection and real-time updates are now handled by AgentStateProvider (Phase 5.2)
  // All WebSocket message handling, state updates, and reconnection logic moved to Provider

  // WebSocket handler for blocker lifecycle events (T018, T033, T034, 049-human-in-loop)
  useEffect(() => {
    const ws = getWebSocketClient();

                // eslint-disable-next-line @typescript-eslint/no-explicit-any
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

  // WebSocket handler for PRD generation events (PRD button synchronization fix)
  useEffect(() => {
    const ws = getWebSocketClient();

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const handlePRDEvent = (message: any) => {
      // Only handle PRD events for this project
      if (message.project_id !== projectId) {
        return;
      }

      // When PRD generation completes, invalidate SWR cache to sync both View PRD buttons
      if (message.type === 'prd_generation_completed') {
        mutatePRD();
      }
    };

    const unsubscribe = ws.onMessage(handlePRDEvent);

    return () => {
      unsubscribe();
    };
  }, [projectId, mutatePRD]);

  if (!projectData) {
    return <div className="p-8 text-center text-muted-foreground">Loading...</div>;
  }

  // Defensive check: ensure progress object exists with defaults
  const progress = projectProgress || projectData.progress || {
    completed_tasks: 0,
    total_tasks: 0,
    percentage: 0.0
  };

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="bg-card border-b border-border" data-testid="dashboard-header">
        <div className="max-w-7xl mx-auto px-4 py-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between" data-testid="project-selector">
            <div>
              {/* Back to Projects navigation */}
              <Link
                href="/"
                data-testid="back-to-projects"
                className="inline-flex items-center text-sm text-muted-foreground hover:text-foreground mb-1"
              >
                <span className="mr-1">←</span>
                <span>Projects</span>
              </Link>
              <h1 className="text-2xl font-bold text-foreground">
                CodeFRAME - {projectData.name}
              </h1>
              <div className="flex items-center gap-4 mt-1">
                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-secondary text-secondary-foreground">
                  {projectData.status.toUpperCase()}
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
                disabled={prdData?.status !== 'available'}
                data-testid="prd-generated"
                className={`px-4 py-2 border border-border rounded-md transition-colors flex items-center gap-2 ${
                  prdData?.status === 'available'
                    ? 'bg-primary text-primary-foreground hover:bg-primary/90'
                    : prdData?.status === 'generating'
                      ? 'bg-secondary text-secondary-foreground cursor-wait'
                      : 'bg-muted text-muted-foreground cursor-not-allowed'
                }`}
              >
                {prdData?.status === 'generating' && (
                  <svg className="animate-spin h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                )}
                {prdData?.status === 'generating' ? 'Generating PRD...' : 'View PRD'}
              </button>
              <button
                onClick={() => setShowChat(!showChat)}
                className={`px-4 py-2 rounded-md transition-colors ${
                  showChat
                    ? 'bg-secondary text-secondary-foreground hover:bg-secondary/80'
                    : 'bg-primary text-primary-foreground hover:bg-primary/90'
                }`}
              >
                {showChat ? 'Hide Chat' : 'Chat with Lead'}
              </button>
              <button className="px-4 py-2 border border-border rounded-md bg-secondary text-secondary-foreground hover:bg-secondary/80">
                Pause
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* Phase Progress Section */}
      <div className="bg-card border-b border-border">
        <div className="max-w-7xl mx-auto px-4 py-3 sm:px-6 lg:px-8">
          <PhaseProgress
            phase={projectData.phase === 'active' ? 'development' : (projectData.phase || 'discovery')}
            currentStep={projectData.workflow_step || 0}
            totalSteps={15}
          />
        </div>
      </div>

      {/* Tab Navigation (T009 - Feature 013, Sprint 10 Refactor) */}
      <div className="bg-card border-b border-border">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <nav className="-mb-px flex space-x-8" role="tablist" aria-label="Dashboard tabs" data-testid="nav-menu">
            <button
              role="tab"
              aria-selected={activeTab === 'overview'}
              aria-controls="overview-panel"
              onClick={() => setActiveTab('overview')}
              data-testid="overview-tab"
              className={`py-4 px-1 border-b-2 font-medium text-sm transition-colors ${
                activeTab === 'overview'
                  ? 'border-primary text-primary'
                  : 'border-transparent text-muted-foreground hover:text-foreground hover:border-border'
              }`}
            >
              Overview
            </button>
            <button
              role="tab"
              aria-selected={activeTab === 'tasks'}
              aria-controls="tasks-panel"
              onClick={() => setActiveTab('tasks')}
              data-testid="tasks-tab"
              className={`py-4 px-1 border-b-2 font-medium text-sm transition-colors ${
                activeTab === 'tasks'
                  ? 'border-primary text-primary'
                  : 'border-transparent text-muted-foreground hover:text-foreground hover:border-border'
              }`}
            >
              Tasks
            </button>
            <button
              role="tab"
              aria-selected={activeTab === 'quality-gates'}
              aria-controls="quality-gates-panel"
              onClick={() => setActiveTab('quality-gates')}
              data-testid="quality-gates-tab"
              className={`py-4 px-1 border-b-2 font-medium text-sm transition-colors ${
                activeTab === 'quality-gates'
                  ? 'border-primary text-primary'
                  : 'border-transparent text-muted-foreground hover:text-foreground hover:border-border'
              }`}
            >
              Quality Gates
            </button>
            <button
              role="tab"
              aria-selected={activeTab === 'checkpoints'}
              aria-controls="checkpoints-panel"
              onClick={() => setActiveTab('checkpoints')}
              data-testid="checkpoint-tab"
              className={`py-4 px-1 border-b-2 font-medium text-sm transition-colors ${
                activeTab === 'checkpoints'
                  ? 'border-primary text-primary'
                  : 'border-transparent text-muted-foreground hover:text-foreground hover:border-border'
              }`}
            >
              Checkpoints
            </button>
            <button
              role="tab"
              aria-selected={activeTab === 'metrics'}
              aria-controls="metrics-panel"
              onClick={() => setActiveTab('metrics')}
              data-testid="metrics-tab"
              className={`py-4 px-1 border-b-2 font-medium text-sm transition-colors ${
                activeTab === 'metrics'
                  ? 'border-primary text-primary'
                  : 'border-transparent text-muted-foreground hover:text-foreground hover:border-border'
              }`}
            >
              Metrics
            </button>
            <button
              role="tab"
              aria-selected={activeTab === 'context'}
              aria-controls="context-panel"
              onClick={() => setActiveTab('context')}
              data-testid="context-tab"
              className={`py-4 px-1 border-b-2 font-medium text-sm transition-colors ${
                activeTab === 'context'
                  ? 'border-primary text-primary'
                  : 'border-transparent text-muted-foreground hover:text-foreground hover:border-border'
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
            <DiscoveryProgress projectId={projectId} onViewPRD={() => setShowPRD(true)} />

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
            <div className="bg-card rounded-lg shadow p-6 mb-6">
              <h2 className="text-lg font-semibold mb-4">Progress</h2>
              <div className="space-y-2">
                <div className="flex justify-between text-sm">
                  <span>
                    {progress.completed_tasks} /{' '}
                    {progress.total_tasks} tasks
                  </span>
                  <span>{progress.percentage}%</span>
                </div>
                <div className="w-full bg-muted rounded-full h-4">
                  <div
                    className="bg-primary h-4 rounded-full transition-all duration-500"
                    style={{ width: `${progress.percentage}%` }}
                  ></div>
                </div>
              </div>

              {projectData.time_tracking && (
                <div className="grid grid-cols-2 gap-4 mt-4 text-sm">
                  <div>
                    <span className="text-muted-foreground">Elapsed:</span>{' '}
                    <span className="font-medium">
                      {projectData.time_tracking.elapsed_hours.toFixed(1)}h
                    </span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Remaining:</span>{' '}
                    <span className="font-medium">
                      ~{projectData.time_tracking.estimated_remaining_hours.toFixed(1)}h
                    </span>
                  </div>
                </div>
              )}

              {projectData.cost_tracking && (
                <div className="mt-4 text-sm border-t border-border pt-4">
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">
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

            {/* Agents Section - Multi-Agent Per Project Architecture */}
            <div className="bg-card rounded-lg shadow p-6 mb-6" data-testid="agent-status-panel">
              <h2 className="text-lg font-semibold mb-4">🤖 Multi-Agent Team</h2>
              <AgentList
                projectId={projectId}
                onAgentClick={handleAgentClick}
                showActiveOnly={true}
                refreshInterval={30000}
              />
            </div>

            {/* Legacy Agent Cards (from AgentStateProvider) - Keeping for backward compatibility */}
            {agents.length > 0 && (
              <div className="bg-card rounded-lg shadow p-6 mb-6" data-testid="agent-state-panel">
                <div className="flex items-center justify-between mb-4">
                  <h2 className="text-lg font-semibold">🔄 Agent State (Real-time)</h2>
                  <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-secondary text-secondary-foreground">
                    {agents.length} agents active
                  </span>
                </div>

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
              </div>
            )}

            {/* Recent Activity */}
            <div className="bg-card rounded-lg shadow p-6">
              <h2 className="text-lg font-semibold mb-4">📝 Recent Activity</h2>
              <div className="space-y-2">
                {activity.length > 0 ? (
                  activity.map((item, index) => (
                    <div key={index} className="flex items-start gap-3 text-sm">
                      <span className="text-muted-foreground min-w-[60px]">
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
                  <div className="text-center py-4 text-muted-foreground">
                    No recent activity
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Tasks Tab Panel (Sprint 10 Refactor) */}
        {activeTab === 'tasks' && (
          <div role="tabpanel" id="tasks-panel" aria-labelledby="tasks-tab" data-testid="tasks-panel">
            {/* Task Statistics Section */}
            <div className="bg-card rounded-lg shadow p-6 mb-6">
              <h2 className="text-lg font-semibold mb-4">📊 Task Statistics</h2>
              <TaskStats />
            </div>

            {/* Issues & Tasks Section (cf-26) */}
            <div className="bg-card rounded-lg shadow p-6 mb-6">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-semibold">🎯 Issues & Tasks</h2>
                {issuesData && (
                  <span className="text-sm text-muted-foreground">
                    {issuesData.total_issues} issues, {issuesData.total_tasks} tasks
                  </span>
                )}
              </div>
              <TaskTreeView issues={issuesData?.issues || []} />
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

            {/* Review Findings Panel (T065, Sprint 10) */}
            <div className="mb-6" data-testid="review-findings-panel">
              <div className="bg-card rounded-lg shadow p-6">
                <h2 className="text-lg font-semibold mb-4">🔍 Code Review Findings</h2>
                <ReviewSummary reviewResult={reviewData} loading={reviewLoading} />
              </div>
            </div>
          </div>
        )}

        {/* Quality Gates Tab Panel (Sprint 10 Refactor) */}
        {activeTab === 'quality-gates' && (
          <div role="tabpanel" id="quality-gates-panel" aria-labelledby="quality-gates-tab" data-testid="quality-gates-panel">
            {showQualityGatesPanel ? (
              <ErrorBoundary
                key={qualityGatesPanelKey}
                fallback={qualityGatesFallback}
                onError={handleQualityGatesError}
              >
                <div className="bg-card rounded-lg shadow p-6">
                  <h2 className="text-lg font-semibold mb-4">✅ Quality Gates</h2>
                  <QualityGatesPanel projectId={projectId} tasks={tasks} />
                </div>
              </ErrorBoundary>
            ) : (
              <div className="bg-card rounded-lg shadow p-6">
                <div className="text-center py-12 text-muted-foreground">
                  <p className="text-lg mb-2">Quality Gates Panel Hidden</p>
                  <button
                    onClick={() => setShowQualityGatesPanel(true)}
                    className="text-primary hover:underline"
                  >
                    Click to show
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Metrics Tab Panel (Sprint 10 Refactor) */}
        {activeTab === 'metrics' && (
          <div role="tabpanel" id="metrics-panel" aria-labelledby="metrics-tab" data-testid="metrics-panel">
            <div className="bg-card rounded-lg shadow p-6">
              <h2 className="text-lg font-semibold mb-4">📊 Cost & Token Metrics</h2>
              <CostDashboard projectId={projectId} />
            </div>
          </div>
        )}

        {/* Context Tab Panel (T011 - Feature 013) */}
        {activeTab === 'context' && (
          <div role="tabpanel" id="context-panel" aria-labelledby="context-tab">
            <div className="bg-card rounded-lg shadow p-6">
              {/* Agent Selector (T016-T019 - Feature 013) */}
              <div className="mb-6">
                <label
                  htmlFor="agent-selector"
                  className="block text-sm font-medium text-foreground mb-2"
                >
                  Select Agent
                </label>
                <select
                  id="agent-selector"
                  aria-label="Select agent"
                  value={selectedAgentId || ''}
                  onChange={(e) => setSelectedAgentId(e.target.value || null)}
                  className="w-full px-4 py-2 border border-border rounded-lg bg-background focus:ring-2 focus:ring-ring focus:border-border"
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
                <div className="text-center py-12 text-muted-foreground">
                  <p className="text-lg mb-2">Select an agent to view context</p>
                  <p className="text-sm">
                    Context items show what&apos;s in agent memory (HOT/WARM/COLD tiers)
                  </p>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Checkpoints Tab Panel (Sprint 10) */}
        {activeTab === 'checkpoints' && (
          <div role="tabpanel" id="checkpoints-panel" aria-labelledby="checkpoints-tab">
            <div className="bg-card rounded-lg shadow p-6" data-testid="checkpoint-panel">
              <h2 className="text-lg font-semibold mb-4">💾 Checkpoints</h2>
              <CheckpointList projectId={projectId} refreshInterval={30000} />
            </div>
          </div>
        )}
      </main>

      {/* PRD Modal (cf-26) */}
      <PRDModal
        isOpen={showPRD}
        onClose={() => setShowPRD(false)}
        prdData={prdData || null}
        onRetry={() => mutatePRD()}
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