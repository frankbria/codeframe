/**
 * Dashboard Component Tests
 * Feature: 013-context-panel-integration
 *
 * Test-Driven Development (TDD) approach:
 * - RED: Tests written first (will fail)
 * - GREEN: Implementation makes tests pass
 * - REFACTOR: Improve code quality
 */

import { render, screen, fireEvent } from '@testing-library/react';
import Dashboard from '@/components/Dashboard';

// Mock dependencies
jest.mock('@/hooks/useAgentState', () => ({
  useAgentState: () => ({
    agents: [
      { id: 'agent-001', type: 'backend', status: 'working' as const },
      { id: 'agent-002', type: 'frontend', status: 'idle' as const },
    ],
    tasks: [],
    activity: [],
    projectProgress: null,
    wsConnected: true,
  }),
}));

jest.mock('@/components/context/ContextPanel', () => ({
  ContextPanel: ({ agentId, projectId }: { agentId: string; projectId: number }) => (
    <div data-testid="context-panel">
      Agent: {agentId}, Project: {projectId}
    </div>
  ),
}));

describe('Dashboard - Context Tab (User Story 1)', () => {
  /**
   * T004 [P] [US1]: Dashboard renders Overview and Context tabs
   * RED: This test will FAIL until tabs are implemented
   */
  it('renders Overview and Context tabs', () => {
    render(<Dashboard projectId={123} />);

    expect(screen.getByRole('tab', { name: /overview/i })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /context/i })).toBeInTheDocument();
  });

  /**
   * T005 [P] [US1]: Overview tab is active by default
   * RED: This test will FAIL until default tab state is set
   */
  it('shows Overview tab active by default', () => {
    render(<Dashboard projectId={123} />);

    const overviewTab = screen.getByRole('tab', { name: /overview/i });
    expect(overviewTab).toHaveAttribute('aria-selected', 'true');
  });

  /**
   * T006 [P] [US1]: Clicking Context tab switches active tab
   * RED: This test will FAIL until tab switching is implemented
   */
  it('switches to Context tab when clicked', () => {
    render(<Dashboard projectId={123} />);

    const contextTab = screen.getByRole('tab', { name: /context/i });
    fireEvent.click(contextTab);

    expect(contextTab).toHaveAttribute('aria-selected', 'true');
  });

  /**
   * T007 [P] [US1]: Active tab has correct styling
   * RED: This test will FAIL until tab styling is applied
   */
  it('shows active tab with highlighted style', () => {
    render(<Dashboard projectId={123} />);

    const contextTab = screen.getByRole('tab', { name: /context/i });
    fireEvent.click(contextTab);

    // Check for blue text and border styling
    expect(contextTab).toHaveClass('text-blue-600');
    expect(contextTab).toHaveClass('border-blue-600');
  });
});
