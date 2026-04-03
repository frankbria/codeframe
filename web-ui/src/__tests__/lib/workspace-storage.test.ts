/**
 * Tests for workspace-storage localStorage utilities
 */

import {
  getRecentWorkspaces,
  addToRecentWorkspaces,
  removeFromRecentWorkspaces,
  getSelectedWorkspacePath,
  setSelectedWorkspacePath,
  clearSelectedWorkspacePath,
} from '@/lib/workspace-storage';

// Simple localStorage mock
const localStorageMock = (() => {
  let store: Record<string, string> = {};
  return {
    getItem: (key: string) => store[key] ?? null,
    setItem: (key: string, value: string) => { store[key] = value; },
    removeItem: (key: string) => { delete store[key]; },
    clear: () => { store = {}; },
  };
})();

Object.defineProperty(window, 'localStorage', { value: localStorageMock });
// Suppress CustomEvent dispatch errors in jsdom
Object.defineProperty(window, 'dispatchEvent', { value: jest.fn() });

beforeEach(() => {
  localStorageMock.clear();
});

describe('getRecentWorkspaces', () => {
  it('returns empty array when nothing stored', () => {
    expect(getRecentWorkspaces()).toEqual([]);
  });

  it('returns stored workspaces', () => {
    addToRecentWorkspaces('/home/user/project-a');
    const result = getRecentWorkspaces();
    expect(result).toHaveLength(1);
    expect(result[0].path).toBe('/home/user/project-a');
    expect(result[0].name).toBe('project-a');
  });

  it('returns [] on corrupt JSON', () => {
    localStorageMock.setItem('codeframe_recent_workspaces', 'not-json');
    expect(getRecentWorkspaces()).toEqual([]);
  });
});

describe('addToRecentWorkspaces', () => {
  it('adds a new workspace with correct name derived from path', () => {
    addToRecentWorkspaces('/home/user/my-project');
    const recent = getRecentWorkspaces();
    expect(recent[0].name).toBe('my-project');
    expect(recent[0].path).toBe('/home/user/my-project');
  });

  it('places most recently added workspace first', () => {
    addToRecentWorkspaces('/home/user/project-a');
    addToRecentWorkspaces('/home/user/project-b');
    const recent = getRecentWorkspaces();
    expect(recent[0].path).toBe('/home/user/project-b');
    expect(recent[1].path).toBe('/home/user/project-a');
  });

  it('moves existing entry to front instead of duplicating', () => {
    addToRecentWorkspaces('/home/user/project-a');
    addToRecentWorkspaces('/home/user/project-b');
    addToRecentWorkspaces('/home/user/project-a');
    const recent = getRecentWorkspaces();
    expect(recent).toHaveLength(2);
    expect(recent[0].path).toBe('/home/user/project-a');
  });

  it('caps list at 5 entries', () => {
    for (let i = 1; i <= 7; i++) {
      addToRecentWorkspaces(`/home/user/project-${i}`);
    }
    expect(getRecentWorkspaces()).toHaveLength(5);
  });

  it('drops oldest entry when cap exceeded', () => {
    for (let i = 1; i <= 6; i++) {
      addToRecentWorkspaces(`/home/user/project-${i}`);
    }
    const paths = getRecentWorkspaces().map(w => w.path);
    expect(paths).not.toContain('/home/user/project-1');
    expect(paths[0]).toBe('/home/user/project-6');
  });
});

describe('removeFromRecentWorkspaces', () => {
  it('removes the specified workspace', () => {
    addToRecentWorkspaces('/home/user/project-a');
    addToRecentWorkspaces('/home/user/project-b');
    removeFromRecentWorkspaces('/home/user/project-a');
    const paths = getRecentWorkspaces().map(w => w.path);
    expect(paths).not.toContain('/home/user/project-a');
    expect(paths).toContain('/home/user/project-b');
  });

  it('is a no-op when path not in list', () => {
    addToRecentWorkspaces('/home/user/project-a');
    removeFromRecentWorkspaces('/home/user/does-not-exist');
    expect(getRecentWorkspaces()).toHaveLength(1);
  });
});

describe('selected workspace path', () => {
  it('returns null when not set', () => {
    expect(getSelectedWorkspacePath()).toBeNull();
  });

  it('returns stored path after set', () => {
    setSelectedWorkspacePath('/home/user/project-a');
    expect(getSelectedWorkspacePath()).toBe('/home/user/project-a');
  });

  it('also adds to recent list when set', () => {
    setSelectedWorkspacePath('/home/user/project-a');
    expect(getRecentWorkspaces()[0].path).toBe('/home/user/project-a');
  });

  it('returns null after clear', () => {
    setSelectedWorkspacePath('/home/user/project-a');
    clearSelectedWorkspacePath();
    expect(getSelectedWorkspacePath()).toBeNull();
  });
});
