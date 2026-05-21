'use client';

import { useCallback, useEffect, useState } from 'react';
import type { AppNotification, AppNotificationType } from '@/types';

export const NOTIFICATIONS_STORAGE_KEY = 'codeframe_notifications';
export const MAX_NOTIFICATIONS = 20;

const TITLES: Record<AppNotificationType, string> = {
  'batch.completed': 'Batch complete',
  'blocker.created': 'Blocker needs input',
  'gate.run.failed': 'Gate run failed',
};

export interface AddNotificationInput {
  type: AppNotificationType;
  message: string;
  batchId?: string;
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

function readStored(): AppNotification[] {
  if (typeof window === 'undefined') return [];
  const raw = localStorage.getItem(NOTIFICATIONS_STORAGE_KEY);
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw) as AppNotification[];
    return Array.isArray(parsed) ? parsed.slice(0, MAX_NOTIFICATIONS) : [];
  } catch {
    return [];
  }
}

function persist(notifications: AppNotification[]): void {
  if (typeof window === 'undefined') return;
  localStorage.setItem(NOTIFICATIONS_STORAGE_KEY, JSON.stringify(notifications));
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
  const [notifications, setNotifications] = useState<AppNotification[]>([]);

  // Hydrate on mount (avoid SSR mismatch by reading inside useEffect)
  useEffect(() => {
    setNotifications(readStored());
  }, []);

  const addNotification = useCallback((input: AddNotificationInput) => {
    setNotifications((prev) => {
      const entry: AppNotification = {
        id: generateId(),
        type: input.type,
        message: input.message,
        timestamp: new Date().toISOString(),
        read: false,
        batchId: input.batchId,
        taskId: input.taskId,
        gateName: input.gateName,
      };
      const next = [entry, ...prev].slice(0, MAX_NOTIFICATIONS);
      persist(next);
      maybeFireBrowserNotification(entry);
      return next;
    });
  }, []);

  const markRead = useCallback((id: string) => {
    setNotifications((prev) => {
      const next = prev.map((n) => (n.id === id ? { ...n, read: true } : n));
      persist(next);
      return next;
    });
  }, []);

  const markAllRead = useCallback(() => {
    setNotifications((prev) => {
      const next = prev.map((n) => ({ ...n, read: true }));
      persist(next);
      return next;
    });
  }, []);

  const clearAll = useCallback(() => {
    setNotifications(() => {
      persist([]);
      return [];
    });
  }, []);

  const unreadCount = notifications.reduce((acc, n) => acc + (n.read ? 0 : 1), 0);

  return { notifications, unreadCount, addNotification, markRead, markAllRead, clearAll };
}
