'use client';

import { useEffect, useRef, useState } from 'react';
import {
  Notification02Icon,
  Cancel01Icon,
  Alert02Icon,
  CheckmarkCircle01Icon,
} from '@hugeicons/react';
import { formatDistanceToNow } from 'date-fns';
import { useNotificationContext } from '@/contexts/NotificationContext';
import type { AppNotification, AppNotificationType } from '@/types';

const TYPE_ICONS: Record<AppNotificationType, typeof Alert02Icon> = {
  'batch.completed': CheckmarkCircle01Icon,
  'blocker.created': Alert02Icon,
  'gate.run.failed': Alert02Icon,
};

const TYPE_COLOR: Record<AppNotificationType, string> = {
  'batch.completed': 'text-green-600',
  'blocker.created': 'text-amber-600',
  'gate.run.failed': 'text-red-600',
};

function formatTimestamp(iso: string): string {
  try {
    return formatDistanceToNow(new Date(iso), { addSuffix: true });
  } catch {
    return '';
  }
}

export function NotificationCenter() {
  const { notifications, unreadCount, markRead, markAllRead, clearAll } = useNotificationContext();
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onMouseDown(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener('mousedown', onMouseDown);
    return () => document.removeEventListener('mousedown', onMouseDown);
  }, [open]);

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        aria-label="Notifications"
        onClick={() => setOpen((prev) => !prev)}
        className="relative flex w-full items-center gap-3 rounded-md px-2 py-2 text-sm text-muted-foreground transition-colors hover:bg-accent/50 hover:text-foreground lg:px-3"
      >
        <Notification02Icon className="h-5 w-5 shrink-0" aria-hidden="true" />
        <span className="hidden lg:inline" aria-hidden="true">Notifications</span>
        {unreadCount > 0 && (
          <span
            data-testid="notification-badge"
            className="ml-auto flex h-5 min-w-5 items-center justify-center rounded-full bg-red-500 px-1.5 text-[10px] font-bold text-white"
          >
            {unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute bottom-0 left-full z-50 ml-2 w-80 rounded-md border bg-popover shadow-lg">
          <div className="flex items-center justify-between border-b px-3 py-2">
            <span className="text-sm font-semibold">Notifications</span>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={markAllRead}
                disabled={notifications.length === 0 || unreadCount === 0}
                className="text-xs text-muted-foreground hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50"
              >
                Mark all read
              </button>
              <button
                type="button"
                onClick={clearAll}
                disabled={notifications.length === 0}
                className="text-xs text-muted-foreground hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50"
              >
                Clear all
              </button>
            </div>
          </div>

          <div className="max-h-96 overflow-y-auto">
            {notifications.length === 0 ? (
              <p className="p-6 text-center text-sm text-muted-foreground">No notifications yet</p>
            ) : (
              <ul className="divide-y">
                {notifications.map((n) => (
                  <NotificationRow key={n.id} notification={n} onMarkRead={markRead} />
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function NotificationRow({
  notification,
  onMarkRead,
}: {
  notification: AppNotification;
  onMarkRead: (id: string) => void;
}) {
  const Icon = TYPE_ICONS[notification.type];
  const colorClass = TYPE_COLOR[notification.type];
  return (
    <li
      data-testid="notification-item"
      className={`flex items-start gap-2 px-3 py-2 text-sm ${notification.read ? 'opacity-60' : ''}`}
    >
      <Icon className={`mt-0.5 h-4 w-4 shrink-0 ${colorClass}`} aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <p className="break-words">{notification.message}</p>
        <p className="mt-0.5 text-xs text-muted-foreground">{formatTimestamp(notification.timestamp)}</p>
      </div>
      {!notification.read && (
        <button
          type="button"
          aria-label="Mark as read"
          onClick={() => onMarkRead(notification.id)}
          className="text-muted-foreground hover:text-foreground"
        >
          <Cancel01Icon className="h-3.5 w-3.5" aria-hidden="true" />
        </button>
      )}
    </li>
  );
}
