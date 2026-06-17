'use client';

import { createContext, useContext, type ReactNode } from 'react';
import { useNotifications, type UseNotificationsReturn } from '@/hooks/useNotifications';
import { useBatchNotificationWatcher } from '@/hooks/useBatchNotificationWatcher';

const NotificationContext = createContext<UseNotificationsReturn | null>(null);

/**
 * Cross-page background watcher. Mounted once here (inside the provider, so it
 * runs on every route) it is the single dispatcher of batch.completed and
 * blocker.created — making those notifications fire even when the execution
 * page is unmounted. See issue #652.
 */
function BackgroundBatchWatcher({ addNotification }: { addNotification: UseNotificationsReturn['addNotification'] }) {
  useBatchNotificationWatcher(addNotification);
  return null;
}

export function NotificationProvider({ children }: { children: ReactNode }) {
  const value = useNotifications();
  return (
    <NotificationContext.Provider value={value}>
      <BackgroundBatchWatcher addNotification={value.addNotification} />
      {children}
    </NotificationContext.Provider>
  );
}

export function useNotificationContext(): UseNotificationsReturn {
  const ctx = useContext(NotificationContext);
  if (!ctx) {
    throw new Error('useNotificationContext must be used inside <NotificationProvider>');
  }
  return ctx;
}
