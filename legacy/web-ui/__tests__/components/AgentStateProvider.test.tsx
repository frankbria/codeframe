/**
 * AgentStateProvider Component Tests
 *
 * Tests for the Context Provider component.
 * Verifies provider renders children, provides initial state, and handles dispatch.
 *
 * Phase: 5.2 - Dashboard Multi-Agent State Management
 * Date: 2025-11-06
 * Tasks: T036, T037, T041
 */

import { render, screen, waitFor } from '@testing-library/react';
import { AgentStateProvider } from '@/components/AgentStateProvider';
import { useAgentState } from '@/hooks/useAgentState';
import { createMockAgent } from '../../test-utils/agentState.fixture';

// Mock SWR to avoid actual API calls
jest.mock('swr', () => ({
  __esModule: true,
  default: jest.fn(() => ({
    data: undefined,
    error: undefined,
    isLoading: false,
    mutate: jest.fn(),
  })),
}));

// Mock API modules
jest.mock('@/lib/api', () => ({
  agentsApi: {
    list: jest.fn(),
  },
  tasksApi: {
    list: jest.fn(),
  },
  activityApi: {
    list: jest.fn(),
  },
}));

/**
 * Test component that consumes Context
 */
function TestConsumer() {
  const { agents, wsConnected } = useAgentState();

  return (
    <div>
      <div data-testid="agent-count">{agents.length}</div>
      <div data-testid="ws-status">{wsConnected ? 'connected' : 'disconnected'}</div>
    </div>
  );
}

describe('AgentStateProvider', () => {
  // ==========================================================================
  // T036: Provider renders children
  // ==========================================================================
  describe('Rendering', () => {
    it('should render children', () => {
      render(
        <AgentStateProvider projectId={1}>
          <div data-testid="test-child">Test Child</div>
        </AgentStateProvider>
      );

      expect(screen.getByTestId('test-child')).toBeInTheDocument();
      expect(screen.getByTestId('test-child')).toHaveTextContent('Test Child');
    });

    it('should render multiple children', () => {
      render(
        <AgentStateProvider projectId={1}>
          <div data-testid="child-1">Child 1</div>
          <div data-testid="child-2">Child 2</div>
          <div data-testid="child-3">Child 3</div>
        </AgentStateProvider>
      );

      expect(screen.getByTestId('child-1')).toBeInTheDocument();
      expect(screen.getByTestId('child-2')).toBeInTheDocument();
      expect(screen.getByTestId('child-3')).toBeInTheDocument();
    });
  });

  // ==========================================================================
  // T037: Provider provides initial state
  // ==========================================================================
  describe('Initial State', () => {
    it('should provide initial state to children', () => {
      render(
        <AgentStateProvider projectId={1}>
          <TestConsumer />
        </AgentStateProvider>
      );

      // Initial state should have 0 agents
      expect(screen.getByTestId('agent-count')).toHaveTextContent('0');

      // Initial state should have wsConnected = false
      expect(screen.getByTestId('ws-status')).toHaveTextContent('disconnected');
    });

    it('should provide Context value to nested children', () => {
      render(
        <AgentStateProvider projectId={1}>
          <div>
            <div>
              <TestConsumer />
            </div>
          </div>
        </AgentStateProvider>
      );

      // Deeply nested component should still access state
      expect(screen.getByTestId('agent-count')).toBeInTheDocument();
    });
  });

  // ==========================================================================
  // T041: Provider handles multiple dispatch calls
  // ==========================================================================
  describe('Dispatch Handling', () => {
    it('should handle dispatch calls and update state', async () => {
      function DispatchTestComponent() {
        const { agents, createAgent } = useAgentState();

        const handleClick = () => {
          const newAgent = createMockAgent({ id: 'test-agent-1' });
          createAgent(newAgent);
        };

        return (
          <div>
            <div data-testid="agent-count">{agents.length}</div>
            <button onClick={handleClick} data-testid="add-agent">
              Add Agent
            </button>
          </div>
        );
      }

      render(
        <AgentStateProvider projectId={1}>
          <DispatchTestComponent />
        </AgentStateProvider>
      );

      // Initial count
      expect(screen.getByTestId('agent-count')).toHaveTextContent('0');

      // Click to add agent
      const button = screen.getByTestId('add-agent');
      button.click();

      // Wait for state update
      await waitFor(() => {
        expect(screen.getByTestId('agent-count')).toHaveTextContent('1');
      });
    });

    it('should handle multiple sequential dispatch calls', async () => {
      function MultiDispatchComponent() {
        const { agents, createAgent } = useAgentState();

        const addMultipleAgents = () => {
          createAgent(createMockAgent({ id: 'agent-1' }));
          createAgent(createMockAgent({ id: 'agent-2' }));
          createAgent(createMockAgent({ id: 'agent-3' }));
        };

        return (
          <div>
            <div data-testid="agent-count">{agents.length}</div>
            <button onClick={addMultipleAgents} data-testid="add-multiple">
              Add Multiple
            </button>
          </div>
        );
      }

      render(
        <AgentStateProvider projectId={1}>
          <MultiDispatchComponent />
        </AgentStateProvider>
      );

      // Click to add multiple agents
      const button = screen.getByTestId('add-multiple');
      button.click();

      // Wait for all state updates
      await waitFor(() => {
        expect(screen.getByTestId('agent-count')).toHaveTextContent('3');
      });
    });

    it('should handle different action types', async () => {
      function MixedActionsComponent() {
        const { agents, wsConnected, createAgent, setWSConnected } =
          useAgentState();

        const performActions = () => {
          createAgent(createMockAgent({ id: 'agent-1' }));
          setWSConnected(true);
        };

        return (
          <div>
            <div data-testid="agent-count">{agents.length}</div>
            <div data-testid="ws-status">{wsConnected ? 'connected' : 'disconnected'}</div>
            <button onClick={performActions} data-testid="perform-actions">
              Perform Actions
            </button>
          </div>
        );
      }

      render(
        <AgentStateProvider projectId={1}>
          <MixedActionsComponent />
        </AgentStateProvider>
      );

      // Initial state
      expect(screen.getByTestId('agent-count')).toHaveTextContent('0');
      expect(screen.getByTestId('ws-status')).toHaveTextContent('disconnected');

      // Perform actions
      const button = screen.getByTestId('perform-actions');
      button.click();

      // Wait for state updates
      await waitFor(() => {
        expect(screen.getByTestId('agent-count')).toHaveTextContent('1');
        expect(screen.getByTestId('ws-status')).toHaveTextContent('connected');
      });
    });
  });

  // ==========================================================================
  // Additional Tests
  // ==========================================================================
  describe('Edge Cases', () => {
    it('should handle projectId prop change', () => {
      const { rerender } = render(
        <AgentStateProvider projectId={1}>
          <TestConsumer />
        </AgentStateProvider>
      );

      // Should still render after projectId change
      rerender(
        <AgentStateProvider projectId={2}>
          <TestConsumer />
        </AgentStateProvider>
      );

      expect(screen.getByTestId('agent-count')).toBeInTheDocument();
    });

    it('should not crash when no children provided', () => {
      const { container } = render(<AgentStateProvider projectId={1}><div></div></AgentStateProvider>);

      // Should render empty provider without errors
      expect(container).toBeInTheDocument();
    });
  });
});
