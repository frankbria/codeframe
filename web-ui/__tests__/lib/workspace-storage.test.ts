import {
  getSelectedWorkspacePath,
  setSelectedWorkspacePath,
  clearSelectedWorkspacePath,
  getRecentWorkspaces,
  addToRecentWorkspaces,
  removeFromRecentWorkspaces,
  type RecentWorkspace,
} from '@/lib/workspace-storage';

// Mock localStorage
const localStorageMock = (() => {
  let store: Record<string, string> = {};
  return {
    getItem: jest.fn((key: string) => store[key] || null),
    setItem: jest.fn((key: string, value: string) => {
      store[key] = value;
    }),
    removeItem: jest.fn((key: string) => {
      delete store[key];
    }),
    clear: () => {
      store = {};
    },
  };
})();

Object.defineProperty(window, 'localStorage', { value: localStorageMock });

describe('workspace-storage', () => {
  beforeEach(() => {
    localStorageMock.clear();
    jest.clearAllMocks();
  });

  describe('getSelectedWorkspacePath', () => {
    it('returns null when no workspace is selected', () => {
      expect(getSelectedWorkspacePath()).toBeNull();
    });

    it('returns the stored workspace path', () => {
      localStorageMock.setItem(
        'codeframe_workspace_path',
        '/home/user/my-project'
      );

      expect(getSelectedWorkspacePath()).toBe('/home/user/my-project');
    });
  });

  describe('setSelectedWorkspacePath', () => {
    it('stores the workspace path in localStorage', () => {
      setSelectedWorkspacePath('/home/user/my-project');

      expect(localStorageMock.setItem).toHaveBeenCalledWith(
        'codeframe_workspace_path',
        '/home/user/my-project'
      );
    });

    it('adds the workspace to recent workspaces', () => {
      setSelectedWorkspacePath('/home/user/my-project');

      const recent = getRecentWorkspaces();
      expect(recent.length).toBe(1);
      expect(recent[0].path).toBe('/home/user/my-project');
    });
  });

  describe('clearSelectedWorkspacePath', () => {
    it('removes the workspace path from localStorage', () => {
      setSelectedWorkspacePath('/home/user/my-project');
      clearSelectedWorkspacePath();

      expect(localStorageMock.removeItem).toHaveBeenCalledWith(
        'codeframe_workspace_path'
      );
    });
  });

  describe('getRecentWorkspaces', () => {
    it('returns empty array when no recent workspaces exist', () => {
      expect(getRecentWorkspaces()).toEqual([]);
    });

    it('returns parsed recent workspaces from localStorage', () => {
      const workspaces: RecentWorkspace[] = [
        { path: '/home/user/project-a', name: 'project-a', lastUsed: '2026-02-04T10:00:00Z' },
        { path: '/home/user/project-b', name: 'project-b', lastUsed: '2026-02-04T09:00:00Z' },
      ];
      localStorageMock.setItem(
        'codeframe_recent_workspaces',
        JSON.stringify(workspaces)
      );

      const result = getRecentWorkspaces();
      expect(result).toEqual(workspaces);
    });

    it('returns empty array when localStorage contains invalid JSON', () => {
      localStorageMock.setItem('codeframe_recent_workspaces', 'invalid-json');

      expect(getRecentWorkspaces()).toEqual([]);
    });
  });

  describe('addToRecentWorkspaces', () => {
    it('adds a new workspace to the front of the list', () => {
      addToRecentWorkspaces('/home/user/project-a');
      addToRecentWorkspaces('/home/user/project-b');

      const recent = getRecentWorkspaces();
      expect(recent[0].path).toBe('/home/user/project-b');
      expect(recent[1].path).toBe('/home/user/project-a');
    });

    it('extracts the name from the path', () => {
      addToRecentWorkspaces('/home/user/my-awesome-project');

      const recent = getRecentWorkspaces();
      expect(recent[0].name).toBe('my-awesome-project');
    });

    it('uses full path as name when path has no segments', () => {
      addToRecentWorkspaces('single-segment');

      const recent = getRecentWorkspaces();
      expect(recent[0].name).toBe('single-segment');
    });

    it('moves existing workspace to front when re-added', () => {
      addToRecentWorkspaces('/home/user/project-a');
      addToRecentWorkspaces('/home/user/project-b');
      addToRecentWorkspaces('/home/user/project-a'); // Re-add

      const recent = getRecentWorkspaces();
      expect(recent.length).toBe(2);
      expect(recent[0].path).toBe('/home/user/project-a');
      expect(recent[1].path).toBe('/home/user/project-b');
    });

    it('limits recent workspaces to 10 items', () => {
      for (let i = 0; i < 15; i++) {
        addToRecentWorkspaces(`/home/user/project-${i}`);
      }

      const recent = getRecentWorkspaces();
      expect(recent.length).toBe(10);
      // Most recent should be project-14, oldest should be project-5
      expect(recent[0].path).toBe('/home/user/project-14');
      expect(recent[9].path).toBe('/home/user/project-5');
    });

    it('sets lastUsed to current timestamp', () => {
      const before = new Date().toISOString();
      addToRecentWorkspaces('/home/user/project');
      const after = new Date().toISOString();

      const recent = getRecentWorkspaces();
      expect(recent[0].lastUsed >= before).toBe(true);
      expect(recent[0].lastUsed <= after).toBe(true);
    });
  });

  describe('removeFromRecentWorkspaces', () => {
    it('removes the specified workspace from the list', () => {
      addToRecentWorkspaces('/home/user/project-a');
      addToRecentWorkspaces('/home/user/project-b');
      addToRecentWorkspaces('/home/user/project-c');

      removeFromRecentWorkspaces('/home/user/project-b');

      const recent = getRecentWorkspaces();
      expect(recent.length).toBe(2);
      expect(recent.find(w => w.path === '/home/user/project-b')).toBeUndefined();
    });

    it('does nothing when workspace not in list', () => {
      addToRecentWorkspaces('/home/user/project-a');

      removeFromRecentWorkspaces('/home/user/nonexistent');

      const recent = getRecentWorkspaces();
      expect(recent.length).toBe(1);
    });

    it('preserves order of remaining items', () => {
      addToRecentWorkspaces('/home/user/project-a');
      addToRecentWorkspaces('/home/user/project-b');
      addToRecentWorkspaces('/home/user/project-c');

      removeFromRecentWorkspaces('/home/user/project-b');

      const recent = getRecentWorkspaces();
      expect(recent[0].path).toBe('/home/user/project-c');
      expect(recent[1].path).toBe('/home/user/project-a');
    });
  });
});
