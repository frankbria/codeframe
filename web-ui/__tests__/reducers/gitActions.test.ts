/**
 * Git Reducer Actions Tests
 *
 * Tests for Git-related reducer action handlers.
 * Following TDD approach - these tests are written before implementation.
 *
 * Ticket: #272 - Git Visualization
 */

import { agentReducer, getInitialState } from '@/reducers/agentReducer';
import type {
  AgentState,
  GitStatusLoadedAction,
  GitCommitsLoadedAction,
  GitBranchesLoadedAction,
  CommitCreatedAction,
  BranchCreatedAction,
  GitLoadingAction,
  GitErrorAction,
} from '@/types/agentState';
import type { GitState, GitStatus, GitCommit, GitBranch } from '@/types/git';
import { INITIAL_GIT_STATE } from '@/types/git';

// ============================================================================
// Test Fixtures
// ============================================================================

function createMockGitStatus(overrides: Partial<GitStatus> = {}): GitStatus {
  return {
    current_branch: 'feature/test',
    is_dirty: false,
    modified_files: [],
    untracked_files: [],
    staged_files: [],
    ...overrides,
  };
}

function createMockGitCommit(overrides: Partial<GitCommit> = {}): GitCommit {
  return {
    hash: 'abc123def456789',
    short_hash: 'abc123d',
    message: 'feat: Add test feature',
    author: 'Agent <agent@codeframe.io>',
    timestamp: '2025-01-01T12:00:00Z',
    ...overrides,
  };
}

function createMockGitBranch(overrides: Partial<GitBranch> = {}): GitBranch {
  return {
    id: 1,
    branch_name: 'feature/test',
    issue_id: 10,
    status: 'active',
    created_at: '2025-01-01T00:00:00Z',
    ...overrides,
  };
}

function createStateWithGitState(gitState: Partial<GitState> = {}): AgentState {
  return {
    ...getInitialState(),
    gitState: {
      ...INITIAL_GIT_STATE,
      ...gitState,
    },
  };
}

// ============================================================================
// GIT_STATUS_LOADED Tests
// ============================================================================

describe('GIT_STATUS_LOADED', () => {
  it('should initialize gitState when null', () => {
    const initialState = getInitialState();
    expect(initialState.gitState).toBeNull();

    const status = createMockGitStatus();
    const action: GitStatusLoadedAction = {
      type: 'GIT_STATUS_LOADED',
      payload: { status, timestamp: Date.now() },
    };

    const newState = agentReducer(initialState, action);

    expect(newState.gitState).not.toBeNull();
    expect(newState.gitState?.status).toEqual(status);
    expect(newState.gitState?.isLoading).toBe(false);
    expect(newState.gitState?.error).toBeNull();
  });

  it('should update existing gitState with new status', () => {
    const initialState = createStateWithGitState({
      status: createMockGitStatus({ current_branch: 'main' }),
    });

    const newStatus = createMockGitStatus({ current_branch: 'feature/new' });
    const action: GitStatusLoadedAction = {
      type: 'GIT_STATUS_LOADED',
      payload: { status: newStatus, timestamp: Date.now() },
    };

    const newState = agentReducer(initialState, action);

    expect(newState.gitState?.status?.current_branch).toBe('feature/new');
  });

  it('should preserve commits and branches when updating status', () => {
    const commits = [createMockGitCommit()];
    const branches = [createMockGitBranch()];
    const initialState = createStateWithGitState({
      recentCommits: commits,
      branches: branches,
    });

    const action: GitStatusLoadedAction = {
      type: 'GIT_STATUS_LOADED',
      payload: { status: createMockGitStatus(), timestamp: Date.now() },
    };

    const newState = agentReducer(initialState, action);

    expect(newState.gitState?.recentCommits).toEqual(commits);
    expect(newState.gitState?.branches).toEqual(branches);
  });
});

// ============================================================================
// GIT_COMMITS_LOADED Tests
// ============================================================================

describe('GIT_COMMITS_LOADED', () => {
  it('should load commits into gitState', () => {
    const initialState = createStateWithGitState();
    const commits = [
      createMockGitCommit({ hash: 'commit1' }),
      createMockGitCommit({ hash: 'commit2' }),
    ];

    const action: GitCommitsLoadedAction = {
      type: 'GIT_COMMITS_LOADED',
      payload: { commits, timestamp: Date.now() },
    };

    const newState = agentReducer(initialState, action);

    expect(newState.gitState?.recentCommits).toEqual(commits);
    expect(newState.gitState?.recentCommits).toHaveLength(2);
  });

  it('should replace existing commits', () => {
    const initialState = createStateWithGitState({
      recentCommits: [createMockGitCommit({ hash: 'old' })],
    });

    const newCommits = [createMockGitCommit({ hash: 'new' })];
    const action: GitCommitsLoadedAction = {
      type: 'GIT_COMMITS_LOADED',
      payload: { commits: newCommits, timestamp: Date.now() },
    };

    const newState = agentReducer(initialState, action);

    expect(newState.gitState?.recentCommits).toHaveLength(1);
    expect(newState.gitState?.recentCommits[0].hash).toBe('new');
  });
});

// ============================================================================
// GIT_BRANCHES_LOADED Tests
// ============================================================================

describe('GIT_BRANCHES_LOADED', () => {
  it('should load branches into gitState', () => {
    const initialState = createStateWithGitState();
    const branches = [
      createMockGitBranch({ id: 1, branch_name: 'feature/a' }),
      createMockGitBranch({ id: 2, branch_name: 'feature/b' }),
    ];

    const action: GitBranchesLoadedAction = {
      type: 'GIT_BRANCHES_LOADED',
      payload: { branches, timestamp: Date.now() },
    };

    const newState = agentReducer(initialState, action);

    expect(newState.gitState?.branches).toEqual(branches);
    expect(newState.gitState?.branches).toHaveLength(2);
  });
});

// ============================================================================
// COMMIT_CREATED Tests
// ============================================================================

describe('COMMIT_CREATED', () => {
  it('should prepend new commit to recentCommits', () => {
    const existingCommit = createMockGitCommit({ hash: 'existing' });
    const initialState = createStateWithGitState({
      recentCommits: [existingCommit],
    });

    const newCommit = createMockGitCommit({ hash: 'new-commit' });
    const action: CommitCreatedAction = {
      type: 'COMMIT_CREATED',
      payload: { commit: newCommit, timestamp: Date.now() },
    };

    const newState = agentReducer(initialState, action);

    expect(newState.gitState?.recentCommits).toHaveLength(2);
    expect(newState.gitState?.recentCommits[0].hash).toBe('new-commit');
    expect(newState.gitState?.recentCommits[1].hash).toBe('existing');
  });

  it('should limit recentCommits to 10 items (FIFO)', () => {
    const existingCommits = Array.from({ length: 10 }, (_, i) =>
      createMockGitCommit({ hash: `commit-${i}` })
    );
    const initialState = createStateWithGitState({
      recentCommits: existingCommits,
    });

    const newCommit = createMockGitCommit({ hash: 'newest' });
    const action: CommitCreatedAction = {
      type: 'COMMIT_CREATED',
      payload: { commit: newCommit, timestamp: Date.now() },
    };

    const newState = agentReducer(initialState, action);

    expect(newState.gitState?.recentCommits).toHaveLength(10);
    expect(newState.gitState?.recentCommits[0].hash).toBe('newest');
    // Oldest commit should be dropped
    expect(newState.gitState?.recentCommits.find(c => c.hash === 'commit-9')).toBeUndefined();
  });

  it('should initialize gitState if null when commit created', () => {
    const initialState = getInitialState();
    expect(initialState.gitState).toBeNull();

    const newCommit = createMockGitCommit();
    const action: CommitCreatedAction = {
      type: 'COMMIT_CREATED',
      payload: { commit: newCommit, timestamp: Date.now() },
    };

    const newState = agentReducer(initialState, action);

    expect(newState.gitState).not.toBeNull();
    expect(newState.gitState?.recentCommits).toHaveLength(1);
  });
});

// ============================================================================
// BRANCH_CREATED Tests
// ============================================================================

describe('BRANCH_CREATED', () => {
  it('should add new branch to branches array', () => {
    const existingBranch = createMockGitBranch({ id: 1, branch_name: 'existing' });
    const initialState = createStateWithGitState({
      branches: [existingBranch],
    });

    const newBranch = createMockGitBranch({ id: 2, branch_name: 'new-branch' });
    const action: BranchCreatedAction = {
      type: 'BRANCH_CREATED',
      payload: { branch: newBranch, timestamp: Date.now() },
    };

    const newState = agentReducer(initialState, action);

    expect(newState.gitState?.branches).toHaveLength(2);
    expect(newState.gitState?.branches.find(b => b.branch_name === 'new-branch')).toBeDefined();
  });

  it('should initialize gitState if null when branch created', () => {
    const initialState = getInitialState();
    expect(initialState.gitState).toBeNull();

    const newBranch = createMockGitBranch();
    const action: BranchCreatedAction = {
      type: 'BRANCH_CREATED',
      payload: { branch: newBranch, timestamp: Date.now() },
    };

    const newState = agentReducer(initialState, action);

    expect(newState.gitState).not.toBeNull();
    expect(newState.gitState?.branches).toHaveLength(1);
  });
});

// ============================================================================
// GIT_LOADING Tests
// ============================================================================

describe('GIT_LOADING', () => {
  it('should set isLoading to true', () => {
    const initialState = createStateWithGitState({ isLoading: false });

    const action: GitLoadingAction = {
      type: 'GIT_LOADING',
      payload: true,
    };

    const newState = agentReducer(initialState, action);

    expect(newState.gitState?.isLoading).toBe(true);
  });

  it('should set isLoading to false', () => {
    const initialState = createStateWithGitState({ isLoading: true });

    const action: GitLoadingAction = {
      type: 'GIT_LOADING',
      payload: false,
    };

    const newState = agentReducer(initialState, action);

    expect(newState.gitState?.isLoading).toBe(false);
  });

  it('should initialize gitState if null', () => {
    const initialState = getInitialState();

    const action: GitLoadingAction = {
      type: 'GIT_LOADING',
      payload: true,
    };

    const newState = agentReducer(initialState, action);

    expect(newState.gitState).not.toBeNull();
    expect(newState.gitState?.isLoading).toBe(true);
  });
});

// ============================================================================
// GIT_ERROR Tests
// ============================================================================

describe('GIT_ERROR', () => {
  it('should set error message', () => {
    const initialState = createStateWithGitState({ error: null });

    const action: GitErrorAction = {
      type: 'GIT_ERROR',
      payload: 'Failed to fetch git status',
    };

    const newState = agentReducer(initialState, action);

    expect(newState.gitState?.error).toBe('Failed to fetch git status');
    expect(newState.gitState?.isLoading).toBe(false);
  });

  it('should clear error when payload is null', () => {
    const initialState = createStateWithGitState({ error: 'Previous error' });

    const action: GitErrorAction = {
      type: 'GIT_ERROR',
      payload: null,
    };

    const newState = agentReducer(initialState, action);

    expect(newState.gitState?.error).toBeNull();
  });
});
