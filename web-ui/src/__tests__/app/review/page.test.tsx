/**
 * Review page orchestration coverage (issue #964).
 *
 * The page is the Ship orchestrator — it wires diff load, gate runs, commit,
 * patch export and PR creation together — and had no unit coverage at all.
 * The nightly e2e only asserted that one action button was visible, so nothing
 * checked the call shapes these handlers send or what the user is told when
 * they fail.
 *
 * The child components are rendered as thin harnesses: this file is about the
 * orchestration, and each child has its own suite.
 */
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

jest.mock('@/lib/api', () => ({
  reviewApi: {
    getDiff: jest.fn(),
    getPatch: jest.fn(),
    generateCommitMessage: jest.fn(),
  },
  gatesApi: { run: jest.fn() },
  gitApi: { commit: jest.fn(), getStatus: jest.fn() },
  prApi: { create: jest.fn(), list: jest.fn() },
  tasksApi: { list: jest.fn() },
}));

jest.mock('@/lib/workspace-storage', () => ({
  getSelectedWorkspacePath: jest.fn(() => '/ws'),
}));

// Drive the page's handlers directly rather than through child internals.
jest.mock('@/components/review/CommitPanel', () => ({
  CommitPanel: ({
    onCommit,
    onGenerateMessage,
    onCreatePR,
    commitMessage,
    isCommitting,
  }: {
    onCommit: () => void;
    onGenerateMessage: () => void;
    onCreatePR: (t: string, b: string) => void;
    commitMessage: string;
    isCommitting: boolean;
  }) => (
    <div>
      <span data-testid="commit-message">{commitMessage}</span>
      <span data-testid="is-committing">{String(isCommitting)}</span>
      <button onClick={onCommit}>do-commit</button>
      <button onClick={onGenerateMessage}>do-generate</button>
      <button onClick={() => onCreatePR('T', 'B')}>do-create-pr</button>
    </div>
  ),
}));

jest.mock('@/components/review/ReviewHeader', () => ({
  ReviewHeader: ({
    onRunGates,
    onExportPatch,
  }: {
    onRunGates: () => void;
    onExportPatch: () => void;
  }) => (
    <div>
      <button onClick={onRunGates}>do-gates</button>
      <button onClick={onExportPatch}>do-export</button>
    </div>
  ),
}));

import useSWR from 'swr';
import { reviewApi, gatesApi, gitApi, prApi } from '@/lib/api';
import ReviewPage from '@/app/review/page';

jest.mock('swr', () => ({ __esModule: true, default: jest.fn() }));

const mockUseSWR = useSWR as jest.MockedFunction<typeof useSWR>;
const mockCommit = gitApi.commit as jest.Mock;
const mockRunGates = gatesApi.run as jest.Mock;
const mockGetPatch = reviewApi.getPatch as jest.Mock;
const mockGenerate = reviewApi.generateCommitMessage as jest.Mock;
const mockCreatePR = prApi.create as jest.Mock;

const DIFF = {
  changed_files: [
    { path: 'src/a.ts', additions: 3, deletions: 1, status: 'modified' },
    { path: 'src/b.ts', additions: 5, deletions: 0, status: 'added' },
  ],
  total_additions: 8,
  total_deletions: 1,
};

const mutateDiff = jest.fn();

beforeEach(() => {
  jest.clearAllMocks();
  (gitApi.getStatus as jest.Mock).mockResolvedValue({ branch: 'main' });
  (prApi.list as jest.Mock).mockResolvedValue({ pull_requests: [] });
  // The page auto-generates a commit message once the diff loads; without a
  // resolved promise here every test dies on `.then of undefined`.
  mockGenerate.mockResolvedValue({ message: '' });

  // The page keys SWR on the request URL string, not a tuple.
  mockUseSWR.mockImplementation(((key: unknown) => {
    if (typeof key === 'string' && key.includes('/review/diff')) {
      return { data: DIFF, error: undefined, isLoading: false, mutate: mutateDiff };
    }
    return { data: undefined, error: undefined, isLoading: false, mutate: jest.fn() };
  }) as never);
});

describe('review page — diff load', () => {
  it('loads the diff and exposes the changed files to the commit panel', async () => {
    render(<ReviewPage />);
    await waitFor(() => expect(screen.getByText('do-commit')).toBeInTheDocument());
  });

  it('auto-generates a commit message once, not on every render', async () => {
    mockGenerate.mockResolvedValue({ message: 'chore: auto' });
    const { rerender } = render(<ReviewPage />);

    await waitFor(() =>
      expect(screen.getByTestId('commit-message')).toHaveTextContent('chore: auto')
    );
    rerender(<ReviewPage />);
    await waitFor(() => expect(mockGenerate).toHaveBeenCalledTimes(1));
  });

  it('leaves the page usable when auto-generation fails', async () => {
    mockGenerate.mockRejectedValue(new Error('llm down'));
    render(<ReviewPage />);

    await waitFor(() => expect(screen.getByText('do-commit')).toBeInTheDocument());
    expect(screen.getByTestId('commit-message')).toHaveTextContent('');
  });
});

describe('review page — gates', () => {
  it('runs gates through gatesApi', async () => {
    mockRunGates.mockResolvedValue({ passed: true, checks: [] });
    render(<ReviewPage />);

    await userEvent.click(screen.getByText('do-gates'));

    await waitFor(() => expect(mockRunGates).toHaveBeenCalledWith('/ws'));
  });

  it('reports a gate failure to the user', async () => {
    mockRunGates.mockRejectedValue({ detail: 'gates exploded' });
    render(<ReviewPage />);

    await userEvent.click(screen.getByText('do-gates'));

    await waitFor(() =>
      expect(screen.getByText('gates exploded')).toBeInTheDocument()
    );
  });
});

describe('review page — commit', () => {
  it('sends every changed file path with the message', async () => {
    mockGenerate.mockResolvedValue({ message: 'feat: things' });
    mockCommit.mockResolvedValue({ commit_hash: 'abcdef1234', files_changed: 2 });
    render(<ReviewPage />);

    // The page owns the message; populate it the way the UI does.
    await userEvent.click(screen.getByText('do-generate'));
    await waitFor(() =>
      expect(screen.getByTestId('commit-message')).toHaveTextContent('feat: things')
    );

    await userEvent.click(screen.getByText('do-commit'));

    await waitFor(() =>
      expect(mockCommit).toHaveBeenCalledWith(
        '/ws',
        ['src/a.ts', 'src/b.ts'],
        'feat: things'
      )
    );
  });

  it('confirms the commit with its short hash and refreshes the diff', async () => {
    mockGenerate.mockResolvedValue({ message: 'feat: things' });
    mockCommit.mockResolvedValue({ commit_hash: 'abcdef1234567', files_changed: 2 });
    render(<ReviewPage />);

    await userEvent.click(screen.getByText('do-generate'));
    await waitFor(() =>
      expect(screen.getByTestId('commit-message')).toHaveTextContent('feat: things')
    );
    await userEvent.click(screen.getByText('do-commit'));

    await waitFor(() =>
      expect(screen.getByText(/committed 2 files: abcdef1/i)).toBeInTheDocument()
    );
    expect(mutateDiff).toHaveBeenCalled();
  });

  it('refuses to commit an empty message without calling the API', async () => {
    mockGenerate.mockResolvedValue({ message: '   ' }); // whitespace only
    render(<ReviewPage />);
    await userEvent.click(screen.getByText('do-commit'));
    await waitFor(() => expect(mockCommit).not.toHaveBeenCalled());
  });

  it('surfaces a commit failure and does not clear the message', async () => {
    mockGenerate.mockResolvedValue({ message: 'feat: things' });
    mockCommit.mockRejectedValue({ detail: 'pre-commit hook rejected' });
    render(<ReviewPage />);

    await userEvent.click(screen.getByText('do-generate'));
    await waitFor(() =>
      expect(screen.getByTestId('commit-message')).toHaveTextContent('feat: things')
    );
    await userEvent.click(screen.getByText('do-commit'));

    await waitFor(() =>
      expect(screen.getByText('pre-commit hook rejected')).toBeInTheDocument()
    );
    // Losing the typed message on failure would be the worst outcome here.
    expect(screen.getByTestId('commit-message')).toHaveTextContent('feat: things');
  });

  it('clears the in-flight flag even when the commit fails', async () => {
    mockGenerate.mockResolvedValue({ message: 'm' });
    mockCommit.mockRejectedValue({ detail: 'nope' });
    render(<ReviewPage />);

    await userEvent.click(screen.getByText('do-generate'));
    await waitFor(() => expect(screen.getByTestId('commit-message')).toHaveTextContent('m'));
    await userEvent.click(screen.getByText('do-commit'));

    await waitFor(() =>
      expect(screen.getByTestId('is-committing')).toHaveTextContent('false')
    );
  });
});

describe('review page — export patch', () => {
  it('fetches the patch and opens the modal', async () => {
    mockGetPatch.mockResolvedValue({ patch: 'diff --git a/x b/x', filename: 'x.patch' });
    render(<ReviewPage />);

    await userEvent.click(screen.getByText('do-export'));

    await waitFor(() => expect(mockGetPatch).toHaveBeenCalledWith('/ws'));
    await waitFor(() => expect(screen.getByText('x.patch')).toBeInTheDocument());
  });
});

describe('review page — pull request', () => {
  it('creates a PR against the current branch and shows the result', async () => {
    mockCreatePR.mockResolvedValue({ url: 'https://github.com/o/r/pull/7', number: 7 });
    render(<ReviewPage />);

    await userEvent.click(screen.getByText('do-create-pr'));

    await waitFor(() =>
      expect(mockCreatePR).toHaveBeenCalledWith('/ws', {
        branch: '',
        title: 'T',
        body: 'B',
      })
    );
  });

  it('reports a PR failure', async () => {
    mockCreatePR.mockRejectedValue({ detail: 'no upstream remote' });
    render(<ReviewPage />);

    await userEvent.click(screen.getByText('do-create-pr'));

    await waitFor(() =>
      expect(screen.getByText('no upstream remote')).toBeInTheDocument()
    );
  });
});
