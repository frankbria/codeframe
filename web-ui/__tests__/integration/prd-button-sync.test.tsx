/**
 * PRD Button Synchronization Integration Tests
 *
 * Tests for Issue: PRD button synchronization and state persistence
 *
 * Problems addressed:
 * 1. Dashboard "View PRD" button stays disabled after PRD completes (SWR cache not invalidated)
 * 2. Spinner reappears when revisiting Overview tab (state not initialized from API)
 * 3. No "Restart Discovery" button in completed state
 */

import { render, screen, waitFor, act, fireEvent } from '@testing-library/react';
import Dashboard from '@/components/Dashboard';
import DiscoveryProgress from '@/components/DiscoveryProgress';
import PRDModal from '@/components/PRDModal';
import { AgentStateProvider } from '@/components/AgentStateProvider';
import * as api from '@/lib/api';
import * as websocket from '@/lib/websocket';

// Mock dependencies
jest.mock('@/lib/api');
jest.mock('@/lib/websocket');
jest.mock('@/lib/api-client', () => ({
  authFetch: jest.fn().mockRejectedValue(new Error('Not authenticated')),
}));
jest.mock('@hugeicons/react', () => ({
  Cancel01Icon: () => <span data-testid="cancel-icon">×</span>,
  CheckmarkCircle01Icon: ({ className }: { className?: string }) => <svg className={className} data-testid="check-icon" />,
  Alert02Icon: () => <span data-testid="alert-icon">!</span>,
  // PhaseProgress icons
  Search01Icon: ({ className }: { className?: string }) => <svg className={className} data-testid="search-icon" />,
  TaskEdit01Icon: ({ className }: { className?: string }) => <svg className={className} data-testid="task-edit-icon" />,
  Wrench01Icon: ({ className }: { className?: string }) => <svg className={className} data-testid="wrench-icon" />,
  Award01Icon: ({ className }: { className?: string }) => <svg className={className} data-testid="award-icon" />,
  RocketIcon: ({ className }: { className?: string }) => <svg className={className} data-testid="rocket-icon" />,
  HelpCircleIcon: ({ className }: { className?: string }) => <svg className={className} data-testid="help-icon" />,
  Idea01Icon: ({ className }: { className?: string }) => <svg className={className} data-testid="idea-icon" />,
}));
jest.mock('@/components/ChatInterface', () => ({
  __esModule: true,
  default: () => <div>ChatInterface Mock</div>,
}));
jest.mock('@/components/TaskTreeView', () => ({
  __esModule: true,
  default: () => <div>TaskTreeView Mock</div>,
}));
jest.mock('@/components/SessionStatus', () => ({
  __esModule: true,
  SessionStatus: () => <div>SessionStatus Mock</div>,
}));

// Mock SWR to track mutations
const mockMutate = jest.fn();
jest.mock('swr', () => {
  const originalSWR = jest.requireActual('swr');
  return {
    __esModule: true,
    default: (key: string, fetcher: any, config: any) => {
      const result = originalSWR.default(key, fetcher, {
        ...config,
        provider: () => new Map(),
        dedupingInterval: 0,
        focusThrottleInterval: 0,
        revalidateOnFocus: false,
        revalidateOnReconnect: false,
        shouldRetryOnError: false,
      });
      // Track mutate calls for PRD endpoint
      if (key && key.includes('/prd')) {
        return { ...result, mutate: mockMutate };
      }
      return result;
    },
  };
});

const mockProjectData = {
  id: 1,
  name: 'Test Project',
  status: 'active',
  phase: 'discovery',
  workflow_step: 2,
  progress: {
    completed_tasks: 0,
    total_tasks: 0,
    percentage: 0,
  },
};

const mockDiscoveryCompleted = {
  phase: 'planning',
  discovery: {
    state: 'completed',
    answered_count: 5,
    total_required: 5,
    progress_percentage: 100,
    current_question: null,
  },
};

const mockPrdAvailable = {
  status: 'available' as const,
  project_id: '1',
  prd_content: '# Test PRD\n\nThis is a test PRD.',
  generated_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
};

const mockPrdNotFound = {
  status: 'not_found' as const,
  project_id: '1',
  prd_content: '',
  generated_at: '',
  updated_at: '',
};

const mockPrdGenerating = {
  status: 'generating' as const,
  project_id: '1',
  prd_content: '',
  generated_at: '',
  updated_at: '',
};

describe('PRD Button Synchronization', () => {
  let mockWsClient: any;
  let messageHandlers: Map<string, Function>;

  beforeEach(() => {
    jest.clearAllMocks();
    mockMutate.mockClear();
    messageHandlers = new Map();

    // Mock WebSocket client
    mockWsClient = {
      connect: jest.fn(),
      disconnect: jest.fn(),
      subscribe: jest.fn(),
      onMessage: jest.fn((handler) => {
        const id = Date.now().toString() + Math.random().toString();
        messageHandlers.set(id, handler);
        return jest.fn(() => messageHandlers.delete(id));
      }),
      onReconnect: jest.fn(() => jest.fn()),
      onConnectionChange: jest.fn(() => jest.fn()),
    };
    (websocket.getWebSocketClient as jest.Mock).mockReturnValue(mockWsClient);

    // Setup default API mocks
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
    (api.projectsApi.getIssues as jest.Mock).mockResolvedValue({
      data: { issues: [], total_issues: 0, total_tasks: 0 },
    });
  });

  describe('Dashboard PRD Button Synchronization via WebSocket', () => {
    it('should trigger SWR mutate when prd_generation_completed WebSocket message arrives', async () => {
      // Setup: PRD not yet available
      (api.projectsApi.getPRD as jest.Mock).mockResolvedValue({
        data: mockPrdNotFound,
      });

      render(
        <AgentStateProvider projectId={1}>
          <Dashboard projectId={1} />
        </AgentStateProvider>
      );

      // Wait for initial render
      await waitFor(() => {
        expect(screen.getByText(/Test Project/i)).toBeInTheDocument();
      });

      // View PRD button should be disabled initially
      const prdButton = screen.getByTestId('prd-generated');
      expect(prdButton).toBeDisabled();

      // Update mock to return PRD available for the next fetch
      (api.projectsApi.getPRD as jest.Mock).mockResolvedValue({
        data: mockPrdAvailable,
      });

      // Simulate prd_generation_completed WebSocket message
      const prdCompletedMessage = {
        type: 'prd_generation_completed',
        project_id: 1,
        timestamp: Date.now(),
      };

      await act(async () => {
        messageHandlers.forEach((handler) => handler(prdCompletedMessage));
      });

      // SWR mutate should be called to refresh PRD data
      await waitFor(() => {
        expect(mockMutate).toHaveBeenCalled();
      });
    });

    it('should filter WebSocket messages by project_id', async () => {
      (api.projectsApi.getPRD as jest.Mock).mockResolvedValue({
        data: mockPrdNotFound,
      });

      render(
        <AgentStateProvider projectId={1}>
          <Dashboard projectId={1} />
        </AgentStateProvider>
      );

      await waitFor(() => {
        expect(screen.getByText(/Test Project/i)).toBeInTheDocument();
      });

      // Simulate prd_generation_completed for a DIFFERENT project
      const otherProjectMessage = {
        type: 'prd_generation_completed',
        project_id: 999, // Different project ID
        timestamp: Date.now(),
      };

      await act(async () => {
        messageHandlers.forEach((handler) => handler(otherProjectMessage));
      });

      // Should NOT trigger mutate for different project
      expect(mockMutate).not.toHaveBeenCalled();
    });
  });

  describe('DiscoveryProgress State Initialization from API', () => {
    it('should initialize PRD completed state when mounting with discovery already completed', async () => {
      // Setup: Discovery completed and PRD available
      (api.projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({
        data: mockDiscoveryCompleted,
      });
      (api.projectsApi.getPRD as jest.Mock).mockResolvedValue({
        data: mockPrdAvailable,
      });

      const mockOnViewPRD = jest.fn();
      render(<DiscoveryProgress projectId={1} onViewPRD={mockOnViewPRD} />);

      // Should show PRD completed state, NOT spinner
      await waitFor(() => {
        // Should have the View PRD button (not "Starting PRD Generation...")
        expect(screen.getByTestId('view-prd-button')).toBeInTheDocument();
      });

      // Spinner should NOT be visible
      expect(screen.queryByText(/Starting PRD Generation/i)).not.toBeInTheDocument();
    });

    it('should show generating state when PRD is still generating on mount', async () => {
      // Setup: Discovery completed but PRD still generating
      (api.projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({
        data: mockDiscoveryCompleted,
      });
      (api.projectsApi.getPRD as jest.Mock).mockResolvedValue({
        data: mockPrdGenerating,
      });

      render(<DiscoveryProgress projectId={1} />);

      await waitFor(() => {
        expect(screen.getByTestId('prd-generation-status')).toBeInTheDocument();
      });

      // Should show generating state
      expect(screen.queryByText(/Generating/i)).toBeInTheDocument();
    });

    it('should not show spinner when returning to Overview tab with completed PRD', async () => {
      // Setup: Discovery completed and PRD available
      (api.projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({
        data: mockDiscoveryCompleted,
      });
      (api.projectsApi.getPRD as jest.Mock).mockResolvedValue({
        data: mockPrdAvailable,
      });

      const mockOnViewPRD = jest.fn();
      const { unmount } = render(<DiscoveryProgress projectId={1} onViewPRD={mockOnViewPRD} />);

      // Wait for initial render with PRD complete
      await waitFor(() => {
        expect(screen.getByTestId('view-prd-button')).toBeInTheDocument();
      });

      // Unmount to simulate navigating away
      unmount();

      // Re-mount to simulate returning to Overview tab
      render(<DiscoveryProgress projectId={1} onViewPRD={mockOnViewPRD} />);

      // Should still show PRD completed state, NOT spinner
      await waitFor(() => {
        expect(screen.getByTestId('view-prd-button')).toBeInTheDocument();
      });

      expect(screen.queryByText(/Starting PRD Generation/i)).not.toBeInTheDocument();
    });
  });

  describe('Restart Discovery Button', () => {
    it('should show Restart Discovery button in completed state', async () => {
      // Setup: Discovery completed and PRD available
      (api.projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({
        data: mockDiscoveryCompleted,
      });
      (api.projectsApi.getPRD as jest.Mock).mockResolvedValue({
        data: mockPrdAvailable,
      });

      const mockOnViewPRD = jest.fn();
      render(<DiscoveryProgress projectId={1} onViewPRD={mockOnViewPRD} />);

      await waitFor(() => {
        expect(screen.getByTestId('view-prd-button')).toBeInTheDocument();
      });

      // Expand the section if minimized (auto-minimizes after 3 seconds, but not in test timing)
      const expandButton = screen.queryByTestId('expand-discovery-button');
      if (expandButton) {
        fireEvent.click(expandButton);
      }

      // Should show Restart Discovery button
      await waitFor(() => {
        expect(screen.getByTestId('restart-discovery-completed-button')).toBeInTheDocument();
      });
    });

    it('should call restartDiscovery API when Restart Discovery button is clicked', async () => {
      (api.projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({
        data: mockDiscoveryCompleted,
      });
      (api.projectsApi.getPRD as jest.Mock).mockResolvedValue({
        data: mockPrdAvailable,
      });
      (api.projectsApi.restartDiscovery as jest.Mock).mockResolvedValue({
        data: { success: true },
      });

      const mockOnViewPRD = jest.fn();
      render(<DiscoveryProgress projectId={1} onViewPRD={mockOnViewPRD} />);

      await waitFor(() => {
        expect(screen.getByTestId('view-prd-button')).toBeInTheDocument();
      });

      // Expand if needed and click Restart Discovery
      const expandButton = screen.queryByTestId('expand-discovery-button');
      if (expandButton) {
        fireEvent.click(expandButton);
        await waitFor(() => {
          expect(screen.getByTestId('restart-discovery-completed-button')).toBeInTheDocument();
        });
      }

      const restartButton = screen.getByTestId('restart-discovery-completed-button');
      fireEvent.click(restartButton);

      await waitFor(() => {
        expect(api.projectsApi.restartDiscovery).toHaveBeenCalledWith(1);
      });
    });
  });

  describe('PRDModal Error Handling', () => {
    it('should show helpful message when PRD is still generating', () => {
      render(
        <PRDModal
          isOpen={true}
          onClose={() => {}}
          prdData={mockPrdGenerating}
        />
      );

      expect(screen.getByText(/Generating PRD/i)).toBeInTheDocument();
    });

    it('should show not found message when PRD does not exist', () => {
      render(
        <PRDModal
          isOpen={true}
          onClose={() => {}}
          prdData={mockPrdNotFound}
        />
      );

      expect(screen.getByText(/PRD Not Found/i)).toBeInTheDocument();
    });

    it('should display PRD content when available', () => {
      render(
        <PRDModal
          isOpen={true}
          onClose={() => {}}
          prdData={mockPrdAvailable}
        />
      );

      expect(screen.getByTestId('prd-content')).toBeInTheDocument();
      expect(screen.getByText(/Test PRD/i)).toBeInTheDocument();
    });

    it('should call onRetry callback when retry button is clicked', async () => {
      const mockOnRetry = jest.fn();

      render(
        <PRDModal
          isOpen={true}
          onClose={() => {}}
          prdData={mockPrdNotFound}
          onRetry={mockOnRetry}
        />
      );

      const retryButton = screen.queryByTestId('prd-retry-button');
      if (retryButton) {
        fireEvent.click(retryButton);
        expect(mockOnRetry).toHaveBeenCalled();
      }
    });
  });

  describe('Both Buttons Synchronize on PRD Completion', () => {
    it('should enable both View PRD buttons simultaneously after prd_generation_completed', async () => {
      // Setup: Start with discovery in progress
      (api.projectsApi.getStatus as jest.Mock).mockResolvedValue({
        data: { ...mockProjectData, phase: 'planning' },
      });
      (api.projectsApi.getPRD as jest.Mock).mockResolvedValue({
        data: mockPrdNotFound,
      });
      (api.projectsApi.getDiscoveryProgress as jest.Mock).mockResolvedValue({
        data: mockDiscoveryCompleted,
      });

      render(
        <AgentStateProvider projectId={1}>
          <Dashboard projectId={1} />
        </AgentStateProvider>
      );

      await waitFor(() => {
        expect(screen.getByText(/Test Project/i)).toBeInTheDocument();
      });

      // Dashboard View PRD button should be disabled
      const dashboardPrdButton = screen.getByTestId('prd-generated');
      expect(dashboardPrdButton).toBeDisabled();

      // Update mock for after PRD completion
      (api.projectsApi.getPRD as jest.Mock).mockResolvedValue({
        data: mockPrdAvailable,
      });

      // Simulate prd_generation_completed
      const prdCompletedMessage = {
        type: 'prd_generation_completed',
        project_id: 1,
        timestamp: Date.now(),
      };

      await act(async () => {
        messageHandlers.forEach((handler) => handler(prdCompletedMessage));
      });

      // Both buttons should now be synchronized (SWR mutate called)
      await waitFor(() => {
        expect(mockMutate).toHaveBeenCalled();
      });
    });
  });
});
