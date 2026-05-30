import { renderHook, waitFor, act } from '@testing-library/react';
import React from 'react';
import { SWRConfig } from 'swr';
import { useWorkspaces } from '@/hooks/useWorkspaces';
import { workspaceApi } from '@/lib/api';
import { getRecentWorkspaces, setRecentWorkspaces } from '@/lib/workspace-storage';
import type { WorkspaceRegistryItem } from '@/types';

jest.mock('@/lib/api', () => ({
  workspaceApi: {
    list: jest.fn(),
    remove: jest.fn(),
  },
}));

const mockedApi = workspaceApi as jest.Mocked<typeof workspaceApi>;

// Fresh SWR cache per render to avoid cross-test bleed.
function wrapper({ children }: { children: React.ReactNode }) {
  return React.createElement(
    SWRConfig,
    { value: { provider: () => new Map(), dedupingInterval: 0 } },
    children
  );
}

const serverItems: WorkspaceRegistryItem[] = [
  {
    id: 'id-a',
    repo_path: '/p/alpha',
    name: 'alpha',
    tech_stack: 'Python',
    created_at: '2026-01-01T00:00:00Z',
    last_opened_at: '2026-05-02T00:00:00Z',
    path_exists: true,
  },
  {
    id: 'id-b',
    repo_path: '/p/beta',
    name: 'beta',
    tech_stack: null,
    created_at: '2026-01-01T00:00:00Z',
    last_opened_at: '2026-05-01T00:00:00Z',
    path_exists: false,
  },
];

beforeEach(() => {
  localStorage.clear();
  jest.clearAllMocks();
});

describe('useWorkspaces', () => {
  it('returns the server list on success', async () => {
    mockedApi.list.mockResolvedValue(serverItems);

    const { result } = renderHook(() => useWorkspaces(), { wrapper });

    await waitFor(() => expect(result.current.workspaces).toHaveLength(2));
    expect(result.current.workspaces[0].repo_path).toBe('/p/alpha');
    expect(result.current.error).toBeUndefined();
  });

  it('mirrors the server list into localStorage recents', async () => {
    mockedApi.list.mockResolvedValue(serverItems);

    const { result } = renderHook(() => useWorkspaces(), { wrapper });
    await waitFor(() => expect(result.current.workspaces).toHaveLength(2));

    const recents = getRecentWorkspaces();
    expect(recents.map((r) => r.path)).toEqual(['/p/alpha', '/p/beta']);
  });

  it('falls back to localStorage recents on fetch error', async () => {
    setRecentWorkspaces([
      { path: '/p/cached', name: 'cached', lastUsed: '2026-04-01T00:00:00Z' },
    ]);
    mockedApi.list.mockRejectedValue(new Error('network down'));

    const { result } = renderHook(() => useWorkspaces(), { wrapper });

    await waitFor(() => expect(result.current.error).toBeTruthy());
    expect(result.current.workspaces).toHaveLength(1);
    expect(result.current.workspaces[0].repo_path).toBe('/p/cached');
    expect(result.current.workspaces[0].path_exists).toBe(true);
  });

  it('removeWorkspace calls the API and refreshes from the server', async () => {
    // Initial fetch returns both; after deletion the server drops alpha.
    mockedApi.list
      .mockResolvedValueOnce(serverItems)
      .mockResolvedValue([serverItems[1]]);
    mockedApi.remove.mockResolvedValue(undefined);

    const { result } = renderHook(() => useWorkspaces(), { wrapper });
    await waitFor(() => expect(result.current.workspaces).toHaveLength(2));

    await act(async () => {
      await result.current.removeWorkspace('id-a');
    });

    expect(mockedApi.remove).toHaveBeenCalledWith('id-a');
    // Post-refresh, the server list no longer contains the removed workspace.
    await waitFor(() => expect(result.current.workspaces).toHaveLength(1));
    expect(result.current.workspaces[0].id).toBe('id-b');
    expect(getRecentWorkspaces().some((r) => r.path === '/p/alpha')).toBe(false);
  });
});
