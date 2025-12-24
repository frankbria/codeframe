import React from 'react';

export interface Agent {
  id: string;
  type: string;
  status: 'idle' | 'busy' | 'blocked';
  currentTask?: number;
  tasksCompleted: number;
  blockedBy?: number[];
}

interface AgentCardProps {
  agent: Agent;
  onAgentClick?: (agentId: string) => void;
}

const AgentCardComponent: React.FC<AgentCardProps> = ({ agent, onAgentClick }) => {
  // Status color mapping (Nova palette)
  const statusColors = {
    idle: 'bg-secondary border-border text-secondary-foreground',
    busy: 'bg-muted border-border text-muted-foreground',
    blocked: 'bg-destructive border-destructive text-destructive-foreground',
  };

  // Status indicator dot color (Nova palette)
  const statusDotColors = {
    idle: 'bg-secondary',
    busy: 'bg-muted-foreground',
    blocked: 'bg-destructive',
  };

  // Agent type badge colors (Nova palette)
  const agentTypeBadges: Record<string, { bg: string; text: string; icon: string }> = {
    'backend': { bg: 'bg-secondary', text: 'text-secondary-foreground', icon: '⚙️' },
    'backend-worker': { bg: 'bg-secondary', text: 'text-secondary-foreground', icon: '⚙️' },
    'frontend': { bg: 'bg-secondary', text: 'text-secondary-foreground', icon: '🎨' },
    'frontend-specialist': { bg: 'bg-secondary', text: 'text-secondary-foreground', icon: '🎨' },
    'test': { bg: 'bg-secondary', text: 'text-secondary-foreground', icon: '🧪' },
    'test-engineer': { bg: 'bg-secondary', text: 'text-secondary-foreground', icon: '🧪' },
  };

  const agentTypeBadge = agentTypeBadges[agent.type] || { bg: 'bg-muted', text: 'text-muted-foreground', icon: '🤖' };

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

  return (
    <div
      className={`relative rounded-lg border-2 p-4 transition-all duration-200 hover:shadow-sm cursor-pointer ${
        statusColors[agent.status]
      }`}
      onClick={() => onAgentClick?.(agent.id)}
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
      <div className="mb-3">
        <span className={`inline-flex items-center gap-1 px-2 py-1 rounded text-xs font-medium ${agentTypeBadge.bg} ${agentTypeBadge.text}`}>
          <span>{agentTypeBadge.icon}</span>
          <span>{formatAgentType(agent.type)}</span>
        </span>
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
      JSON.stringify(prevProps.agent.blockedBy) === JSON.stringify(nextProps.agent.blockedBy)
    );
  }
);

AgentCard.displayName = 'AgentCard';

export default AgentCard;