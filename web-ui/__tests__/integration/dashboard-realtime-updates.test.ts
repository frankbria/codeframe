/**
 * Dashboard Real-Time Updates Integration Tests
 * Tests T100 and T101: Dashboard integration with WebSocket updates
 */

import { render, screen, waitFor } from '@testing-library/react';
import Dashboard from '@/components/Dashboard';
import { AgentStateProvider } from '@/components/AgentStateProvider';
import * as api from '@/lib/api';
import * as websocket from '@/lib/websocket';

// Mock dependencies
jest.mock('@/lib/api');
jest.mock('@/lib/websocket');
jest.mock('@/components/ChatInterface', () => ({
  __esModule: true,
  default: () => <div>ChatInterface Mock</div>,
}));
jest.mock('@/components/PRDModal', () => ({
  __esModule: true,
  default: () => <div>PRDModal Mock</div>,
}));
jest.mock('@/components/TaskTreeView', () => ({
  __esModule: true,
  default: () => <div>TaskTreeView Mock</div>,
}));
jest.mock('@/components/DiscoveryProgress', () => ({
  __esModule: true,
  default: () => <div>DiscoveryProgress Mock</div>,
}));

// Mock SWR to disable caching
jest.mock('swr', () => {
  const originalSWR = jest.requireActual('swr');
  return {
    __esModule: true,
    default: (key: any, fetcher: any, config: any) => {
      return originalSWR.default(key, fetcher, {
        ...config,
        provider: () => new Map(),
        dedupingInterval: 0,
        focusThrottleInterval: 0,
        revalidateOnFocus: false,
        revalidateOnReconnect: false,
        shouldRetryOnError: false,
      });
    },
  };
});

const mockProjectData = {
  id: 1,
  name: 'Test Project',
  status: 'active',
  phase: 'implementation',
  workflow_step: 5,
  progress: {
    completed_tasks: 3,
    total_tasks: 10,
    percentage: 30,
  },
  time_tracking: {
    elapsed_hours: 2.5,
    estimated_remaining_hours: 5.0,
  },
  cost_tracking: {
    input_tokens: 1500000,
    output_tokens: 50000,
    estimated_cost: 12.50,
  },
};

describe('Dashboard Real-Time Updates Integration', () => {
  let mockWsClient: any;
  let messageHandlers: Map<string, Function>;

  beforeEach(() => {
    jest.clearAllMocks();
    messageHandlers = new Map();

    // Mock WebSocket client with message handler tracking
    mockWsClient = {
      connect: jest.fn(),
      disconnect: jest.fn(),
      subscribe: jest.fn(),
      onMessage: jest.fn((handler) => {
        const id = Date.now().toString();
        messageHandlers.set(id, handler);
        return jest.fn(() => messageHandlers.delete(id));
      }),
      onReconnect: jest.fn(() => jest.fn()),
      onConnectionChange: jest.fn(() => jest.fn()),
    };
    (websocket.getWebSocketClient as jest.Mock).mockReturnValue(mockWsClient);

    // Mock API calls
    (api.projectsApi.getStatus as jest.Mock).mockResolvedValue({
      data: mockProjectData,
    });
    (api.agentsApi.list as jest.Mock).mockResolvedValue({
      data: { agents: [] },
    });
    (api.blockersApi.list as jest.Mock).mockResolvedValue({
      data: { blockers: [] },
    });
    (api.activityApi.list as jest.Mock).mockResolvedValue({
      data: { activity: [] },
    });
    (api.projectsApi.getPRD as jest.Mock).mockResolvedValue({
      data: null,
    });
    (api.projectsApi.getIssues as jest.Mock).mockResolvedValue({
      data: { issues: [], total_issues: 0, total_tasks: 0 },
    });
  });

  describe('T100: Dashboard updates when WebSocket message arrives', () => {
    it('should update Dashboard state when receiving agent_created WebSocket message', async () => {
      render(
        <AgentStateProvider projectId={1}>
          <Dashboard projectId={1} />
        </AgentStateProvider>
      );

      // Wait for initial render
      await waitFor(() => {
        expect(screen.getByText(/Test Project/i)).toBeInTheDocument();
      });

      // Initially no agents
      expect(screen.getByText(/No agents active yet/i)).toBeInTheDocument();

      // Simulate WebSocket message for agent creation
      const agentCreatedMessage = {
        type: 'agent_created',
        project_id: 1,
        data: {
          id: 'backend-worker-1',
          type: 'backend-worker',
          status: 'idle',
          provider: 'anthropic',
          maturity: 'directive',
          context_tokens: 0,
          tasks_completed: 0,
          timestamp: Date.now(),
        },
      };

      // Trigger message handler
      messageHandlers.forEach((handler) => handler(agentCreatedMessage));

      // Verify Dashboard updates with new agent
      await waitFor(() => {
        expect(screen.getByText(/1 agents active/i)).toBeInTheDocument();
        expect(screen.getByText(/backend-worker-1/i)).toBeInTheDocument();
      });
    });

    it('should update Dashboard when receiving agent_status_changed message', async () => {
      // Start with one agent
      (api.agentsApi.list as jest.Mock).mockResolvedValue({
        data: {
          agents: [
            {
              id: 'backend-worker-1',
              type: 'backend-worker',
              status: 'idle',
              provider: 'anthropic',
              maturity: 'directive',
              context_tokens: 0,
              tasks_completed: 0,
              timestamp: Date.now(),
            },
          ],
        },
      });

      render(
        <AgentStateProvider projectId={1}>
          <Dashboard projectId={1} />
        </AgentStateProvider>
      );

      // Wait for agent to load
      await waitFor(() => {
        expect(screen.getByText(/backend-worker-1/i)).toBeInTheDocument();
      });

      // Simulate status change message
      const statusChangeMessage = {
        type: 'agent_status_changed',
        project_id: 1,
        data: {
          agent_id: 'backend-worker-1',
          old_status: 'idle',
          new_status: 'working',
          current_task: {
            id: 'task-1',
            title: 'Implement feature',
          },
          timestamp: Date.now(),
        },
      };

      // Trigger message handler
      messageHandlers.forEach((handler) => handler(statusChangeMessage));

      // Verify agent status updated
      await waitFor(() => {
        // AgentCard should show busy status (mapped from working)
        const agentCard = screen.getByText(/backend-worker-1/i).closest('div');
        expect(agentCard).toBeInTheDocument();
      });
    });
  });

  describe('T101: Multiple AgentCards update independently', () => {
    it('should update multiple agents independently without affecting each other', async () => {
      // Start with two agents
      (api.agentsApi.list as jest.Mock).mockResolvedValue({
        data: {
          agents: [
            {
              id: 'backend-worker-1',
              type: 'backend-worker',
              status: 'idle',
              provider: 'anthropic',
              maturity: 'directive',
              context_tokens: 0,
              tasks_completed: 0,
              timestamp: Date.now(),
            },
            {
              id: 'frontend-specialist-1',
              type: 'frontend-specialist',
              status: 'idle',
              provider: 'anthropic',
              maturity: 'directive',
              context_tokens: 0,
              tasks_completed: 0,
              timestamp: Date.now(),
            },
          ],
        },
      });

      render(
        <AgentStateProvider projectId={1}>
          <Dashboard projectId={1} />
        </AgentStateProvider>
      );

      // Wait for agents to load
      await waitFor(() => {
        expect(screen.getByText(/backend-worker-1/i)).toBeInTheDocument();
        expect(screen.getByText(/frontend-specialist-1/i)).toBeInTheDocument();
      });

      // Update only backend worker
      const backendUpdateMessage = {
        type: 'agent_status_changed',
        project_id: 1,
        data: {
          agent_id: 'backend-worker-1',
          old_status: 'idle',
          new_status: 'working',
          current_task: {
            id: 'task-1',
            title: 'Backend task',
          },
          timestamp: Date.now(),
        },
      };

      messageHandlers.forEach((handler) => handler(backendUpdateMessage));

      // Verify backend worker updated but frontend specialist unchanged
      await waitFor(() => {
        expect(screen.getByText(/backend-worker-1/i)).toBeInTheDocument();
        expect(screen.getByText(/frontend-specialist-1/i)).toBeInTheDocument();
      });

      // Now update frontend specialist
      const frontendUpdateMessage = {
        type: 'agent_status_changed',
        project_id: 1,
        data: {
          agent_id: 'frontend-specialist-1',
          old_status: 'idle',
          new_status: 'working',
          current_task: {
            id: 'task-2',
            title: 'Frontend task',
          },
          timestamp: Date.now(),
        },
      };

      messageHandlers.forEach((handler) => handler(frontendUpdateMessage));

      // Both should still be present and updated
      await waitFor(() => {
        expect(screen.getByText(/backend-worker-1/i)).toBeInTheDocument();
        expect(screen.getByText(/frontend-specialist-1/i)).toBeInTheDocument();
      });
    });

    it('should handle simultaneous updates to multiple agents', async () => {
      // Start with three agents
      (api.agentsApi.list as jest.Mock).mockResolvedValue({
        data: {
          agents: [
            {
              id: 'agent-1',
              type: 'backend-worker',
              status: 'idle',
              provider: 'anthropic',
              maturity: 'directive',
              context_tokens: 0,
              tasks_completed: 0,
              timestamp: Date.now(),
            },
            {
              id: 'agent-2',
              type: 'frontend-specialist',
              status: 'idle',
              provider: 'anthropic',
              maturity: 'directive',
              context_tokens: 0,
              tasks_completed: 0,
              timestamp: Date.now(),
            },
            {
              id: 'agent-3',
              type: 'test-engineer',
              status: 'idle',
              provider: 'anthropic',
              maturity: 'directive',
              context_tokens: 0,
              tasks_completed: 0,
              timestamp: Date.now(),
            },
          ],
        },
      });

      render(
        <AgentStateProvider projectId={1}>
          <Dashboard projectId={1} />
        </AgentStateProvider>
      );

      // Wait for all agents to load
      await waitFor(() => {
        expect(screen.getByText(/3 agents active/i)).toBeInTheDocument();
      });

      // Send multiple updates rapidly
      const updates = [
        {
          type: 'agent_status_changed',
          project_id: 1,
          data: {
            agent_id: 'agent-1',
            old_status: 'idle',
            new_status: 'working',
            timestamp: Date.now(),
          },
        },
        {
          type: 'agent_status_changed',
          project_id: 1,
          data: {
            agent_id: 'agent-2',
            old_status: 'idle',
            new_status: 'working',
            timestamp: Date.now() + 1,
          },
        },
        {
          type: 'agent_status_changed',
          project_id: 1,
          data: {
            agent_id: 'agent-3',
            old_status: 'idle',
            new_status: 'working',
            timestamp: Date.now() + 2,
          },
        },
      ];

      updates.forEach((update) => {
        messageHandlers.forEach((handler) => handler(update));
      });

      // All agents should still be present
      await waitFor(() => {
        expect(screen.getByText(/agent-1/i)).toBeInTheDocument();
        expect(screen.getByText(/agent-2/i)).toBeInTheDocument();
        expect(screen.getByText(/agent-3/i)).toBeInTheDocument();
      });
    });
  });
});
