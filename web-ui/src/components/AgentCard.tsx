import React from 'react';
import {
  Settings01Icon,
  PaintBrush01Icon,
  TestTube01Icon,
  BotIcon,
  SunriseIcon,
  BookOpen01Icon,
  FlashIcon,
  Award01Icon,
} from '@hugeicons/react';

export interface AgentMetrics {
  task_count?: number;
  completed_count?: number;
  completion_rate?: number;
  avg_test_pass_rate?: number;
  self_correction_rate?: number;
  maturity_score?: number;
  last_assessed?: string;
}

export interface Agent {
  id: string;
  type: string;
  status: 'idle' | 'busy' | 'blocked';
  currentTask?: number;
  tasksCompleted: number;
  blockedBy?: number[];
  maturityLevel?: 'directive' | 'coaching' | 'supporting' | 'delegating';
  metrics?: AgentMetrics;
}

interface AgentCardProps {
  agent: Agent;
  onAgentClick?: (agentId: string) => void;
}

const AgentCardComponent: React.FC<AgentCardProps> = ({ agent, onAgentClick }) => {
  // Status color mapping (Nova palette)
  const statusColors = {
    idle: 'bg-secondary border-border text-secondary-foreground',
    busy: 'bg-primary/20 border-border text-foreground',
    blocked: 'bg-destructive/10 border-destructive text-destructive-foreground',
  };

  // Status indicator dot color (Nova palette)
  const statusDotColors = {
    idle: 'bg-secondary',
    busy: 'bg-muted-foreground',
    blocked: 'bg-destructive',
  };

  // Agent type badge colors (Nova palette)
  const agentTypeBadges: Record<string, { bg: string; text: string; Icon: React.ComponentType<{ className?: string; 'data-testid'?: string }> }> = {
    'backend': { bg: 'bg-primary/10', text: 'text-primary-foreground', Icon: Settings01Icon },
    'backend-worker': { bg: 'bg-primary/10', text: 'text-primary-foreground', Icon: Settings01Icon },
    'frontend': { bg: 'bg-secondary', text: 'text-secondary-foreground', Icon: PaintBrush01Icon },
    'frontend-specialist': { bg: 'bg-secondary', text: 'text-secondary-foreground', Icon: PaintBrush01Icon },
    'test': { bg: 'bg-secondary', text: 'text-secondary-foreground', Icon: TestTube01Icon },
    'test-engineer': { bg: 'bg-secondary', text: 'text-secondary-foreground', Icon: TestTube01Icon },
  };

  const agentTypeBadge = agentTypeBadges[agent.type] || { bg: 'bg-muted', text: 'text-foreground', Icon: BotIcon };

  // Maturity level badges (Nova palette)
  const maturityBadges: Record<string, { bg: string; text: string; Icon: React.ComponentType<{ className?: string; 'data-testid'?: string }>; label: string }> = {
    'directive': { bg: 'bg-muted', text: 'text-muted-foreground', Icon: SunriseIcon, label: 'Novice' },
    'coaching': { bg: 'bg-primary/20', text: 'text-primary-foreground', Icon: BookOpen01Icon, label: 'Intermediate' },
    'supporting': { bg: 'bg-accent', text: 'text-accent-foreground', Icon: FlashIcon, label: 'Advanced' },
    'delegating': { bg: 'bg-primary', text: 'text-primary-foreground', Icon: Award01Icon, label: 'Expert' },
  };

  const maturityBadge = agent.maturityLevel
    ? maturityBadges[agent.maturityLevel]
    : null;

  // Format agent type for display
  const formatAgentType = (type: string): string => {
    if (!type) return 'Unknown';
    if (type.includes('-')) {
      // Convert "backend-worker" to "Backend Worker"
      return type
        .split('-')
        .map(word => word.charAt(0).toUpperCase() + word.slice(1))
        .join(' ');
    }
    return type.charAt(0).toUpperCase() + type.slice(1);
  };

  // Status text
  const statusText = {
    idle: 'Idle',
    busy: 'Working',
    blocked: 'Blocked',
  };

  // Extract base agent type for data-testid (e.g., "backend-worker" -> "backend")
  // Defensive coding: handle undefined/empty agent.type gracefully
  const baseAgentType = agent.type?.split('-')[0] ?? 'unknown';

  return (
    <div
      className={`relative rounded-lg border-2 p-4 transition-all duration-200 hover:shadow-sm cursor-pointer ${
        statusColors[agent.status]
      }`}
      onClick={() => onAgentClick?.(agent.id)}
      data-testid={`agent-${baseAgentType}`}
    >
      {/* Agent Header */}
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2">
          {/* Status Indicator Dot */}
          <div className={`w-3 h-3 rounded-full ${statusDotColors[agent.status]} animate-pulse`} />

          {/* Agent ID */}
          <h3 className="font-semibold text-sm truncate max-w-[150px]" title={agent.id}>
            {agent.id}
          </h3>
        </div>

        {/* Status Badge */}
        <span className="px-2 py-0.5 rounded text-xs font-medium">
          {statusText[agent.status]}
        </span>
      </div>

      {/* Agent Type Badge */}
      <div className="mb-3 flex flex-wrap gap-2">
        <span className={`inline-flex items-center gap-1 px-2 py-1 rounded text-xs font-medium ${agentTypeBadge.bg} ${agentTypeBadge.text}`}>
          <agentTypeBadge.Icon className="h-3 w-3" aria-hidden="true" />
          <span>{formatAgentType(agent.type)}</span>
        </span>

        {/* Maturity Level Badge */}
        {maturityBadge && (
          <span
            className={`inline-flex items-center gap-1 px-2 py-1 rounded text-xs font-medium ${maturityBadge.bg} ${maturityBadge.text}`}
            title={agent.metrics ? `Score: ${((agent.metrics.maturity_score || 0) * 100).toFixed(0)}%` : undefined}
          >
            <maturityBadge.Icon className="h-3 w-3" aria-hidden="true" />
            <span>{maturityBadge.label}</span>
          </span>
        )}
      </div>

      {/* Current Task (if busy) */}
      {agent.status === 'busy' && agent.currentTask !== undefined && (
        <div className="mb-3 p-2 bg-card bg-opacity-50 rounded">
          <div className="text-xs text-muted-foreground mb-1">Current Task:</div>
          <div className="text-sm font-medium">
            Task #{agent.currentTask}
          </div>
        </div>
      )}

      {/* Blocked By (if blocked) */}
      {agent.status === 'blocked' && agent.blockedBy && agent.blockedBy.length > 0 && (
        <div className="mb-3 p-2 bg-card bg-opacity-50 rounded">
          <div className="text-xs text-muted-foreground mb-1">Blocked By:</div>
          <div className="text-sm font-medium">
            {agent.blockedBy.length === 1 ? (
              `Task #${agent.blockedBy[0]}`
            ) : (
              `${agent.blockedBy.length} tasks`
            )}
          </div>
        </div>
      )}

      {/* Maturity Metrics (if available) */}
      {agent.metrics && (agent.metrics.completion_rate !== undefined || agent.metrics.avg_test_pass_rate !== undefined) && (
        <div className="mb-3 p-2 bg-card bg-opacity-50 rounded">
          <div className="text-xs text-muted-foreground mb-2">Performance Metrics:</div>
          <div className="grid grid-cols-2 gap-2 text-xs">
            {agent.metrics.completion_rate !== undefined && (
              <div>
                <span className="text-muted-foreground">Completion:</span>{' '}
                <span className="font-medium">{(agent.metrics.completion_rate * 100).toFixed(0)}%</span>
              </div>
            )}
            {agent.metrics.avg_test_pass_rate !== undefined && (
              <div>
                <span className="text-muted-foreground">Test Pass:</span>{' '}
                <span className="font-medium">{(agent.metrics.avg_test_pass_rate * 100).toFixed(0)}%</span>
              </div>
            )}
            {agent.metrics.self_correction_rate !== undefined && (
              <div>
                <span className="text-muted-foreground">First Try:</span>{' '}
                <span className="font-medium">{(agent.metrics.self_correction_rate * 100).toFixed(0)}%</span>
              </div>
            )}
            {agent.metrics.maturity_score !== undefined && (
              <div>
                <span className="text-muted-foreground">Score:</span>{' '}
                <span className="font-medium">{(agent.metrics.maturity_score * 100).toFixed(0)}%</span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Tasks Completed Counter */}
      <div className="flex items-center justify-between pt-3 border-t border-border border-opacity-20">
        <span className="text-xs text-muted-foreground">Tasks Completed</span>
        <span className="text-lg font-bold">{agent.tasksCompleted}</span>
      </div>

      {/* Idle State Message */}
      {agent.status === 'idle' && (
        <div className="mt-2 text-xs text-center text-muted-foreground italic">
          Ready for work
        </div>
      )}
    </div>
  );
};

// Memoize AgentCard to prevent unnecessary re-renders (Phase 5.2 - T110)
// Only re-render if agent data or handler changes
export const AgentCard = React.memo(
  AgentCardComponent,
  (prevProps, nextProps) => {
    // Custom comparison: only re-render if agent changed
    return (
      prevProps.agent.id === nextProps.agent.id &&
      prevProps.agent.status === nextProps.agent.status &&
      prevProps.agent.currentTask === nextProps.agent.currentTask &&
      prevProps.agent.tasksCompleted === nextProps.agent.tasksCompleted &&
      prevProps.agent.maturityLevel === nextProps.agent.maturityLevel &&
      JSON.stringify(prevProps.agent.blockedBy) === JSON.stringify(nextProps.agent.blockedBy) &&
      JSON.stringify(prevProps.agent.metrics) === JSON.stringify(nextProps.agent.metrics)
    );
  }
);

AgentCard.displayName = 'AgentCard';

export default AgentCard;