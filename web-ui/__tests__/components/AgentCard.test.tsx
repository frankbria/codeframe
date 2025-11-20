/**
 * AgentCard Component Tests
 * Feature: 013-context-panel-integration (Phase 6)
 */

import { render, screen, fireEvent } from '@testing-library/react';
import AgentCard, { Agent } from '@/components/AgentCard';

describe('AgentCard - Navigation (User Story 4)', () => {
  const mockAgent: Agent = {
    id: 'agent-001',
    type: 'backend',
    status: 'busy',
    tasksCompleted: 5,
  };

  /**
   * T028 [P] [US4]: AgentCard accepts onClick prop and calls it
   * RED: This test will FAIL until onAgentClick prop is verified
   */
  it('accepts onAgentClick prop and calls it when clicked', () => {
    const onAgentClickMock = jest.fn();
    const { container } = render(
      <AgentCard agent={mockAgent} onAgentClick={onAgentClickMock} />
    );

    const card = container.firstChild as HTMLElement;
    fireEvent.click(card);

    expect(onAgentClickMock).toHaveBeenCalledTimes(1);
    expect(onAgentClickMock).toHaveBeenCalledWith('agent-001');
  });

  /**
   * T031 [P] [US4]: AgentCard shows cursor-pointer when clickable
   * RED: This test will FAIL until cursor-pointer class is applied
   */
  it('shows cursor-pointer when onAgentClick provided', () => {
    const onAgentClickMock = jest.fn();
    const { container } = render(
      <AgentCard agent={mockAgent} onAgentClick={onAgentClickMock} />
    );

    const card = container.firstChild as HTMLElement;
    expect(card).toHaveClass('cursor-pointer');
  });

  it('renders without onClick callback', () => {
    const { container } = render(<AgentCard agent={mockAgent} />);

    const card = container.firstChild as HTMLElement;
    expect(card).toBeInTheDocument();
    // Should still have cursor-pointer since AgentCard is always clickable
    expect(card).toHaveClass('cursor-pointer');
  });
});
