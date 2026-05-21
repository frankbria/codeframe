import { renderHook, act } from '@testing-library/react';
import { useNotifications, NOTIFICATIONS_STORAGE_KEY, MAX_NOTIFICATIONS } from '@/hooks/useNotifications';

// Helper to mock Notification API + visibility
type PermissionState = NotificationPermission;

let currentPermission: PermissionState = 'default';

function setNotificationPermission(value: PermissionState) {
  currentPermission = value;
}

function setVisibility(value: DocumentVisibilityState) {
  Object.defineProperty(document, 'visibilityState', {
    configurable: true,
    get: () => value,
  });
}

const NotificationCtor = jest.fn();

// Stub the Notification global with a function plus a `permission` getter.
function installNotificationStub() {
  const stub = function (this: unknown, title: string, options?: NotificationOptions) {
    NotificationCtor(title, options);
  } as unknown as typeof Notification;
  Object.defineProperty(stub, 'permission', {
    configurable: true,
    get: () => currentPermission,
  });
  Object.defineProperty(stub, 'requestPermission', {
    configurable: true,
    value: jest.fn().mockResolvedValue('granted'),
  });
  (global as unknown as { Notification: typeof Notification }).Notification = stub;
}

beforeEach(() => {
  localStorage.clear();
  NotificationCtor.mockClear();
  currentPermission = 'default';
  installNotificationStub();
  setVisibility('visible');
});

describe('useNotifications', () => {
  it('starts empty when no localStorage entry exists', () => {
    const { result } = renderHook(() => useNotifications());
    expect(result.current.notifications).toEqual([]);
    expect(result.current.unreadCount).toBe(0);
  });

  it('hydrates from localStorage on mount', () => {
    const stored = [
      {
        id: '1',
        type: 'batch.completed',
        message: 'Batch finished',
        timestamp: new Date().toISOString(),
        read: false,
      },
    ];
    localStorage.setItem(NOTIFICATIONS_STORAGE_KEY, JSON.stringify(stored));
    const { result } = renderHook(() => useNotifications());
    expect(result.current.notifications).toHaveLength(1);
    expect(result.current.notifications[0].id).toBe('1');
    expect(result.current.unreadCount).toBe(1);
  });

  it('prepends a new notification (newest first) and persists', () => {
    const { result } = renderHook(() => useNotifications());

    act(() => {
      result.current.addNotification({
        type: 'batch.completed',
        message: 'Batch 1 done',
      });
    });

    expect(result.current.notifications).toHaveLength(1);
    expect(result.current.notifications[0].message).toBe('Batch 1 done');
    expect(result.current.notifications[0].read).toBe(false);

    act(() => {
      result.current.addNotification({
        type: 'blocker.created',
        message: 'Blocked',
      });
    });

    expect(result.current.notifications).toHaveLength(2);
    expect(result.current.notifications[0].message).toBe('Blocked');
    expect(result.current.notifications[1].message).toBe('Batch 1 done');

    const persisted = JSON.parse(localStorage.getItem(NOTIFICATIONS_STORAGE_KEY)!);
    expect(persisted).toHaveLength(2);
  });

  it(`caps history at ${MAX_NOTIFICATIONS} entries`, () => {
    const { result } = renderHook(() => useNotifications());
    act(() => {
      for (let i = 0; i < MAX_NOTIFICATIONS + 5; i++) {
        result.current.addNotification({
          type: 'batch.completed',
          message: `msg ${i}`,
        });
      }
    });
    expect(result.current.notifications).toHaveLength(MAX_NOTIFICATIONS);
    // Newest first → first element should be the last we added
    expect(result.current.notifications[0].message).toBe(`msg ${MAX_NOTIFICATIONS + 4}`);
  });

  it('marks a single notification as read', () => {
    const { result } = renderHook(() => useNotifications());
    act(() => {
      result.current.addNotification({ type: 'batch.completed', message: 'a' });
      result.current.addNotification({ type: 'batch.completed', message: 'b' });
    });
    expect(result.current.unreadCount).toBe(2);

    const firstId = result.current.notifications[0].id;
    act(() => {
      result.current.markRead(firstId);
    });
    expect(result.current.unreadCount).toBe(1);
    expect(result.current.notifications.find((n) => n.id === firstId)?.read).toBe(true);
  });

  it('marks all notifications as read', () => {
    const { result } = renderHook(() => useNotifications());
    act(() => {
      result.current.addNotification({ type: 'batch.completed', message: 'a' });
      result.current.addNotification({ type: 'blocker.created', message: 'b' });
    });
    act(() => {
      result.current.markAllRead();
    });
    expect(result.current.unreadCount).toBe(0);
  });

  it('clears all notifications and persists empty state', () => {
    const { result } = renderHook(() => useNotifications());
    act(() => {
      result.current.addNotification({ type: 'batch.completed', message: 'a' });
    });
    expect(result.current.notifications).toHaveLength(1);

    act(() => {
      result.current.clearAll();
    });
    expect(result.current.notifications).toHaveLength(0);
    const persisted = JSON.parse(localStorage.getItem(NOTIFICATIONS_STORAGE_KEY)!);
    expect(persisted).toEqual([]);
  });

  it('fires a browser Notification when tab is hidden and permission is granted', () => {
    setVisibility('hidden');
    setNotificationPermission('granted');

    const { result } = renderHook(() => useNotifications());
    act(() => {
      result.current.addNotification({
        type: 'batch.completed',
        message: 'Batch 7 done',
      });
    });

    expect(NotificationCtor).toHaveBeenCalledTimes(1);
    const [title, options] = NotificationCtor.mock.calls[0];
    expect(typeof title).toBe('string');
    expect(options.body).toBe('Batch 7 done');
  });

  it('does NOT fire a browser Notification when tab is visible', () => {
    setVisibility('visible');
    setNotificationPermission('granted');

    const { result } = renderHook(() => useNotifications());
    act(() => {
      result.current.addNotification({
        type: 'batch.completed',
        message: 'Batch 8 done',
      });
    });
    expect(NotificationCtor).not.toHaveBeenCalled();
  });

  it('does NOT fire a browser Notification when permission is denied', () => {
    setVisibility('hidden');
    setNotificationPermission('denied');

    const { result } = renderHook(() => useNotifications());
    act(() => {
      result.current.addNotification({
        type: 'batch.completed',
        message: 'Batch 9 done',
      });
    });
    expect(NotificationCtor).not.toHaveBeenCalled();
  });
});
