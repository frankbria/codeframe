'use client';

import { useCallback, useEffect, useState } from 'react';
import { getSelectedWorkspacePath } from '@/lib/workspace-storage';
import type { AppNotification, AppNotificationBatchStatus, AppNotificationType } from '@/types';

export const NOTIFICATIONS_STORAGE_KEY_PREFIX = 'codeframe_notifications';
export const NOTIFICATIONS_GLOBAL_STORAGE_KEY = NOTIFICATIONS_STORAGE_KEY_PREFIX;
export const MAX_NOTIFICATIONS = 20;

// Back-compat alias for tests written against the original key name.
export const NOTIFICATIONS_STORAGE_KEY = NOTIFICATIONS_GLOBAL_STORAGE_KEY;

const TITLES: Record<AppNotificationType, string> = {
  'batch.completed': 'Batch finished',
  'blocker.created': 'Blocker needs input',
  'gate.run.failed': 'Gate run failed',
};

function storageKeyFor(workspacePath: string | null): string {
  if (!workspacePath) return NOTIFICATIONS_GLOBAL_STORAGE_KEY;
  return `${NOTIFICATIONS_STORAGE_KEY_PREFIX}_${encodeURIComponent(workspacePath)}`;
}

export interface AddNotificationInput {
  type: AppNotificationType;
  message: string;
  batchId?: string;
  batchStatus?: AppNotificationBatchStatus;
  taskId?: string;
  gateName?: string;
}

export interface UseNotificationsReturn {
  notifications: AppNotification[];
  unreadCount: number;
  addNotification: (input: AddNotificationInput) => void;
  markRead: (id: string) => void;
  markAllRead: () => void;
  clearAll: () => void;
}

function readStored(key: string): AppNotification[] {
  if (typeof window === 'undefined') return [];
  const raw = localStorage.getItem(key);
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw) as AppNotification[];
    return Array.isArray(parsed) ? parsed.slice(0, MAX_NOTIFICATIONS) : [];
  } catch {
    return [];
  }
}

function persist(key: string, notifications: AppNotification[]): void {
  if (typeof window === 'undefined') return;
  localStorage.setItem(key, JSON.stringify(notifications));
}

function generateId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

function maybeFireBrowserNotification(n: AppNotification): void {
  if (typeof window === 'undefined') return;
  if (typeof Notification === 'undefined') return;
  if (document.visibilityState === 'visible') return;
  if (Notification.permission !== 'granted') return;
  try {
    new Notification(TITLES[n.type], {
      body: n.message,
      icon: '/favicon.ico',
      tag: n.id,
    });
  } catch {
    // Some browsers throw if Notification is invoked from an insecure context;
    // ignore — the in-app history still records the event.
  }
}

export function useNotifications(): UseNotificationsReturn {
  const [workspacePath, setWorkspacePath] = useState<string | null>(null);
  const [notifications, setNotifications] = useState<AppNotification[]>([]);

  // Hydrate from localStorage when the workspace changes
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const path = getSelectedWorkspacePath();
    setWorkspacePath(path);
    setNotifications(readStored(storageKeyFor(path)));

    const handleWorkspaceChange = () => {
      const next = getSelectedWorkspacePath();
      setWorkspacePath(next);
      setNotifications(readStored(storageKeyFor(next)));
    };
    window.addEventListener('storage', handleWorkspaceChange);
    window.addEventListener('workspaceChanged', handleWorkspaceChange);
    return () => {
      window.removeEventListener('storage', handleWorkspaceChange);
      window.removeEventListener('workspaceChanged', handleWorkspaceChange);
    };
  }, []);

  const addNotification = useCallback(
    (input: AddNotificationInput) => {
      setNotifications((prev) => {
        const entry: AppNotification = {
          id: generateId(),
          type: input.type,
          message: input.message,
          timestamp: new Date().toISOString(),
          read: false,
          batchId: input.batchId,
          batchStatus: input.batchStatus,
          taskId: input.taskId,
          gateName: input.gateName,
          workspacePath: workspacePath ?? undefined,
        };
        const next = [entry, ...prev].slice(0, MAX_NOTIFICATIONS);
        persist(storageKeyFor(workspacePath), next);
        maybeFireBrowserNotification(entry);
        return next;
      });
    },
    [workspacePath]
  );

  const markRead = useCallback(
    (id: string) => {
      setNotifications((prev) => {
        const next = prev.map((n) => (n.id === id ? { ...n, read: true } : n));
        persist(storageKeyFor(workspacePath), next);
        return next;
      });
    },
    [workspacePath]
  );

  const markAllRead = useCallback(() => {
    setNotifications((prev) => {
      const next = prev.map((n) => ({ ...n, read: true }));
      persist(storageKeyFor(workspacePath), next);
      return next;
    });
  }, [workspacePath]);

  const clearAll = useCallback(() => {
    setNotifications(() => {
      persist(storageKeyFor(workspacePath), []);
      return [];
    });
  }, [workspacePath]);

  const unreadCount = notifications.reduce((acc, n) => acc + (n.read ? 0 : 1), 0);

  return { notifications, unreadCount, addNotification, markRead, markAllRead, clearAll };
}
