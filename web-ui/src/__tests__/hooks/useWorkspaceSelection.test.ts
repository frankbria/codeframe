import { renderHook, act, waitFor } from '@testing-library/react';
import { useWorkspaceSelection } from '@/hooks/useWorkspaceSelection';
import { workspaceApi } from '@/lib/api';
import {
  getSelectedWorkspacePath,
  setSelectedWorkspacePath,
  clearSelectedWorkspacePath,
} from '@/lib/workspace-storage';
import { mutate as globalMutate } from 'swr';
import type { WorkspaceResponse } from '@/types';

jest.mock('swr', () => ({ mutate: jest.fn() }));
jest.mock('@/hooks/useWorkspaces', () => ({ WORKSPACES_SWR_KEY: 'workspaces' }));
jest.mock('@/lib/workspace-storage', () => ({
  getSelectedWorkspacePath: jest.fn(),
  setSelectedWorkspacePath: jest.fn(),
  clearSelectedWorkspacePath: jest.fn(),
}));
jest.mock('@/lib/api', () => ({
  workspaceApi: {
    checkExists: jest.fn(),
    getByPath: jest.fn(),
    init: jest.fn(),
  },
}));

const mockedApi = workspaceApi as jest.Mocked<typeof workspaceApi>;
const mockedGet = getSelectedWorkspacePath as jest.Mock;

function makeWorkspace(overrides: Partial<WorkspaceResponse> = {}): WorkspaceResponse {
  return {
    id: 'ws-1',
    repo_path: '/p/new',
    name: 'new',
    tech_stack: 'Python',
    ...overrides,
  } as WorkspaceResponse;
}

beforeEach(() => {
  jest.clearAllMocks();
  mockedGet.mockReturnValue(null);
  mockedApi.getByPath.mockResolvedValue(makeWorkspace());
});

describe('useWorkspaceSelection', () => {
  it('hydrates the path from localStorage on mount and flags ready', async () => {
    mockedGet.mockReturnValue('/p/stored');
    const { result } = renderHook(() => useWorkspaceSelection());

    await waitFor(() => expect(result.current.workspaceReady).toBe(true));
    expect(result.current.workspacePath).toBe('/p/stored');
  });

  it('selects an existing workspace without calling init or onInitialized', async () => {
    mockedApi.checkExists.mockResolvedValue({ exists: true } as never);
    const onInitialized = jest.fn();
    const { result } = renderHook(() => useWorkspaceSelection());

    await act(async () => {
      await result.current.selectWorkspace('/p/exists', { onInitialized });
    });

    expect(mockedApi.init).not.toHaveBeenCalled();
    expect(onInitialized).not.toHaveBeenCalled();
    expect(setSelectedWorkspacePath).toHaveBeenCalledWith('/p/exists');
    expect(globalMutate).toHaveBeenCalledWith('workspaces');
    expect(result.current.workspacePath).toBe('/p/exists');
    expect(result.current.isSelecting).toBe(false);
  });

  it('initializes a new workspace and fires onInitialized with the result', async () => {
    mockedApi.checkExists.mockResolvedValue({ exists: false } as never);
    const initialized = makeWorkspace({ tech_stack: 'TypeScript' });
    mockedApi.init.mockResolvedValue(initialized);
    const onInitialized = jest.fn();
    const { result } = renderHook(() => useWorkspaceSelection());

    await act(async () => {
      await result.current.selectWorkspace('/p/new', { onInitialized });
    });

    expect(mockedApi.init).toHaveBeenCalledWith('/p/new', { detect: true });
    expect(onInitialized).toHaveBeenCalledWith(initialized);
    expect(result.current.workspacePath).toBe('/p/new');
  });

  it('captures a selection error and stops selecting on API failure', async () => {
    mockedApi.checkExists.mockRejectedValue({ detail: 'boom' });
    const { result } = renderHook(() => useWorkspaceSelection());

    await act(async () => {
      await result.current.selectWorkspace('/p/bad');
    });

    expect(result.current.selectionError).toBe('boom');
    expect(result.current.isSelecting).toBe(false);
    expect(result.current.workspacePath).toBeNull();
  });

  it('clearWorkspace resets the path, persists the clear, and drops a stale error', async () => {
    mockedApi.checkExists.mockRejectedValue({ detail: 'boom' });
    const { result } = renderHook(() => useWorkspaceSelection());

    await act(async () => {
      await result.current.selectWorkspace('/p/bad');
    });
    expect(result.current.selectionError).toBe('boom');

    act(() => {
      result.current.clearWorkspace();
    });

    expect(clearSelectedWorkspacePath).toHaveBeenCalled();
    expect(result.current.workspacePath).toBeNull();
    expect(result.current.selectionError).toBeNull();
  });
});
