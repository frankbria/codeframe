import { render, screen } from '@testing-library/react';
import { FileChangeEvent } from '@/components/execution/FileChangeEvent';
import type { ProgressEvent } from '@/hooks/useTaskStream';

function makeEvent(message: string): ProgressEvent {
  return {
    event_type: 'progress',
    task_id: 'task-1',
    timestamp: '2026-02-06T10:00:00Z',
    phase: 'execution',
    step: 2,
    total_steps: 5,
    message,
  };
}

describe('FileChangeEvent', () => {
  it('renders the extracted file path, not the raw message', () => {
    render(<FileChangeEvent event={makeEvent('Creating file: src/main.py')} />);
    expect(screen.getByText('src/main.py')).toBeInTheDocument();
    expect(screen.queryByText('Creating file: src/main.py')).not.toBeInTheDocument();
  });

  it('falls back to the raw message when the pattern does not match', () => {
    render(<FileChangeEvent event={makeEvent('some other message')} />);
    expect(screen.getByText('some other message')).toBeInTheDocument();
  });

  // Regression guard for #775: the "View Diff" toggle only expanded to a
  // placeholder (the event message), never a real diff, so it was removed.
  it('does not render a View Diff affordance', () => {
    render(<FileChangeEvent event={makeEvent('Editing file: src/app.py')} />);
    expect(screen.queryByText(/view diff/i)).not.toBeInTheDocument();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });
});
