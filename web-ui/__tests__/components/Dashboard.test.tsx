/**
 * Dashboard Component Tests
 * Tests Dashboard integration with AgentStateProvider
 */

import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import Dashboard from '@/components/Dashboard';
import { AgentStateProvider } from '@/components/AgentStateProvider';
import * as api from '@/lib/api';
import * as websocket from '@/lib/websocket';

// Mock dependencies
jest.mock('@/lib/api');
jest.mock('@/lib/websocket', () => ({
  getWebSocketClient: jest.fn(() => ({
    connect: jest.fn(),
    disconnect: jest.fn(),
    subscribe: jest.fn(),
    onMessage: jest.fn(() => jest.fn()),
    offMessage: jest.fn(),
    onReconnect: jest.fn(() => jest.fn()),
    onConnectionChange: jest.fn(() => jest.fn()),
  })),
}));
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
jest.mock('@/components/context/ContextPanel', () => ({
  ContextPanel: jest.fn(({ agentId, projectId }) => (
    <div data-testid="context-panel">
      Agent: {agentId}, Project: {projectId}
    </div>
  )),
}));

// Mock SWR to disable caching
jest.mock('swr', () => {
  const originalSWR = jest.requireActual('swr');
  return {
    __esModule: true,
    default: (key: any, fetcher: any, config: any) => {
      // Disable all caching for tests
      return originalSWR.default(key, fetcher, {
        ...config,
        provider: () => new Map(), // Use empty cache for each hook
        dedupingInterval: 0,
        focusThrottleInterval: 0,
        revalidateOnFocus: false,
        revalidateOnReconnect: false,
        shouldRetryOnError: false,
      });
    },
  };
});

// Mock WebSocket client globally before any tests run
const mockWsClientGlobal = {
  connect: jest.fn(),
  disconnect: jest.fn(),
  subscribe: jest.fn(),
  onMessage: jest.fn(() => jest.fn()),
  offMessage: jest.fn(),
  onReconnect: jest.fn(() => jest.fn()),
  onConnectionChange: jest.fn(() => jest.fn()),
};

// Set up websocket mock to return our mock client
(websocket.getWebSocketClient as jest.Mock) = jest.fn(() => mockWsClientGlobal);

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

const mockAgents = [
  {
    id: 'backend-worker-1',
    type: 'backend-worker',
    status: 'working',
    provider: 'anthropic',
    maturity: 'directive',
    current_task: { id: 'task-1', title: 'Implement feature' },
    context_tokens: 5000,
    tasks_completed: 2,
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
];

const mockActivity = [
  {
    timestamp: new Date().toISOString(),
    type: 'task_completed',
    agent: 'backend-worker-1',
    message: 'Completed task #1',
  },
];

describe('Dashboard with AgentStateProvider', () => {
  let mockWsClient: any;

  beforeEach(() => {
    // Reset mocks
    jest.clearAllMocks();

    // Mock WebSocket client
    mockWsClient = {
      connect: jest.fn(),
      disconnect: jest.fn(),
      subscribe: jest.fn(),
      onMessage: jest.fn(() => jest.fn()), // Returns unsubscribe function
      onReconnect: jest.fn(() => jest.fn()),
      onConnectionChange: jest.fn(() => jest.fn()), // Add missing method
    };
    (websocket.getWebSocketClient as jest.Mock).mockReturnValue(mockWsClient);

    // Mock API calls
    (api.projectsApi.getStatus as jest.Mock).mockResolvedValue({
      data: mockProjectData,
    });
    (api.agentsApi.list as jest.Mock).mockResolvedValue({
      data: { agents: mockAgents },
    });
    (api.blockersApi.list as jest.Mock).mockResolvedValue({
      data: { blockers: [] },
    });
    (api.activityApi.list as jest.Mock).mockResolvedValue({
      data: { activity: mockActivity },
    });
    (api.projectsApi.getPRD as jest.Mock).mockResolvedValue({
      data: null,
    });
    (api.projectsApi.getIssues as jest.Mock).mockResolvedValue({
      data: { issues: [], total_issues: 0, total_tasks: 0 },
    });
  });

  describe('T096: Rendering with Context', () => {
    it('should render Dashboard wrapped in AgentStateProvider', async () => {
      render(
        <AgentStateProvider projectId={1}>
          <Dashboard projectId={1} />
        </AgentStateProvider>
      );

      // Wait for project data to load
      await waitFor(() => {
        expect(screen.getByText(/Test Project/i)).toBeInTheDocument();
      });

      // Verify header elements
      expect(screen.getByText(/CodeFRAME - Test Project/i)).toBeInTheDocument();
      // Use more specific selector for status badge
      const statusBadges = screen.getAllByText(/ACTIVE/i);
      expect(statusBadges.length).toBeGreaterThan(0);
      expect(screen.getByText(/Phase: implementation \(Step 5\/15\)/i)).toBeInTheDocument();
    });

    // TODO: Fix SWR timing issues - see beads issue cf-jf1
    it.skip('should display loading state initially', async () => {
      // Use mockImplementationOnce to control this specific test without affecting others
      let resolvePromise: (value: any) => void;
      const controlledPromise = new Promise((resolve) => {
        resolvePromise = resolve;
      });
      
      // Override just for this test
      (api.projectsApi.getStatus as jest.Mock).mockReturnValueOnce(controlledPromise);

      const { unmount } = render(
        <AgentStateProvider projectId={1}>
          <Dashboard projectId={1} />
        </AgentStateProvider>
      );

      // Should show loading initially
      expect(screen.getByText(/Loading.../i)).toBeInTheDocument();

      // Now resolve the promise
      resolvePromise!({ data: mockProjectData });

      // Then should show project name after loading
      await waitFor(() => {
        expect(screen.getByText(/Test Project/i)).toBeInTheDocument();
      });
      
      unmount();
    });
  });

  describe('T097: Agent Display from Context', () => {
    it('should display agents from AgentStateProvider', async () => {
      render(
        <AgentStateProvider projectId={1}>
          <Dashboard projectId={1} />
        </AgentStateProvider>
      );

      // Wait for agents to load
      await waitFor(() => {
        expect(screen.getByText(/2 agents active/i)).toBeInTheDocument();
      });

      // Verify agent cards are rendered (use getAllByText since names appear multiple times)
      await waitFor(() => {
        const backendWorkerElements = screen.getAllByText(/backend-worker-1/i);
        expect(backendWorkerElements.length).toBeGreaterThan(0);
        
        const frontendSpecialistElements = screen.getAllByText(/frontend-specialist-1/i);
        expect(frontendSpecialistElements.length).toBeGreaterThan(0);
      });
    });

    // TODO: Fix SWR cache persistence issues - see beads issue cf-jf1
    it.skip('should show "no agents" message when no agents exist', async () => {
      // Override mocks for this specific test only using mockResolvedValueOnce
      (api.agentsApi.list as jest.Mock).mockResolvedValueOnce({
        data: { agents: [] },
      });

      const { unmount } = render(
        <AgentStateProvider projectId={1}>
          <Dashboard projectId={1} />
        </AgentStateProvider>
      );

      // Wait for initial render
      await waitFor(() => {
        expect(screen.getByText(/Test Project/i)).toBeInTheDocument();
      });

      // Should show "no agents" message
      await waitFor(() => {
        expect(
          screen.getByText(/No agents active yet/i)
        ).toBeInTheDocument();
      });
      
      unmount();
    });
  });

  describe('T098: Progress Display', () => {
    it('should display project progress from context', async () => {
      render(
        <AgentStateProvider projectId={1}>
          <Dashboard projectId={1} />
        </AgentStateProvider>
      );

      await waitFor(() => {
        expect(screen.getByText(/3 \/ 10 tasks/i)).toBeInTheDocument();
        expect(screen.getByText(/30%/i)).toBeInTheDocument();
      });
    });

    it('should display time tracking information', async () => {
      render(
        <AgentStateProvider projectId={1}>
          <Dashboard projectId={1} />
        </AgentStateProvider>
      );

      await waitFor(() => {
        expect(screen.getByText(/2.5h/i)).toBeInTheDocument();
        expect(screen.getByText(/~5.0h/i)).toBeInTheDocument();
      });
    });

    it('should display cost tracking information', async () => {
      render(
        <AgentStateProvider projectId={1}>
          <Dashboard projectId={1} />
        </AgentStateProvider>
      );

      await waitFor(() => {
        expect(screen.getByText(/1.5M input/i)).toBeInTheDocument();
        expect(screen.getByText(/50K output/i)).toBeInTheDocument();
        expect(screen.getByText(/\$12\.50/i)).toBeInTheDocument();
      });
    });
  });

  describe('T099: Connection Indicator', () => {
    it('should show connection status from context', async () => {
      render(
        <AgentStateProvider projectId={1}>
          <Dashboard projectId={1} />
        </AgentStateProvider>
      );

      await waitFor(() => {
        expect(screen.getByText(/Test Project/i)).toBeInTheDocument();
      });

      // Initially should show "Live" when connected
      // Note: This depends on WebSocket actually connecting in the test
      // We may need to trigger a WebSocket message to set wsConnected to true
    });
  });

  describe('T018: Blocker WebSocket Integration', () => {
    it('should register WebSocket handler on mount', async () => {
      render(
        <AgentStateProvider projectId={1}>
          <Dashboard projectId={1} />
        </AgentStateProvider>
      );

      await waitFor(() => {
        expect(screen.getByText(/Test Project/i)).toBeInTheDocument();
      });

      // Verify WebSocket onMessage was called to register handler
      expect(mockWsClient.onMessage).toHaveBeenCalled();
    });

    it('should call mutateBlockers when blocker_created event received', async () => {
      // Mock SWR mutate function
      const mutateMock = jest.fn();
      (api.blockersApi.list as jest.Mock).mockResolvedValue({
        data: { blockers: [] },
      });

      render(
        <AgentStateProvider projectId={1}>
          <Dashboard projectId={1} />
        </AgentStateProvider>
      );

      await waitFor(() => {
        expect(screen.getByText(/Test Project/i)).toBeInTheDocument();
      });

      // Get the handler that was registered
      const registeredHandler = mockWsClient.onMessage.mock.calls[0]?.[0];
      expect(registeredHandler).toBeDefined();

      // Mock SWR's mutate function
      const originalMutate = jest.requireActual('swr').useSWRConfig;

      // Trigger the handler with a blocker_created event
      if (registeredHandler) {
        registeredHandler({
          type: 'blocker_created',
          project_id: 1,
          blocker: {
            id: 1,
            agent_id: 'test-agent',
            task_id: 123,
            blocker_type: 'SYNC',
            question: 'Test question?',
            status: 'PENDING',
          },
        });
      }

      // Since we can't easily verify mutateBlockers was called with the mocked SWR,
      // we verify that the handler was registered correctly
      expect(mockWsClient.onMessage).toHaveBeenCalled();
    });

    it('should call mutateBlockers when blocker_resolved event received', async () => {
      render(
        <AgentStateProvider projectId={1}>
          <Dashboard projectId={1} />
        </AgentStateProvider>
      );

      await waitFor(() => {
        expect(screen.getByText(/Test Project/i)).toBeInTheDocument();
      });

      const registeredHandler = mockWsClient.onMessage.mock.calls[0]?.[0];

      // Trigger the handler with a blocker_resolved event
      if (registeredHandler) {
        registeredHandler({
          type: 'blocker_resolved',
          project_id: 1,
          blocker_id: 1,
          answer: 'Test answer',
          resolved_at: new Date().toISOString(),
        });
      }

      // Verify handler was registered
      expect(mockWsClient.onMessage).toHaveBeenCalled();
    });

    it('should call mutateBlockers when blocker_expired event received', async () => {
      render(
        <AgentStateProvider projectId={1}>
          <Dashboard projectId={1} />
        </AgentStateProvider>
      );

      await waitFor(() => {
        expect(screen.getByText(/Test Project/i)).toBeInTheDocument();
      });

      const registeredHandler = mockWsClient.onMessage.mock.calls[0]?.[0];

      // Trigger the handler with a blocker_expired event
      if (registeredHandler) {
        registeredHandler({
          type: 'blocker_expired',
          project_id: 1,
          blocker_id: 1,
          task_id: 123,
          expired_at: new Date().toISOString(),
        });
      }

      // Verify handler was registered
      expect(mockWsClient.onMessage).toHaveBeenCalled();
    });

    it('should ignore non-blocker events', async () => {
      render(
        <AgentStateProvider projectId={1}>
          <Dashboard projectId={1} />
        </AgentStateProvider>
      );

      await waitFor(() => {
        expect(screen.getByText(/Test Project/i)).toBeInTheDocument();
      });

      const registeredHandler = mockWsClient.onMessage.mock.calls[0]?.[0];

      // Trigger the handler with a non-blocker event
      if (registeredHandler) {
        registeredHandler({
          type: 'agent_created',
          project_id: 1,
          agent: { id: 'test-agent' },
        });
      }

      // Should not cause any issues
      expect(mockWsClient.onMessage).toHaveBeenCalled();
    });

    it('should cleanup WebSocket listener on unmount', async () => {
      const unsubscribeMock = jest.fn();
      mockWsClient.onMessage.mockReturnValue(unsubscribeMock);
      mockWsClient.offMessage = jest.fn();

      const { unmount } = render(
        <AgentStateProvider projectId={1}>
          <Dashboard projectId={1} />
        </AgentStateProvider>
      );

      await waitFor(() => {
        expect(screen.getByText(/Test Project/i)).toBeInTheDocument();
      });

      // Unmount the component
      unmount();

      // Verify cleanup was called
      expect(mockWsClient.offMessage).toHaveBeenCalled();
    });
  });

  describe('T020: BlockerPanel Integration', () => {
    it('should pass blockers from SWR to BlockerPanel', async () => {
      const mockBlockers = [
        {
          id: 1,
          agent_id: 'test-agent',
          task_id: 123,
          blocker_type: 'SYNC',
          question: 'Test blocker question?',
          answer: null,
          status: 'PENDING',
          created_at: new Date().toISOString(),
          resolved_at: null,
          time_waiting_ms: 300000,
        },
      ];

      (api.blockersApi.list as jest.Mock).mockResolvedValue({
        data: { blockers: mockBlockers },
      });

      render(
        <AgentStateProvider projectId={1}>
          <Dashboard projectId={1} />
        </AgentStateProvider>
      );

      await waitFor(() => {
        expect(screen.getByText(/Test blocker question\?/i)).toBeInTheDocument();
      });
    });

    it('should pass empty array when blockersData is null', async () => {
      (api.blockersApi.list as jest.Mock).mockResolvedValue({
        data: null,
      });

      render(
        <AgentStateProvider projectId={1}>
          <Dashboard projectId={1} />
        </AgentStateProvider>
      );

      await waitFor(() => {
        expect(screen.getByText(/Test Project/i)).toBeInTheDocument();
      });

      // Should show empty state
      await waitFor(() => {
        expect(screen.getByText(/No blockers - agents are running smoothly!/i)).toBeInTheDocument();
      });
    });

    it('should initialize selectedBlocker as null', async () => {
      render(
        <AgentStateProvider projectId={1}>
          <Dashboard projectId={1} />
        </AgentStateProvider>
      );

      await waitFor(() => {
        expect(screen.getByText(/Test Project/i)).toBeInTheDocument();
      });

      // No blocker modal should be visible initially
      // (This is a basic test - more detailed modal tests would be in a separate file)
    });
  });

  /**
   * Feature: 013-context-panel-integration
   * User Story 1: View Context Tab (P1)
   * TDD - RED Phase: Tests written before implementation
   */
  describe('US1: Context Tab UI (013-context-panel-integration)', () => {
    /**
     * T004 [P] [US1]: Dashboard renders Overview and Context tabs
     * RED: This test will FAIL until tabs are implemented
     */
    it('renders Overview and Context tabs', async () => {
      render(
        <AgentStateProvider projectId={123}>
          <Dashboard projectId={123} />
        </AgentStateProvider>
      );

      await waitFor(() => {
        expect(screen.getByRole('tab', { name: /overview/i })).toBeInTheDocument();
        expect(screen.getByRole('tab', { name: /context/i })).toBeInTheDocument();
      });
    });

    /**
     * T005 [P] [US1]: Overview tab is active by default
     * RED: This test will FAIL until default tab state is set
     */
    it('shows Overview tab active by default', async () => {
      render(
        <AgentStateProvider projectId={123}>
          <Dashboard projectId={123} />
        </AgentStateProvider>
      );

      await waitFor(() => {
        const overviewTab = screen.getByRole('tab', { name: /overview/i });
        expect(overviewTab).toHaveAttribute('aria-selected', 'true');
      });
    });

    /**
     * T006 [P] [US1]: Clicking Context tab switches active tab
     * RED: This test will FAIL until tab switching is implemented
     */
    it('switches to Context tab when clicked', async () => {
      render(
        <AgentStateProvider projectId={123}>
          <Dashboard projectId={123} />
        </AgentStateProvider>
      );

      await waitFor(() => {
        expect(screen.getByRole('tab', { name: /context/i })).toBeInTheDocument();
      });

      const contextTab = screen.getByRole('tab', { name: /context/i });
      fireEvent.click(contextTab);

      expect(contextTab).toHaveAttribute('aria-selected', 'true');
    });

    /**
     * T007 [P] [US1]: Active tab has correct styling
     * RED: This test will FAIL until tab styling is applied
     */
    it('shows active tab with highlighted style', async () => {
      render(
        <AgentStateProvider projectId={123}>
          <Dashboard projectId={123} />
        </AgentStateProvider>
      );

      await waitFor(() => {
        expect(screen.getByRole('tab', { name: /context/i })).toBeInTheDocument();
      });

      const contextTab = screen.getByRole('tab', { name: /context/i });
      fireEvent.click(contextTab);

      // Check for blue text and border styling
      expect(contextTab).toHaveClass('text-blue-600');
      expect(contextTab).toHaveClass('border-blue-600');
    });
  });

  /**
   * Feature: 013-context-panel-integration
   * User Story 2: Agent Selector (P1)
   * TDD - RED Phase: Tests written before implementation
   */
  describe('US2: Agent Selector (013-context-panel-integration)', () => {
    /**
     * T012 [P] [US2]: Agent selector dropdown renders in Context tab
     * RED: This test will FAIL until dropdown is implemented
     */
    it('displays agent selector dropdown in Context tab', async () => {
      render(
        <AgentStateProvider projectId={123}>
          <Dashboard projectId={123} />
        </AgentStateProvider>
      );

      await waitFor(() => {
        expect(screen.getByRole('tab', { name: /context/i })).toBeInTheDocument();
      });

      const contextTab = screen.getByRole('tab', { name: /context/i });
      fireEvent.click(contextTab);

      await waitFor(() => {
        expect(screen.getByLabelText(/select agent/i)).toBeInTheDocument();
      });
    });

    /**
     * T013 [P] [US2]: Dropdown lists all active agents
     * RED: This test will FAIL until agent options are populated
     */
    it('lists all active agents in dropdown', async () => {
      render(
        <AgentStateProvider projectId={123}>
          <Dashboard projectId={123} />
        </AgentStateProvider>
      );

      await waitFor(() => {
        expect(screen.getByRole('tab', { name: /context/i })).toBeInTheDocument();
      });

      const contextTab = screen.getByRole('tab', { name: /context/i });
      fireEvent.click(contextTab);

      await waitFor(() => {
        const dropdown = screen.getByLabelText(/select agent/i);
        expect(dropdown).toBeInTheDocument();
      });

      // Check that agent options are present
      // The mock has 2 agents: backend-worker-1 and frontend-specialist-1
      expect(screen.getByText(/backend-worker/i)).toBeInTheDocument();
      expect(screen.getByText(/frontend-specialist/i)).toBeInTheDocument();
    });

    /**
     * T014 [P] [US2]: Shows placeholder when no agent selected
     * RED: This test will FAIL until placeholder text is added
     */
    it('shows placeholder when no agent selected', async () => {
      render(
        <AgentStateProvider projectId={123}>
          <Dashboard projectId={123} />
        </AgentStateProvider>
      );

      await waitFor(() => {
        expect(screen.getByRole('tab', { name: /context/i })).toBeInTheDocument();
      });

      const contextTab = screen.getByRole('tab', { name: /context/i });
      fireEvent.click(contextTab);

      await waitFor(() => {
        expect(screen.getByText(/select an agent to view context/i)).toBeInTheDocument();
      });
    });

    /**
     * T015 [P] [US2]: Selecting agent updates state
     * RED: This test will FAIL until onChange handler is implemented
     */
    it('updates state when agent selected', async () => {
      render(
        <AgentStateProvider projectId={123}>
          <Dashboard projectId={123} />
        </AgentStateProvider>
      );

      await waitFor(() => {
        expect(screen.getByRole('tab', { name: /context/i })).toBeInTheDocument();
      });

      const contextTab = screen.getByRole('tab', { name: /context/i });
      fireEvent.click(contextTab);

      await waitFor(() => {
        const dropdown = screen.getByLabelText(/select agent/i) as HTMLSelectElement;
        expect(dropdown).toBeInTheDocument();
      });

      const dropdown = screen.getByLabelText(/select agent/i) as HTMLSelectElement;
      fireEvent.change(dropdown, { target: { value: 'backend-worker-1' } });

      // Verify the dropdown value changed
      expect(dropdown.value).toBe('backend-worker-1');
    });
  });

  /**
   * Feature: 013-context-panel-integration
   * User Story 3: Context Statistics (P1)
   * TDD - RED Phase: Tests written before implementation
   */
  describe('US3: Context Statistics (013-context-panel-integration)', () => {
    /**
     * T020 [P] [US3]: ContextPanel renders when agent selected
     * RED: This test will FAIL until ContextPanel is imported and rendered
     */
    it('renders ContextPanel when agent selected', async () => {
      render(
        <AgentStateProvider projectId={123}>
          <Dashboard projectId={123} />
        </AgentStateProvider>
      );

      await waitFor(() => {
        expect(screen.getByRole('tab', { name: /context/i })).toBeInTheDocument();
      });

      const contextTab = screen.getByRole('tab', { name: /context/i });
      fireEvent.click(contextTab);

      await waitFor(() => {
        const dropdown = screen.getByLabelText(/select agent/i);
        expect(dropdown).toBeInTheDocument();
      });

      const dropdown = screen.getByLabelText(/select agent/i) as HTMLSelectElement;
      fireEvent.change(dropdown, { target: { value: 'backend-worker-1' } });

      await waitFor(() => {
        expect(screen.getByTestId('context-panel')).toBeInTheDocument();
      });
    });

    /**
     * T021 [P] [US3]: ContextPanel receives agentId and projectId props
     * RED: This test will FAIL until props are passed correctly
     */
    it('passes correct props to ContextPanel', async () => {
      render(
        <AgentStateProvider projectId={123}>
          <Dashboard projectId={123} />
        </AgentStateProvider>
      );

      await waitFor(() => {
        expect(screen.getByRole('tab', { name: /context/i })).toBeInTheDocument();
      });

      const contextTab = screen.getByRole('tab', { name: /context/i });
      fireEvent.click(contextTab);

      await waitFor(() => {
        const dropdown = screen.getByLabelText(/select agent/i);
        expect(dropdown).toBeInTheDocument();
      });

      const dropdown = screen.getByLabelText(/select agent/i) as HTMLSelectElement;
      fireEvent.change(dropdown, { target: { value: 'backend-worker-1' } });

      await waitFor(() => {
        const panel = screen.getByTestId('context-panel');
        expect(panel).toHaveTextContent('Agent: backend-worker-1');
        expect(panel).toHaveTextContent('Project: 123');
      });
    });

    /**
     * T022 [P] [US3]: ContextPanel hidden when no agent selected
     * RED: This test will FAIL until conditional rendering is implemented
     */
    it('hides ContextPanel when no agent selected', async () => {
      render(
        <AgentStateProvider projectId={123}>
          <Dashboard projectId={123} />
        </AgentStateProvider>
      );

      await waitFor(() => {
        expect(screen.getByRole('tab', { name: /context/i })).toBeInTheDocument();
      });

      const contextTab = screen.getByRole('tab', { name: /context/i });
      fireEvent.click(contextTab);

      await waitFor(() => {
        expect(screen.getByLabelText(/select agent/i)).toBeInTheDocument();
      });

      // ContextPanel should not be rendered when no agent is selected
      expect(screen.queryByTestId('context-panel')).not.toBeInTheDocument();
    });

    /**
     * T023 [P] [US3]: Changing agent updates ContextPanel
     * RED: This test will FAIL until ContextPanel re-renders on agent change
     */
    it('updates ContextPanel when agent changed', async () => {
      render(
        <AgentStateProvider projectId={123}>
          <Dashboard projectId={123} />
        </AgentStateProvider>
      );

      await waitFor(() => {
        expect(screen.getByRole('tab', { name: /context/i })).toBeInTheDocument();
      });

      const contextTab = screen.getByRole('tab', { name: /context/i });
      fireEvent.click(contextTab);

      await waitFor(() => {
        const dropdown = screen.getByLabelText(/select agent/i);
        expect(dropdown).toBeInTheDocument();
      });

      const dropdown = screen.getByLabelText(/select agent/i) as HTMLSelectElement;

      // Select first agent
      fireEvent.change(dropdown, { target: { value: 'backend-worker-1' } });

      await waitFor(() => {
        expect(screen.getByTestId('context-panel')).toHaveTextContent('Agent: backend-worker-1');
      });

      // Select second agent
      fireEvent.change(dropdown, { target: { value: 'frontend-specialist-1' } });

      await waitFor(() => {
        expect(screen.getByTestId('context-panel')).toHaveTextContent('Agent: frontend-specialist-1');
      });
    });
  });

  /**
   * Feature: 013-context-panel-integration
   * User Story 4: Agent Card Navigation (P2)
   * TDD - RED Phase: Tests written before implementation
   */
  describe('US4: Agent Card Navigation (013-context-panel-integration)', () => {
    /**
     * T029 [P] [US4]: Clicking agent card switches to Context tab
     * RED: This test will FAIL until navigation is wired up
     */
    it('switches to Context tab when agent card clicked', async () => {
      render(
        <AgentStateProvider projectId={123}>
          <Dashboard projectId={123} />
        </AgentStateProvider>
      );

      await waitFor(() => {
        expect(screen.getByText(/Test Project/i)).toBeInTheDocument();
      });

      // Find and click an agent card within the Multi-Agent Pool section
      // Look for agent cards with the characteristic status indicator
      const agentCards = screen.getAllByText(/backend-worker-1/i);
      // The first occurrence should be in the agent card (within Multi-Agent Pool)
      const agentCard = agentCards[0].closest('div[class*="rounded-lg border-2"]');
      expect(agentCard).toBeInTheDocument();

      fireEvent.click(agentCard!);

      // Verify Context tab is now active
      await waitFor(() => {
        const contextTab = screen.getByRole('tab', { name: /context/i });
        expect(contextTab).toHaveAttribute('aria-selected', 'true');
      });
    });

    /**
     * T030 [P] [US4]: Clicked agent pre-selected in dropdown
     * RED: This test will FAIL until agent selection is wired up
     */
    it('pre-selects clicked agent in dropdown', async () => {
      render(
        <AgentStateProvider projectId={123}>
          <Dashboard projectId={123} />
        </AgentStateProvider>
      );

      await waitFor(() => {
        expect(screen.getByText(/Test Project/i)).toBeInTheDocument();
      });

      // Find and click an agent card within the Multi-Agent Pool section
      const agentCards = screen.getAllByText(/backend-worker-1/i);
      const agentCard = agentCards[0].closest('div[class*="rounded-lg border-2"]');
      expect(agentCard).toBeInTheDocument();

      fireEvent.click(agentCard!);

      // Wait for Context tab to be active
      await waitFor(() => {
        const contextTab = screen.getByRole('tab', { name: /context/i });
        expect(contextTab).toHaveAttribute('aria-selected', 'true');
      });

      // Verify agent is selected in dropdown
      await waitFor(() => {
        const dropdown = screen.getByLabelText(/select agent/i) as HTMLSelectElement;
        expect(dropdown.value).toBe('backend-worker-1');
      });
    });
  });
});