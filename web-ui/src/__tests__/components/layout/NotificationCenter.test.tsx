import { render, screen, fireEvent, within } from '@testing-library/react';
import { NotificationCenter } from '@/components/layout/NotificationCenter';
import { NotificationProvider } from '@/contexts/NotificationContext';
import { useNotificationContext } from '@/contexts/NotificationContext';
import { NOTIFICATIONS_STORAGE_KEY } from '@/hooks/useNotifications';

// Test harness — lets us add notifications from outside the component tree.
function Harness({ children }: { children: React.ReactNode }) {
  return <NotificationProvider>{children}</NotificationProvider>;
}

function Adder({ buttonId, payload }: { buttonId: string; payload: { type: 'batch.completed' | 'blocker.created' | 'gate.run.failed'; message: string } }) {
  const { addNotification } = useNotificationContext();
  return (
    <button data-testid={buttonId} onClick={() => addNotification(payload)}>
      add
    </button>
  );
}

beforeEach(() => {
  localStorage.clear();
});

describe('NotificationCenter', () => {
  it('renders a bell button with no badge when there are no unread notifications', () => {
    render(
      <Harness>
        <NotificationCenter />
      </Harness>
    );
    const bell = screen.getByRole('button', { name: /notifications/i });
    expect(bell).toBeInTheDocument();
    expect(screen.queryByTestId('notification-badge')).not.toBeInTheDocument();
  });

  it('shows an unread badge when there are unread notifications', () => {
    render(
      <Harness>
        <Adder buttonId="add-1" payload={{ type: 'batch.completed', message: 'Batch 1 done' }} />
        <NotificationCenter />
      </Harness>
    );
    fireEvent.click(screen.getByTestId('add-1'));
    expect(screen.getByTestId('notification-badge')).toHaveTextContent('1');
  });

  it('opens the dropdown and lists notifications when the bell is clicked', () => {
    render(
      <Harness>
        <Adder buttonId="add-1" payload={{ type: 'batch.completed', message: 'Batch 1 done' }} />
        <Adder buttonId="add-2" payload={{ type: 'blocker.created', message: 'Blocked: task 7' }} />
        <NotificationCenter />
      </Harness>
    );

    fireEvent.click(screen.getByTestId('add-1'));
    fireEvent.click(screen.getByTestId('add-2'));

    expect(screen.queryByText(/Batch 1 done/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /notifications/i }));

    expect(screen.getByText(/Batch 1 done/)).toBeInTheDocument();
    expect(screen.getByText(/Blocked: task 7/)).toBeInTheDocument();
  });

  it('shows empty state when there are no notifications', () => {
    render(
      <Harness>
        <NotificationCenter />
      </Harness>
    );
    fireEvent.click(screen.getByRole('button', { name: /notifications/i }));
    expect(screen.getByText(/no notifications/i)).toBeInTheDocument();
  });

  it('marks a single notification read via its X button', () => {
    render(
      <Harness>
        <Adder buttonId="add-1" payload={{ type: 'batch.completed', message: 'msg-x' }} />
        <NotificationCenter />
      </Harness>
    );
    fireEvent.click(screen.getByTestId('add-1'));
    expect(screen.getByTestId('notification-badge')).toHaveTextContent('1');

    fireEvent.click(screen.getByRole('button', { name: /notifications/i }));
    const item = screen.getByText(/msg-x/).closest('[data-testid="notification-item"]');
    expect(item).toBeTruthy();
    const markBtn = within(item as HTMLElement).getByRole('button', { name: /mark as read/i });
    fireEvent.click(markBtn);

    expect(screen.queryByTestId('notification-badge')).not.toBeInTheDocument();
  });

  it('marks all notifications read', () => {
    render(
      <Harness>
        <Adder buttonId="add-1" payload={{ type: 'batch.completed', message: 'a' }} />
        <Adder buttonId="add-2" payload={{ type: 'blocker.created', message: 'b' }} />
        <NotificationCenter />
      </Harness>
    );
    fireEvent.click(screen.getByTestId('add-1'));
    fireEvent.click(screen.getByTestId('add-2'));
    expect(screen.getByTestId('notification-badge')).toHaveTextContent('2');

    fireEvent.click(screen.getByRole('button', { name: /notifications/i }));
    fireEvent.click(screen.getByRole('button', { name: /mark all read/i }));

    expect(screen.queryByTestId('notification-badge')).not.toBeInTheDocument();
  });

  it('clears all notifications', () => {
    render(
      <Harness>
        <Adder buttonId="add-1" payload={{ type: 'batch.completed', message: 'a' }} />
        <NotificationCenter />
      </Harness>
    );
    fireEvent.click(screen.getByTestId('add-1'));
    fireEvent.click(screen.getByRole('button', { name: /notifications/i }));
    fireEvent.click(screen.getByRole('button', { name: /clear all/i }));

    expect(screen.queryByText(/^a$/)).not.toBeInTheDocument();
    expect(screen.getByText(/no notifications/i)).toBeInTheDocument();
  });

  it('does not render a green checkmark for a FAILED batch notification', () => {
    // Regression for codex review finding: FAILED/CANCELLED must not look like success.
    const stored = [
      {
        id: '1',
        type: 'batch.completed',
        batchStatus: 'FAILED',
        message: 'Batch X failed — 2/5 tasks completed before failure',
        timestamp: new Date().toISOString(),
        read: false,
      },
    ];
    localStorage.setItem(NOTIFICATIONS_STORAGE_KEY, JSON.stringify(stored));

    render(
      <Harness>
        <NotificationCenter />
      </Harness>
    );
    fireEvent.click(screen.getByRole('button', { name: /notifications/i }));
    const item = screen.getByText(/Batch X failed/).closest('[data-testid="notification-item"]');
    expect(item).toBeTruthy();
    // The success icon must not be present in a failed-batch row
    expect(within(item as HTMLElement).queryByTestId('icon-CheckmarkCircle01Icon')).toBeNull();
  });

  it('renders notifications from existing localStorage state on mount', () => {
    const stored = [
      {
        id: '1',
        type: 'gate.run.failed',
        message: 'gate failed: unit',
        timestamp: new Date().toISOString(),
        read: false,
      },
    ];
    localStorage.setItem(NOTIFICATIONS_STORAGE_KEY, JSON.stringify(stored));

    render(
      <Harness>
        <NotificationCenter />
      </Harness>
    );
    expect(screen.getByTestId('notification-badge')).toHaveTextContent('1');
    fireEvent.click(screen.getByRole('button', { name: /notifications/i }));
    expect(screen.getByText(/gate failed: unit/)).toBeInTheDocument();
  });
});
