import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { DiffViewer } from '@/components/review/DiffViewer';
import type { Task } from '@/types';
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
    oldPath: 'a/src/foo.ts',
    newPath: 'b/src/foo.ts',
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

// ─── Tests ──────────────────────────────────────────────────────────

describe('DiffViewer', () => {
  it('renders "No changes to display" when diffFiles is empty', () => {
    render(<DiffViewer diffFiles={[]} selectedFile={null} />);
    expect(screen.getByText('No changes to display')).toBeInTheDocument();
  });

  it('does not render task chip when tasks is undefined', () => {
    render(<DiffViewer diffFiles={mockDiffFiles} selectedFile={null} />);
    expect(screen.queryByText('Add login')).not.toBeInTheDocument();
    expect(screen.queryByText(/View Task/)).not.toBeInTheDocument();
  });

  it('does not render task chip when tasks is empty', () => {
    render(<DiffViewer diffFiles={mockDiffFiles} selectedFile={null} tasks={[]} />);
    expect(screen.queryByText(/View Task/)).not.toBeInTheDocument();
  });

  it('renders task title chip when tasks has items', () => {
    render(<DiffViewer diffFiles={mockDiffFiles} selectedFile={null} tasks={mockTasks} />);
    expect(screen.getByText('Add login')).toBeInTheDocument();
  });

  it('renders requirement ID when task has requirement_ids', () => {
    render(<DiffViewer diffFiles={mockDiffFiles} selectedFile={null} tasks={mockTasks} />);
    expect(screen.getByText('REQ: REQ-42')).toBeInTheDocument();
  });

  it('renders "View Task" link pointing to /tasks', () => {
    render(<DiffViewer diffFiles={mockDiffFiles} selectedFile={null} tasks={mockTasks} />);
    const link = screen.getByText(/View Task/);
    expect(link.closest('a')).toHaveAttribute('href', '/tasks');
  });

  it('clicking "View Task" link does not collapse the file', async () => {
    const user = userEvent.setup();
    render(<DiffViewer diffFiles={mockDiffFiles} selectedFile={null} tasks={mockTasks} />);

    // Content should be visible
    expect(screen.getByText('const a = 1;')).toBeInTheDocument();

    // Click the View Task link
    const link = screen.getByText(/View Task/);
    await user.click(link);

    // Content should still be visible (not collapsed)
    expect(screen.getByText('const a = 1;')).toBeInTheDocument();
  });
});
