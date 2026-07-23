import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { FileTreePanel } from '@/components/review/FileTreePanel';
import type { FileChange, Task } from '@/types';

// jsdom doesn't provide ResizeObserver (needed by radix ScrollArea)
global.ResizeObserver = class {
  observe() {}
  unobserve() {}
  disconnect() {}
} as unknown as typeof ResizeObserver;

// ─── Fixtures ───────────────────────────────────────────────────────

const mockFiles: FileChange[] = [
  { path: 'src/foo.ts', change_type: 'modified', insertions: 5, deletions: 2, task_id: 'task-1', task_title: 'Add login' },
  { path: 'src/bar.ts', change_type: 'added', insertions: 10, deletions: 0 },
  { path: 'lib/utils.ts', change_type: 'modified', insertions: 3, deletions: 1, task_id: 'task-2', task_title: 'Fix utils' },
];

const mockTasks: Task[] = [
  { id: 'task-1', title: 'Add login', description: '', status: 'IN_PROGRESS', priority: 1, depends_on: [] },
  { id: 'task-2', title: 'Fix utils', description: '', status: 'READY', priority: 2, depends_on: [] },
];

const defaultProps = {
  files: mockFiles,
  selectedFile: null,
  onFileSelect: jest.fn(),
};

beforeEach(() => {
  jest.clearAllMocks();
});

// ─── Tests ──────────────────────────────────────────────────────────

describe('FileTreePanel', () => {
  it('renders file list grouped by directory', () => {
    render(<FileTreePanel {...defaultProps} />);
    expect(screen.getByText('src')).toBeInTheDocument();
    expect(screen.getByText('lib')).toBeInTheDocument();
    expect(screen.getByText('foo.ts')).toBeInTheDocument();
    expect(screen.getByText('bar.ts')).toBeInTheDocument();
    expect(screen.getByText('utils.ts')).toBeInTheDocument();
  });

  it('renders a grouping toggle button when tasks prop has items', () => {
    render(<FileTreePanel {...defaultProps} tasks={mockTasks} />);
    expect(screen.getByRole('button', { name: /task/i })).toBeInTheDocument();
  });

  it('does not render a grouping toggle when tasks is empty', () => {
    render(<FileTreePanel {...defaultProps} tasks={[]} />);
    expect(screen.queryByRole('button', { name: /task/i })).not.toBeInTheDocument();
  });

  it('does not render a grouping toggle when tasks is undefined', () => {
    render(<FileTreePanel {...defaultProps} />);
    expect(screen.queryByRole('button', { name: /task/i })).not.toBeInTheDocument();
  });

  it('groups files under task headers when toggled to task mode', async () => {
    const user = userEvent.setup();
    render(<FileTreePanel {...defaultProps} tasks={mockTasks} />);

    await user.click(screen.getByRole('button', { name: /task/i }));

    // Task group headers should appear
    expect(screen.getByText('Add login')).toBeInTheDocument();
    expect(screen.getByText('Fix utils')).toBeInTheDocument();
    expect(screen.getByText('Unassigned')).toBeInTheDocument();
  });

  it('shows task title badge next to filename in dir mode when file has task_title', () => {
    render(<FileTreePanel {...defaultProps} tasks={mockTasks} />);
    // In dir mode (default), files with task_title should show a badge
    const badges = screen.getAllByText('Add login');
    expect(badges.length).toBeGreaterThanOrEqual(1);
  });

  it('groups untagged files under contextTask when contextTask is provided', async () => {
    const user = userEvent.setup();
    const contextTask = mockTasks[0]; // 'Add login'
    const untaggedFiles: FileChange[] = [
      { path: 'src/untagged.ts', change_type: 'modified', insertions: 1, deletions: 0 },
    ];
    render(
      <FileTreePanel
        files={untaggedFiles}
        selectedFile={null}
        onFileSelect={jest.fn()}
        tasks={mockTasks}
        contextTask={contextTask}
      />
    );

    await user.click(screen.getByRole('button', { name: /group by task/i }));

    // Untagged file should appear under the contextTask group, not 'Unassigned'
    expect(screen.getByText('Add login')).toBeInTheDocument();
    expect(screen.queryByText('Unassigned')).not.toBeInTheDocument();
  });

  it('shows contextTask title as badge in dir mode for files without task_title', () => {
    const contextTask = mockTasks[0]; // 'Add login'
    const untaggedFiles: FileChange[] = [
      { path: 'src/untagged.ts', change_type: 'modified', insertions: 1, deletions: 0 },
    ];
    render(
      <FileTreePanel
        files={untaggedFiles}
        selectedFile={null}
        onFileSelect={jest.fn()}
        tasks={mockTasks}
        contextTask={contextTask}
      />
    );

    expect(screen.getByText('Add login')).toBeInTheDocument();
  });

  it('task groups are collapsible', async () => {
    const user = userEvent.setup();
    render(<FileTreePanel {...defaultProps} tasks={mockTasks} />);

    // Switch to task mode
    await user.click(screen.getByRole('button', { name: /task/i }));

    // Files should be visible
    expect(screen.getByText('foo.ts')).toBeInTheDocument();

    // Click on task group header to collapse
    const addLoginHeader = screen.getByRole('button', { name: /collapse add login/i });
    await user.click(addLoginHeader);

    // foo.ts should no longer be visible
    expect(screen.queryByText('foo.ts')).not.toBeInTheDocument();
  });
});
