import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { DiffViewer } from '@/components/review/DiffViewer';
import type { FileChange, Task } from '@/types';
import type { DiffFile } from '@/lib/diffParser';

// jsdom doesn't provide ResizeObserver (needed by radix ScrollArea)
global.ResizeObserver = class {
  observe() {}
  unobserve() {}
  disconnect() {}
} as unknown as typeof ResizeObserver;

// Mock scrollIntoView (not available in jsdom)
Element.prototype.scrollIntoView = jest.fn();

// ─── Fixtures ───────────────────────────────────────────────────────

const mockDiffFiles: DiffFile[] = [
  {
    oldPath: 'src/foo.ts',
    newPath: 'src/foo.ts',
    hunks: [
      {
        header: '@@ -1,3 +1,4 @@',
        oldStart: 1,
        oldCount: 3,
        newStart: 1,
        newCount: 4,
        lines: [
          { type: 'context', content: 'const a = 1;', oldLineNumber: 1, newLineNumber: 1 },
          { type: 'addition', content: 'const b = 2;', oldLineNumber: null, newLineNumber: 2 },
        ],
      },
    ],
    insertions: 1,
    deletions: 0,
    isNew: false,
    isDeleted: false,
    isRenamed: false,
  },
];

const mockTasks: Task[] = [
  {
    id: 'task-1',
    title: 'Add login',
    description: '',
    status: 'IN_PROGRESS',
    priority: 1,
    depends_on: [],
    requirement_ids: ['REQ-42'],
  },
];

const mockTaskNoReqs: Task[] = [
  {
    id: 'task-1',
    title: 'Add login',
    description: '',
    status: 'IN_PROGRESS',
    priority: 1,
    depends_on: [],
  },
];

// getFilePath returns newPath for non-deleted/non-renamed files
const mockChangedFiles: FileChange[] = [
  { path: 'src/foo.ts', change_type: 'modified', insertions: 1, deletions: 0, task_id: 'task-1' },
];

// ─── Tests ──────────────────────────────────────────────────────────

describe('DiffViewer', () => {
  it('renders "No changes to display" when diffFiles is empty', () => {
    render(<DiffViewer diffFiles={[]} selectedFile={null} />);
    expect(screen.getByText('No changes to display')).toBeInTheDocument();
  });

  it('does not render task chip when no tasks or contextTask', () => {
    render(<DiffViewer diffFiles={mockDiffFiles} selectedFile={null} />);
    expect(screen.queryByText('Add login')).not.toBeInTheDocument();
    expect(screen.queryByText(/View Task/)).not.toBeInTheDocument();
  });

  it('does not render task chip when tasks is empty and no contextTask', () => {
    render(<DiffViewer diffFiles={mockDiffFiles} selectedFile={null} tasks={[]} />);
    expect(screen.queryByText(/View Task/)).not.toBeInTheDocument();
  });

  it('renders task chip via contextTask fallback when no per-file mapping', () => {
    render(
      <DiffViewer
        diffFiles={mockDiffFiles}
        selectedFile={null}
        tasks={mockTasks}
        contextTask={mockTasks[0]}
      />
    );
    expect(screen.getByText('Add login')).toBeInTheDocument();
  });

  it('renders task chip via per-file changedFiles mapping', () => {
    render(
      <DiffViewer
        diffFiles={mockDiffFiles}
        selectedFile={null}
        tasks={mockTasks}
        changedFiles={mockChangedFiles}
      />
    );
    expect(screen.getByText('Add login')).toBeInTheDocument();
  });

  it('renders requirement ID when task has requirement_ids', () => {
    render(
      <DiffViewer
        diffFiles={mockDiffFiles}
        selectedFile={null}
        tasks={mockTasks}
        contextTask={mockTasks[0]}
      />
    );
    expect(screen.getByText('REQ: REQ-42')).toBeInTheDocument();
  });

  it('does not render requirement ID when task has no requirement_ids', () => {
    render(
      <DiffViewer
        diffFiles={mockDiffFiles}
        selectedFile={null}
        tasks={mockTaskNoReqs}
        contextTask={mockTaskNoReqs[0]}
      />
    );
    expect(screen.queryByText(/REQ:/)).not.toBeInTheDocument();
  });

  it('renders "View Task" link pointing to /tasks', () => {
    render(
      <DiffViewer
        diffFiles={mockDiffFiles}
        selectedFile={null}
        tasks={mockTasks}
        contextTask={mockTasks[0]}
      />
    );
    const link = screen.getByText(/View Task/);
    expect(link.closest('a')).toHaveAttribute('href', '/tasks');
  });

  it('clicking "View Task" link does not collapse the file', async () => {
    const user = userEvent.setup();
    render(
      <DiffViewer
        diffFiles={mockDiffFiles}
        selectedFile={null}
        tasks={mockTasks}
        contextTask={mockTasks[0]}
      />
    );

    expect(screen.getByText('const a = 1;')).toBeInTheDocument();
    const link = screen.getByText(/View Task/);
    await user.click(link);
    expect(screen.getByText('const a = 1;')).toBeInTheDocument();
  });
});
