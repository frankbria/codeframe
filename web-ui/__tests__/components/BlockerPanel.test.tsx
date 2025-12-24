/**
 * BlockerPanel Component Tests
 * Tests for blocker list display and sorting (049-human-in-loop, T017)
 */

import { render, screen, fireEvent } from '@testing-library/react';
import BlockerPanel from '@/components/BlockerPanel';
import {
  mockSyncBlocker,
  mockAsyncBlocker,
  mockResolvedBlocker,
  mockExpiredBlocker,
  mockLongQuestionBlocker,
  mockShortQuestionBlocker,
  mockBlockerWithoutTask,
  mockEmptyBlockersList,
  mockBlockersUnsorted,
  mockMultipleSyncBlockers,
  mockMultipleAsyncBlockers,
} from '../fixtures/blockers';

// Mock BlockerBadge component
jest.mock('@/components/BlockerBadge', () => ({
  BlockerBadge: ({ type }: { type: string }) => (
    <div data-testid={`blocker-badge-${type}`}>{type} Badge</div>
  ),
}));

describe('BlockerPanel', () => {
  describe('empty state', () => {
    it('renders empty state when blockers array is empty', () => {
      render(<BlockerPanel blockers={mockEmptyBlockersList} />);
      expect(screen.getByText('No blockers - agents are running smoothly!')).toBeInTheDocument();
      expect(screen.getByText('✅')).toBeInTheDocument();
    });

    it('displays (0) count in empty state', () => {
      render(<BlockerPanel blockers={mockEmptyBlockersList} />);
      expect(screen.getByText('(0)')).toBeInTheDocument();
    });

    it('renders empty state when all blockers are non-PENDING', () => {
      render(<BlockerPanel blockers={[mockResolvedBlocker, mockExpiredBlocker]} />);
      expect(screen.getByText('No blockers - agents are running smoothly!')).toBeInTheDocument();
    });
  });

  describe('blocker count display', () => {
    it('displays correct count for single blocker', () => {
      render(<BlockerPanel blockers={[mockSyncBlocker]} />);
      expect(screen.getByText('(1)')).toBeInTheDocument();
    });

    it('displays correct count for multiple blockers', () => {
      render(<BlockerPanel blockers={[mockSyncBlocker, mockAsyncBlocker]} />);
      expect(screen.getByText('(2)')).toBeInTheDocument();
    });

    it('excludes RESOLVED blockers from count', () => {
      render(<BlockerPanel blockers={[mockSyncBlocker, mockResolvedBlocker]} />);
      expect(screen.getByText('(1)')).toBeInTheDocument();
    });

    it('excludes EXPIRED blockers from count', () => {
      render(<BlockerPanel blockers={[mockAsyncBlocker, mockExpiredBlocker]} />);
      expect(screen.getByText('(1)')).toBeInTheDocument();
    });
  });

  describe('status filtering', () => {
    it('shows only PENDING blockers', () => {
      render(
        <BlockerPanel
          blockers={[
            mockSyncBlocker,
            mockAsyncBlocker,
            mockResolvedBlocker,
            mockExpiredBlocker,
          ]}
        />
      );
      expect(screen.getByText(mockSyncBlocker.question)).toBeInTheDocument();
      expect(screen.getByText(mockAsyncBlocker.question)).toBeInTheDocument();
      expect(screen.queryByText(mockResolvedBlocker.question)).not.toBeInTheDocument();
    });

    it('does not render RESOLVED blockers', () => {
      render(<BlockerPanel blockers={[mockResolvedBlocker]} />);
      expect(screen.queryByText(mockResolvedBlocker.question)).not.toBeInTheDocument();
    });

    it('does not render EXPIRED blockers', () => {
      render(<BlockerPanel blockers={[mockExpiredBlocker]} />);
      expect(screen.queryByText(mockExpiredBlocker.question)).not.toBeInTheDocument();
    });
  });

  describe('sorting logic', () => {
    it('sorts SYNC blockers before ASYNC blockers', () => {
      render(<BlockerPanel blockers={mockBlockersUnsorted} />);
      const questions = screen.getAllByRole('button').map(btn => btn.textContent);

      // Find index of SYNC and ASYNC blockers
      const syncIndex = questions.findIndex(q => q?.includes(mockSyncBlocker.question));
      const asyncIndex = questions.findIndex(q => q?.includes(mockAsyncBlocker.question));

      expect(syncIndex).toBeLessThan(asyncIndex);
    });

    it('sorts SYNC blockers by created_at DESC (newest first)', () => {
      const [olderSync, newerSync] = mockMultipleSyncBlockers;
      render(<BlockerPanel blockers={[olderSync, newerSync]} />);

      const buttons = screen.getAllByRole('button');
      // Skip first 3 filter buttons (All, SYNC, ASYNC)
      const blockerButtons = buttons.slice(3);
      // Newer should be first
      expect(blockerButtons[0].textContent).toContain(newerSync.question);
      expect(blockerButtons[1].textContent).toContain(olderSync.question);
    });

    it('sorts ASYNC blockers by created_at DESC (newest first)', () => {
      const [olderAsync, newerAsync] = mockMultipleAsyncBlockers;
      render(<BlockerPanel blockers={[olderAsync, newerAsync]} />);

      const buttons = screen.getAllByRole('button');
      // Skip first 3 filter buttons (All, SYNC, ASYNC)
      const blockerButtons = buttons.slice(3);
      // Newer should be first
      expect(blockerButtons[0].textContent).toContain(newerAsync.question);
      expect(blockerButtons[1].textContent).toContain(olderAsync.question);
    });

    it('maintains SYNC before ASYNC regardless of timestamps', () => {
      // Create ASYNC blocker with newer timestamp than SYNC
      const newerAsync = { ...mockAsyncBlocker, created_at: '2025-11-08T11:00:00Z' };
      const olderSync = { ...mockSyncBlocker, created_at: '2025-11-08T09:00:00Z' };

      render(<BlockerPanel blockers={[newerAsync, olderSync]} />);

      const buttons = screen.getAllByRole('button');
      // Skip first 3 filter buttons (All, SYNC, ASYNC)
      const blockerButtons = buttons.slice(3);
      // SYNC should still be first even though it's older
      expect(blockerButtons[0].textContent).toContain(olderSync.question);
      expect(blockerButtons[1].textContent).toContain(newerAsync.question);
    });
  });

  describe('question truncation', () => {
    it('truncates long questions to 80 characters', () => {
      render(<BlockerPanel blockers={[mockLongQuestionBlocker]} />);
      const displayedText = screen.getByText(/This is a very long question/);
      expect(displayedText.textContent).toHaveLength(83); // 80 chars + '...'
      expect(displayedText.textContent).toContain('...');
    });

    it('does not truncate short questions', () => {
      render(<BlockerPanel blockers={[mockShortQuestionBlocker]} />);
      const displayedText = screen.getByText(mockShortQuestionBlocker.question);
      expect(displayedText.textContent).toBe(mockShortQuestionBlocker.question);
      expect(displayedText.textContent).not.toContain('...');
    });

    it('truncates exactly at 80 character boundary', () => {
      const exactly80 = { ...mockSyncBlocker, question: 'a'.repeat(80) };
      const exactly81 = { ...mockAsyncBlocker, question: 'b'.repeat(81) };

      render(<BlockerPanel blockers={[exactly80, exactly81]} />);

      // 80 chars should NOT be truncated
      const text80 = screen.getByText('a'.repeat(80));
      expect(text80.textContent).toHaveLength(80);
      expect(text80.textContent).not.toContain('...');

      // 81 chars should be truncated
      const text81Container = screen.getByText(/b{80}\.\.\./);
      expect(text81Container.textContent).toHaveLength(83);
    });
  });

  describe('click handler', () => {
    it('calls onBlockerClick when blocker is clicked', () => {
      const mockOnClick = jest.fn();
      render(<BlockerPanel blockers={[mockSyncBlocker]} onBlockerClick={mockOnClick} />);

      const buttons = screen.getAllByRole('button');
      // Skip first 3 filter buttons, click the first blocker button
      fireEvent.click(buttons[3]);

      expect(mockOnClick).toHaveBeenCalledTimes(1);
      expect(mockOnClick).toHaveBeenCalledWith(mockSyncBlocker);
    });

    it('calls onBlockerClick with correct blocker for each item', () => {
      const mockOnClick = jest.fn();
      render(
        <BlockerPanel
          blockers={[mockSyncBlocker, mockAsyncBlocker]}
          onBlockerClick={mockOnClick}
        />
      );

      const buttons = screen.getAllByRole('button');
      // Skip first 3 filter buttons
      const blockerButtons = buttons.slice(3);

      fireEvent.click(blockerButtons[0]);
      expect(mockOnClick).toHaveBeenLastCalledWith(mockSyncBlocker);

      fireEvent.click(blockerButtons[1]);
      expect(mockOnClick).toHaveBeenLastCalledWith(mockAsyncBlocker);

      expect(mockOnClick).toHaveBeenCalledTimes(2);
    });

    it('does not error when onBlockerClick is undefined', () => {
      render(<BlockerPanel blockers={[mockSyncBlocker]} />);

      const buttons = screen.getAllByRole('button');
      // Skip first 3 filter buttons, click the first blocker button
      expect(() => fireEvent.click(buttons[3])).not.toThrow();
    });
  });

  describe('agent and task info display', () => {
    it('displays agent name when available', () => {
      render(<BlockerPanel blockers={[mockSyncBlocker]} />);
      expect(screen.getByText(mockSyncBlocker.agent_name!)).toBeInTheDocument();
    });

    it('falls back to agent_id when agent_name not available', () => {
      const blockerWithoutName = { ...mockSyncBlocker, agent_name: undefined };
      render(<BlockerPanel blockers={[blockerWithoutName]} />);
      expect(screen.getByText(mockSyncBlocker.agent_id)).toBeInTheDocument();
    });

    it('displays task title when available', () => {
      render(<BlockerPanel blockers={[mockSyncBlocker]} />);
      expect(screen.getByText(mockSyncBlocker.task_title!)).toBeInTheDocument();
    });

    it('does not show task separator when task_title is missing', () => {
      render(<BlockerPanel blockers={[mockBlockerWithoutTask]} />);
      const buttons = screen.getAllByRole('button');
      // Skip first 3 filter buttons, get the first blocker button
      const blockerButton = buttons[3];
      // Should not have the '•' separator for task
      expect(blockerButton.textContent).not.toMatch(/🤖.*•.*Implement/);
    });

    it('displays robot emoji for agent', () => {
      render(<BlockerPanel blockers={[mockSyncBlocker]} />);
      expect(screen.getByText('🤖')).toBeInTheDocument();
    });
  });

  describe('time formatting', () => {
    it('formats minutes correctly', () => {
      const blocker = { ...mockSyncBlocker, time_waiting_ms: 300000 }; // 5 minutes
      render(<BlockerPanel blockers={[blocker]} />);
      expect(screen.getByText('5m ago')).toBeInTheDocument();
    });

    it('formats hours correctly', () => {
      const blocker = { ...mockAsyncBlocker, time_waiting_ms: 7200000 }; // 2 hours
      render(<BlockerPanel blockers={[blocker]} />);
      expect(screen.getByText('2h ago')).toBeInTheDocument();
    });

    it('formats days correctly', () => {
      const blocker = { ...mockSyncBlocker, time_waiting_ms: 86400000 }; // 1 day
      render(<BlockerPanel blockers={[blocker]} />);
      expect(screen.getByText('1d ago')).toBeInTheDocument();
    });

    it('shows "Just now" for very recent blockers', () => {
      const blocker = { ...mockSyncBlocker, time_waiting_ms: 30000 }; // 30 seconds
      render(<BlockerPanel blockers={[blocker]} />);
      expect(screen.getByText('Just now')).toBeInTheDocument();
    });

    it('handles zero time_waiting_ms', () => {
      const blocker = { ...mockSyncBlocker, time_waiting_ms: 0 };
      render(<BlockerPanel blockers={[blocker]} />);
      expect(screen.getByText('Just now')).toBeInTheDocument();
    });

    it('handles undefined time_waiting_ms', () => {
      const blocker = { ...mockSyncBlocker, time_waiting_ms: undefined };
      render(<BlockerPanel blockers={[blocker]} />);
      expect(screen.getByText('Just now')).toBeInTheDocument();
    });
  });

  describe('BlockerBadge integration', () => {
    it('renders BlockerBadge for SYNC blocker', () => {
      render(<BlockerPanel blockers={[mockSyncBlocker]} />);
      expect(screen.getByTestId('blocker-badge-SYNC')).toBeInTheDocument();
    });

    it('renders BlockerBadge for ASYNC blocker', () => {
      render(<BlockerPanel blockers={[mockAsyncBlocker]} />);
      expect(screen.getByTestId('blocker-badge-ASYNC')).toBeInTheDocument();
    });

    it('renders correct badge type for each blocker', () => {
      render(<BlockerPanel blockers={[mockSyncBlocker, mockAsyncBlocker]} />);
      expect(screen.getByTestId('blocker-badge-SYNC')).toBeInTheDocument();
      expect(screen.getByTestId('blocker-badge-ASYNC')).toBeInTheDocument();
    });
  });

  describe('UI styling and structure', () => {
    it('applies hover styles to blocker buttons', () => {
      render(<BlockerPanel blockers={[mockSyncBlocker]} />);
      const buttons = screen.getAllByRole('button');
      // Skip first 3 filter buttons, check the first blocker button
      const blockerButton = buttons[3];
      expect(blockerButton).toHaveClass('hover:bg-muted');
    });

    it('renders header with correct styling', () => {
      const { container } = render(<BlockerPanel blockers={[mockSyncBlocker]} />);
      const header = screen.getByText('Blockers');
      expect(header).toHaveClass('text-lg', 'font-semibold');
    });

    it('uses white background for panel', () => {
      const { container } = render(<BlockerPanel blockers={[mockSyncBlocker]} />);
      const panel = container.querySelector('.bg-card');
      expect(panel).toBeInTheDocument();
    });
  });
});
