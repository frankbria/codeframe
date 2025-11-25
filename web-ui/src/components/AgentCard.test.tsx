/**
 * Tests for AgentCard component (cf-8ip: Phase 5.1)
 */

import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';
import { AgentCard, Agent } from './AgentCard';

describe('AgentCard Component', () => {
  const mockOnAgentClick = jest.fn();

  beforeEach(() => {
    mockOnAgentClick.mockClear();
  });

  describe('Display Agent Information', () => {
    it('should display agent ID', () => {
      const agent: Agent = {
        id: 'backend-worker-001',
        type: 'backend-worker',
        status: 'idle',
        tasksCompleted: 0,
      };

      render(<AgentCard agent={agent} onAgentClick={mockOnAgentClick} />);

      expect(screen.getByText('backend-worker-001')).toBeInTheDocument();
    });

    it('should display formatted agent type', () => {
      const agent: Agent = {
        id: 'frontend-specialist-001',
        type: 'frontend-specialist',
        status: 'idle',
        tasksCompleted: 5,
      };

      render(<AgentCard agent={agent} onAgentClick={mockOnAgentClick} />);

      expect(screen.getByText('Frontend Specialist')).toBeInTheDocument();
    });

    it('should display tasks completed counter', () => {
      const agent: Agent = {
        id: 'test-engineer-001',
        type: 'test-engineer',
        status: 'busy',
        currentTask: 15,
        tasksCompleted: 7,
      };

      render(<AgentCard agent={agent} onAgentClick={mockOnAgentClick} />);

      expect(screen.getByText('Tasks Completed')).toBeInTheDocument();
      expect(screen.getByText('7')).toBeInTheDocument();
    });
  });

  describe('Status Colors', () => {
    it('should show green for idle status', () => {
      const agent: Agent = {
        id: 'agent-001',
        type: 'backend',
        status: 'idle',
        tasksCompleted: 0,
      };

      const { container: _container } = render(<AgentCard agent={agent} onAgentClick={mockOnAgentClick} />);

      const card = container.firstChild as HTMLElement;
      expect(card).toHaveClass('bg-green-100', 'border-green-500', 'text-green-800');
      expect(screen.getByText('Idle')).toBeInTheDocument();
    });

    it('should show yellow for busy status', () => {
      const agent: Agent = {
        id: 'agent-002',
        type: 'backend',
        status: 'busy',
        currentTask: 10,
        tasksCompleted: 3,
      };

      const { container: _container } = render(<AgentCard agent={agent} onAgentClick={mockOnAgentClick} />);

      const card = container.firstChild as HTMLElement;
      expect(card).toHaveClass('bg-yellow-100', 'border-yellow-500', 'text-yellow-800');
      expect(screen.getByText('Working')).toBeInTheDocument();
    });

    it('should show red for blocked status', () => {
      const agent: Agent = {
        id: 'agent-003',
        type: 'backend',
        status: 'blocked',
        blockedBy: [5, 6],
        tasksCompleted: 1,
      };

      const { container: _container } = render(<AgentCard agent={agent} onAgentClick={mockOnAgentClick} />);

      const card = container.firstChild as HTMLElement;
      expect(card).toHaveClass('bg-red-100', 'border-red-500', 'text-red-800');
      expect(screen.getByText('Blocked')).toBeInTheDocument();
    });
  });

  describe('Current Task Display', () => {
    it('should show current task when agent is busy', () => {
      const agent: Agent = {
        id: 'agent-004',
        type: 'backend-worker',
        status: 'busy',
        currentTask: 42,
        tasksCompleted: 5,
      };

      render(<AgentCard agent={agent} onAgentClick={mockOnAgentClick} />);

      expect(screen.getByText('Current Task:')).toBeInTheDocument();
      expect(screen.getByText('Task #42')).toBeInTheDocument();
    });

    it('should NOT show current task when agent is idle', () => {
      const agent: Agent = {
        id: 'agent-005',
        type: 'backend',
        status: 'idle',
        tasksCompleted: 2,
      };

      render(<AgentCard agent={agent} onAgentClick={mockOnAgentClick} />);

      expect(screen.queryByText('Current Task:')).not.toBeInTheDocument();
      expect(screen.getByText('Ready for work')).toBeInTheDocument();
    });

    it('should NOT show current task when agent is blocked', () => {
      const agent: Agent = {
        id: 'agent-006',
        type: 'frontend',
        status: 'blocked',
        blockedBy: [10],
        tasksCompleted: 3,
      };

      render(<AgentCard agent={agent} onAgentClick={mockOnAgentClick} />);

      expect(screen.queryByText('Current Task:')).not.toBeInTheDocument();
    });
  });

  describe('Blocked Status Display', () => {
    it('should show blocked by information when blocked by single task', () => {
      const agent: Agent = {
        id: 'agent-007',
        type: 'test',
        status: 'blocked',
        blockedBy: [15],
        tasksCompleted: 1,
      };

      render(<AgentCard agent={agent} onAgentClick={mockOnAgentClick} />);

      expect(screen.getByText('Blocked By:')).toBeInTheDocument();
      expect(screen.getByText('Task #15')).toBeInTheDocument();
    });

    it('should show count when blocked by multiple tasks', () => {
      const agent: Agent = {
        id: 'agent-008',
        type: 'backend',
        status: 'blocked',
        blockedBy: [10, 11, 12],
        tasksCompleted: 2,
      };

      render(<AgentCard agent={agent} onAgentClick={mockOnAgentClick} />);

      expect(screen.getByText('Blocked By:')).toBeInTheDocument();
      expect(screen.getByText('3 tasks')).toBeInTheDocument();
    });

    it('should NOT show blocked by section when not blocked', () => {
      const agent: Agent = {
        id: 'agent-009',
        type: 'backend',
        status: 'idle',
        tasksCompleted: 0,
      };

      render(<AgentCard agent={agent} onAgentClick={mockOnAgentClick} />);

      expect(screen.queryByText('Blocked By:')).not.toBeInTheDocument();
    });
  });

  describe('Agent Type Badges', () => {
    it('should show backend badge with correct icon', () => {
      const agent: Agent = {
        id: 'agent-010',
        type: 'backend-worker',
        status: 'idle',
        tasksCompleted: 0,
      };

      render(<AgentCard agent={agent} onAgentClick={mockOnAgentClick} />);

      const badge = screen.getByText('Backend Worker').parentElement;
      expect(badge).toHaveClass('bg-blue-100', 'text-blue-800');
      expect(screen.getByText('⚙️')).toBeInTheDocument();
    });

    it('should show frontend badge with correct icon', () => {
      const agent: Agent = {
        id: 'agent-011',
        type: 'frontend-specialist',
        status: 'idle',
        tasksCompleted: 0,
      };

      render(<AgentCard agent={agent} onAgentClick={mockOnAgentClick} />);

      const badge = screen.getByText('Frontend Specialist').parentElement;
      expect(badge).toHaveClass('bg-purple-100', 'text-purple-800');
      expect(screen.getByText('🎨')).toBeInTheDocument();
    });

    it('should show test badge with correct icon', () => {
      const agent: Agent = {
        id: 'agent-012',
        type: 'test-engineer',
        status: 'idle',
        tasksCompleted: 0,
      };

      render(<AgentCard agent={agent} onAgentClick={mockOnAgentClick} />);

      const badge = screen.getByText('Test Engineer').parentElement;
      expect(badge).toHaveClass('bg-emerald-100', 'text-emerald-800');
      expect(screen.getByText('🧪')).toBeInTheDocument();
    });

    it('should show default badge for unknown agent type', () => {
      const agent: Agent = {
        id: 'agent-013',
        type: 'custom-agent',
        status: 'idle',
        tasksCompleted: 0,
      };

      render(<AgentCard agent={agent} onAgentClick={mockOnAgentClick} />);

      const badge = screen.getByText('Custom Agent').parentElement;
      expect(badge).toHaveClass('bg-gray-100', 'text-gray-800');
      expect(screen.getByText('🤖')).toBeInTheDocument();
    });
  });

  describe('Click Interaction', () => {
    it('should call onAgentClick when card is clicked', () => {
      const agent: Agent = {
        id: 'agent-014',
        type: 'backend',
        status: 'idle',
        tasksCompleted: 0,
      };

      const { container: _container } = render(<AgentCard agent={agent} onAgentClick={mockOnAgentClick} />);

      const card = container.firstChild as HTMLElement;
      fireEvent.click(card);

      expect(mockOnAgentClick).toHaveBeenCalledTimes(1);
      expect(mockOnAgentClick).toHaveBeenCalledWith('agent-014');
    });

    it('should handle optional onAgentClick callback', () => {
      const agent: Agent = {
        id: 'agent-015',
        type: 'backend',
        status: 'idle',
        tasksCompleted: 0,
      };

      const { container: _container } = render(<AgentCard agent={agent} />);

      const card = container.firstChild as HTMLElement;
      // Should not throw error when onAgentClick is undefined
      expect(() => fireEvent.click(card)).not.toThrow();
    });
  });

  describe('Status Indicator', () => {
    it('should show animated pulse dot for all statuses', () => {
      const statuses: Array<'idle' | 'busy' | 'blocked'> = ['idle', 'busy', 'blocked'];

      statuses.forEach((status) => {
        const agent: Agent = {
          id: `agent-${status}`,
          type: 'backend',
          status,
          tasksCompleted: 0,
        };

        const { container: _container } = render(<AgentCard agent={agent} />);

        const dot = container.querySelector('.animate-pulse');
        expect(dot).toBeInTheDocument();
        expect(dot).toHaveClass('w-3', 'h-3', 'rounded-full');
      });
    });
  });

  describe('Responsive Design', () => {
    it('should have proper styling classes for responsiveness', () => {
      const agent: Agent = {
        id: 'agent-016',
        type: 'backend',
        status: 'idle',
        tasksCompleted: 0,
      };

      const { container: _container } = render(<AgentCard agent={agent} onAgentClick={mockOnAgentClick} />);

      const card = container.firstChild as HTMLElement;
      expect(card).toHaveClass('rounded-lg', 'border-2', 'p-4');
      expect(card).toHaveClass('transition-all', 'duration-200');
      expect(card).toHaveClass('hover:shadow-md', 'cursor-pointer');
    });

    it('should truncate long agent IDs', () => {
      const agent: Agent = {
        id: 'very-long-agent-identifier-that-should-be-truncated',
        type: 'backend',
        status: 'idle',
        tasksCompleted: 0,
      };

      const { container: _container } = render(<AgentCard agent={agent} onAgentClick={mockOnAgentClick} />);

      const agentIdElement = screen.getByText(agent.id);
      expect(agentIdElement).toHaveClass('truncate', 'max-w-[150px]');
      expect(agentIdElement).toHaveAttribute('title', agent.id);
    });
  });

  describe('Edge Cases', () => {
    it('should handle zero tasks completed', () => {
      const agent: Agent = {
        id: 'agent-017',
        type: 'backend',
        status: 'idle',
        tasksCompleted: 0,
      };

      render(<AgentCard agent={agent} onAgentClick={mockOnAgentClick} />);

      expect(screen.getByText('0')).toBeInTheDocument();
    });

    it('should handle large tasks completed number', () => {
      const agent: Agent = {
        id: 'agent-018',
        type: 'backend',
        status: 'idle',
        tasksCompleted: 9999,
      };

      render(<AgentCard agent={agent} onAgentClick={mockOnAgentClick} />);

      expect(screen.getByText('9999')).toBeInTheDocument();
    });

    it('should handle undefined currentTask gracefully', () => {
      const agent: Agent = {
        id: 'agent-019',
        type: 'backend',
        status: 'busy',
        tasksCompleted: 5,
        // currentTask is undefined
      };

      render(<AgentCard agent={agent} onAgentClick={mockOnAgentClick} />);

      // Should not show current task section when undefined
      expect(screen.queryByText('Current Task:')).not.toBeInTheDocument();
    });

    it('should handle empty blockedBy array', () => {
      const agent: Agent = {
        id: 'agent-020',
        type: 'backend',
        status: 'blocked',
        blockedBy: [],
        tasksCompleted: 2,
      };

      render(<AgentCard agent={agent} onAgentClick={mockOnAgentClick} />);

      // Should not show blocked by section when array is empty
      expect(screen.queryByText('Blocked By:')).not.toBeInTheDocument();
    });
  });
});
