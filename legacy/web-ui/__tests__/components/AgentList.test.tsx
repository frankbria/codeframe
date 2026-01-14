/**
 * Unit tests for AgentList component
 *
 * Tests phase-awareness functionality for the "late-joining user" bug fix.
 * During planning phase, shows informational message instead of "No agents assigned"
 * since agents haven't been created yet (which is expected during planning).
 *
 * Part of Phase-Awareness Pattern implementation
 */

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { SWRConfig } from 'swr';
import { AgentList } from '../../src/components/AgentList';
import * as agentAssignmentApi from '../../src/api/agentAssignment';
import type { IssuesResponse } from '../../src/types/api';
import type { AgentAssignment } from '../../src/types/agentAssignment';

// Mock the agent assignment API
jest.mock('../../src/api/agentAssignment');

const mockGetAgentsForProject = agentAssignmentApi.getAgentsForProject as jest.MockedFunction<
  typeof agentAssignmentApi.getAgentsForProject
>;

// Wrapper to clear SWR cache between tests
const SWRWrapper: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>
    {children}
  </SWRConfig>
);

// Custom render that clears SWR cache
const renderWithSWR = (ui: React.ReactElement) => {
  return render(ui, { wrapper: SWRWrapper });
};

describe('AgentList', () => {
  // Sample agent assignment data matching AgentAssignment interface
  const mockAgentAssignment: AgentAssignment = {
    agent_id: 'agent-123',
    type: 'backend',
    provider: 'claude',
    maturity_level: 'senior',
    status: 'idle',
    current_task_id: null,
    last_heartbeat: '2025-01-01T00:00:00Z',
    role: 'worker',
    assigned_at: '2025-01-01T00:00:00Z',
    unassigned_at: null,
    is_active: true,
  };

  // Sample issues data for planning phase
  const mockIssuesData: IssuesResponse = {
    issues: [],
    total_issues: 2,
    total_tasks: 24,
  };

  beforeEach(() => {
    jest.clearAllMocks();
    // Reset to default mock implementation
    mockGetAgentsForProject.mockResolvedValue([]);
  });

  describe('Phase-Aware Empty State', () => {
    it('shows planning phase message when phase is planning and no agents', async () => {
      // ARRANGE: Planning phase with no agents (expected state during planning)
      mockGetAgentsForProject.mockResolvedValue([]);

      // ACT
      renderWithSWR(
        <AgentList
          projectId={1}
          phase="planning"
          issuesData={mockIssuesData}
        />
      );

      // ASSERT: Should show planning-specific message, not "No Agents Assigned"
      await waitFor(() => {
        expect(screen.getByTestId('planning-phase-message')).toBeInTheDocument();
      });

      // Should NOT show the default empty state message
      expect(screen.queryByText('No Agents Assigned')).not.toBeInTheDocument();
    });

    it('shows task count in planning phase message', async () => {
      mockGetAgentsForProject.mockResolvedValue([]);

      renderWithSWR(
        <AgentList
          projectId={1}
          phase="planning"
          issuesData={mockIssuesData}
        />
      );

      await waitFor(() => {
        // Task count appears in the badge element
        const elements = screen.getAllByText(/24 tasks/i);
        expect(elements.length).toBeGreaterThan(0);
      });
    });

    it('shows default empty state during development phase with no agents', async () => {
      // ARRANGE: Development phase with no agents (unusual, but possible)
      mockGetAgentsForProject.mockResolvedValue([]);

      // ACT
      renderWithSWR(
        <AgentList
          projectId={1}
          phase="development"
          issuesData={mockIssuesData}
        />
      );

      // ASSERT: Should show default "No Agents Assigned" message
      await waitFor(() => {
        expect(screen.getByText('No Agents Assigned')).toBeInTheDocument();
      });

      // Should NOT show planning phase message
      expect(screen.queryByTestId('planning-phase-message')).not.toBeInTheDocument();
    });

    it('shows default empty state when phase is undefined (backward compatibility)', async () => {
      mockGetAgentsForProject.mockResolvedValue([]);

      renderWithSWR(<AgentList projectId={1} />);

      await waitFor(() => {
        expect(screen.getByText('No Agents Assigned')).toBeInTheDocument();
      });
    });
  });

  describe('Agent Display', () => {
    it('shows agent cards when agents are present regardless of phase', async () => {
      // ARRANGE: Agents present (development phase)
      mockGetAgentsForProject.mockResolvedValue([mockAgentAssignment]);

      // ACT
      renderWithSWR(
        <AgentList
          projectId={1}
          phase="development"
          issuesData={mockIssuesData}
        />
      );

      // ASSERT: Should show agent count and card
      await waitFor(() => {
        expect(screen.getByText(/1 agent assigned/i)).toBeInTheDocument();
      });
    });

    it('shows agents during planning phase if they exist (edge case)', async () => {
      // Edge case: agents might exist during planning (e.g., from previous runs)
      mockGetAgentsForProject.mockResolvedValue([mockAgentAssignment]);

      renderWithSWR(
        <AgentList
          projectId={1}
          phase="planning"
          issuesData={mockIssuesData}
        />
      );

      await waitFor(() => {
        expect(screen.getByText(/1 agent assigned/i)).toBeInTheDocument();
      });
    });

    it('handles review phase correctly', async () => {
      mockGetAgentsForProject.mockResolvedValue([mockAgentAssignment]);

      renderWithSWR(
        <AgentList
          projectId={1}
          phase="review"
          issuesData={mockIssuesData}
        />
      );

      await waitFor(() => {
        expect(screen.getByText(/1 agent assigned/i)).toBeInTheDocument();
      });
    });
  });

  describe('Loading and Error States', () => {
    it('shows loading state initially', async () => {
      // Don't resolve the promise immediately
      mockGetAgentsForProject.mockImplementation(() => new Promise(() => {}));

      renderWithSWR(<AgentList projectId={1} />);

      // SWR shows loading state immediately
      expect(screen.getByText(/Loading agents/i)).toBeInTheDocument();
    });

    it('shows error state when API fails', async () => {
      mockGetAgentsForProject.mockRejectedValue(new Error('API Error'));

      renderWithSWR(<AgentList projectId={1} />);

      await waitFor(() => {
        expect(screen.getByText(/Failed to Load Agents/i)).toBeInTheDocument();
      });
    });
  });

  describe('Planning Phase Message Content', () => {
    it('includes informational icon', async () => {
      mockGetAgentsForProject.mockResolvedValue([]);

      renderWithSWR(
        <AgentList
          projectId={1}
          phase="planning"
          issuesData={mockIssuesData}
        />
      );

      await waitFor(() => {
        // Check for BotIcon (Hugeicons adds data-testid automatically)
        expect(screen.getByTestId('bot-icon')).toBeInTheDocument();
      });
    });

    it('explains when agents will be created', async () => {
      mockGetAgentsForProject.mockResolvedValue([]);

      renderWithSWR(
        <AgentList
          projectId={1}
          phase="planning"
          issuesData={mockIssuesData}
        />
      );

      await waitFor(() => {
        expect(screen.getByText(/development begins/i)).toBeInTheDocument();
      });
    });

    it('handles missing issuesData gracefully during planning', async () => {
      mockGetAgentsForProject.mockResolvedValue([]);

      renderWithSWR(
        <AgentList
          projectId={1}
          phase="planning"
          // No issuesData prop
        />
      );

      // Should still show planning message without task count
      await waitFor(() => {
        expect(screen.getByTestId('planning-phase-message')).toBeInTheDocument();
      });
    });
  });

  describe('Phase Transitions', () => {
    it('updates display when phase changes from planning to development', async () => {
      mockGetAgentsForProject.mockResolvedValue([]);

      const { rerender } = renderWithSWR(
        <AgentList
          projectId={1}
          phase="planning"
          issuesData={mockIssuesData}
        />
      );

      // Initially shows planning message
      await waitFor(() => {
        expect(screen.getByTestId('planning-phase-message')).toBeInTheDocument();
      });

      // Rerender with development phase (wrap in SWRConfig manually for rerender)
      rerender(
        <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>
          <AgentList
            projectId={1}
            phase="development"
            issuesData={mockIssuesData}
          />
        </SWRConfig>
      );

      // Should now show default empty state
      await waitFor(() => {
        expect(screen.getByText('No Agents Assigned')).toBeInTheDocument();
        expect(screen.queryByTestId('planning-phase-message')).not.toBeInTheDocument();
      });
    });
  });
});
