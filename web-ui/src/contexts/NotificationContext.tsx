'use client';

import { createContext, useContext, type ReactNode } from 'react';
import { useNotifications, type UseNotificationsReturn } from '@/hooks/useNotifications';

const NotificationContext = createContext<UseNotificationsReturn | null>(null);

export function NotificationProvider({ children }: { children: ReactNode }) {
  const value = useNotifications();
  return (
    <NotificationContext.Provider value={value}>{children}</NotificationContext.Provider>
  );
}

export function useNotificationContext(): UseNotificationsReturn {
  const ctx = useContext(NotificationContext);
  if (!ctx) {
    throw new Error('useNotificationContext must be used inside <NotificationProvider>');
  }
  return ctx;
}
