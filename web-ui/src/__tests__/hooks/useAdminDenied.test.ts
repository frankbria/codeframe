/**
 * useAdminDenied (#1255): the UI gates admin-only actions only when the server
 * has said the session is NOT admin. Loading and failure leave actions enabled
 * — the server's 403 stays the backstop, and a flaky probe must not lock the
 * local operator out of their own instance.
 */
import { renderHook, waitFor } from '@testing-library/react';
import React from 'react';
import { SWRConfig } from 'swr';
import { useAdminDenied } from '@/hooks/useAdminDenied';
import { authApi } from '@/lib/api';

jest.mock('@/lib/api', () => ({
  authApi: { getMe: jest.fn() },
}));

const mockGetMe = authApi.getMe as jest.MockedFunction<typeof authApi.getMe>;

function wrapper({ children }: { children: React.ReactNode }) {
  return React.createElement(
    SWRConfig,
    { value: { provider: () => new Map(), dedupingInterval: 0 } },
    children
  );
}

beforeEach(() => jest.clearAllMocks());

it('is denied when the server reports a non-admin principal', async () => {
  mockGetMe.mockResolvedValue({ scopes: ['read', 'write'], is_admin: false });
  const { result } = renderHook(() => useAdminDenied(), { wrapper });
  await waitFor(() => expect(result.current).toBe(true));
});

it('is not denied for an admin (including the auth-off local operator)', async () => {
  mockGetMe.mockResolvedValue({ scopes: ['read', 'write', 'admin'], is_admin: true });
  const { result } = renderHook(() => useAdminDenied(), { wrapper });
  await waitFor(() => expect(mockGetMe).toHaveBeenCalled());
  expect(result.current).toBe(false);
});

it('is not denied while loading or when the probe fails', async () => {
  mockGetMe.mockRejectedValue(new Error('network'));
  const { result } = renderHook(() => useAdminDenied(), { wrapper });
  expect(result.current).toBe(false);
  await waitFor(() => expect(mockGetMe).toHaveBeenCalled());
  expect(result.current).toBe(false);
});
