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
  // Status color mapping
  const statusColors = {
    idle: 'bg-green-100 border-green-500 text-green-800',
    busy: 'bg-yellow-100 border-yellow-500 text-yellow-800',
    blocked: 'bg-red-100 border-red-500 text-red-800',
  };

  // Status indicator dot color
  const statusDotColors = {
    idle: 'bg-green-500',
    busy: 'bg-yellow-500',
    blocked: 'bg-red-500',
  };

  // Agent type badge colors
  const agentTypeBadges: Record<string, { bg: string; text: string; icon: string }> = {
    'backend': { bg: 'bg-blue-100', text: 'text-blue-800', icon: '⚙️' },
    'backend-worker': { bg: 'bg-blue-100', text: 'text-blue-800', icon: '⚙️' },
    'frontend': { bg: 'bg-purple-100', text: 'text-purple-800', icon: '🎨' },
    'frontend-specialist': { bg: 'bg-purple-100', text: 'text-purple-800', icon: '🎨' },
    'test': { bg: 'bg-emerald-100', text: 'text-emerald-800', icon: '🧪' },
    'test-engineer': { bg: 'bg-emerald-100', text: 'text-emerald-800', icon: '🧪' },
  };

  const agentTypeBadge = agentTypeBadges[agent.type] || { bg: 'bg-gray-100', text: 'text-gray-800', icon: '🤖' };

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
      className={`relative rounded-lg border-2 p-4 transition-all duration-200 hover:shadow-md cursor-pointer ${
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
        <div className="mb-3 p-2 bg-white bg-opacity-50 rounded">
          <div className="text-xs text-gray-600 mb-1">Current Task:</div>
          <div className="text-sm font-medium">
            Task #{agent.currentTask}
          </div>
        </div>
      )}

      {/* Blocked By (if blocked) */}
      {agent.status === 'blocked' && agent.blockedBy && agent.blockedBy.length > 0 && (
        <div className="mb-3 p-2 bg-white bg-opacity-50 rounded">
          <div className="text-xs text-gray-600 mb-1">Blocked By:</div>
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
      <div className="flex items-center justify-between pt-3 border-t border-current border-opacity-20">
        <span className="text-xs text-gray-600">Tasks Completed</span>
        <span className="text-lg font-bold">{agent.tasksCompleted}</span>
      </div>

      {/* Idle State Message */}
      {agent.status === 'idle' && (
        <div className="mt-2 text-xs text-center text-gray-500 italic">
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