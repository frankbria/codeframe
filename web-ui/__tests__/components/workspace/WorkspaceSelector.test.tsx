import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { WorkspaceSelector } from '@/components/workspace/WorkspaceSelector';
import type { WorkspaceRegistryItem } from '@/types';

// Mock the server-backed workspaces hook (issue #601)
const mockRemoveWorkspace = jest.fn();
let mockHookState: {
  workspaces: WorkspaceRegistryItem[];
  isLoading: boolean;
  error: unknown;
};

jest.mock('@/hooks/useWorkspaces', () => ({
  useWorkspaces: () => ({
    workspaces: mockHookState.workspaces,
    isLoading: mockHookState.isLoading,
    error: mockHookState.error,
    refresh: jest.fn(),
    removeWorkspace: mockRemoveWorkspace,
  }),
}));

function makeItem(overrides: Partial<WorkspaceRegistryItem>): WorkspaceRegistryItem {
  return {
    id: 'default-test-id',
    repo_path: '/home/user/project',
    name: 'project',
    tech_stack: null,
    created_at: '2026-01-01T00:00:00Z',
    last_opened_at: new Date().toISOString(),
    path_exists: true,
    ...overrides,
  };
}

describe('WorkspaceSelector', () => {
  const mockOnSelectWorkspace = jest.fn();

  beforeEach(() => {
    jest.clearAllMocks();
    mockHookState = { workspaces: [], isLoading: false, error: null };
    mockOnSelectWorkspace.mockResolvedValue(undefined);
    mockRemoveWorkspace.mockResolvedValue(undefined);
  });

  describe('initial render', () => {
    it('renders the header and description', () => {
      render(
        <WorkspaceSelector
          onSelectWorkspace={mockOnSelectWorkspace}
          isLoading={false}
          error={null}
        />
      );

      expect(screen.getByText('CodeFRAME')).toBeInTheDocument();
      expect(
        screen.getByText('Select a project to get started')
      ).toBeInTheDocument();
    });

    it('renders the path input form', () => {
      render(
        <WorkspaceSelector
          onSelectWorkspace={mockOnSelectWorkspace}
          isLoading={false}
          error={null}
        />
      );

      // "Open Project" appears as both card title and button - use heading role for title
      expect(screen.getByRole('heading', { name: 'Open Project' })).toBeInTheDocument();
      expect(screen.getByLabelText('Repository Path')).toBeInTheDocument();
      expect(
        screen.getByPlaceholderText('/home/user/projects/my-app')
      ).toBeInTheDocument();
    });

    it('shows help text about .codeframe directory', () => {
      render(
        <WorkspaceSelector
          onSelectWorkspace={mockOnSelectWorkspace}
          isLoading={false}
          error={null}
        />
      );

      expect(screen.getByText('.codeframe')).toBeInTheDocument();
    });
  });

  describe('form submission', () => {
    it('calls onSelectWorkspace when form is submitted with valid path', async () => {
      render(
        <WorkspaceSelector
          onSelectWorkspace={mockOnSelectWorkspace}
          isLoading={false}
          error={null}
        />
      );

      const input = screen.getByPlaceholderText('/home/user/projects/my-app');
      await userEvent.type(input, '/home/user/test-project');

      const submitButton = screen.getByRole('button', { name: 'Open Project' });
      await userEvent.click(submitButton);

      expect(mockOnSelectWorkspace).toHaveBeenCalledWith(
        '/home/user/test-project'
      );
    });

    it('trims whitespace from input path', async () => {
      render(
        <WorkspaceSelector
          onSelectWorkspace={mockOnSelectWorkspace}
          isLoading={false}
          error={null}
        />
      );

      const input = screen.getByPlaceholderText('/home/user/projects/my-app');
      await userEvent.type(input, '  /home/user/test-project  ');

      const submitButton = screen.getByRole('button', { name: 'Open Project' });
      await userEvent.click(submitButton);

      expect(mockOnSelectWorkspace).toHaveBeenCalledWith(
        '/home/user/test-project'
      );
    });

    it('does not submit when path is empty', async () => {
      render(
        <WorkspaceSelector
          onSelectWorkspace={mockOnSelectWorkspace}
          isLoading={false}
          error={null}
        />
      );

      const submitButton = screen.getByRole('button', { name: 'Open Project' });
      expect(submitButton).toBeDisabled();

      await userEvent.click(submitButton);

      expect(mockOnSelectWorkspace).not.toHaveBeenCalled();
    });

    it('does not submit when path is only whitespace', async () => {
      render(
        <WorkspaceSelector
          onSelectWorkspace={mockOnSelectWorkspace}
          isLoading={false}
          error={null}
        />
      );

      const input = screen.getByPlaceholderText('/home/user/projects/my-app');
      await userEvent.type(input, '   ');

      const submitButton = screen.getByRole('button', { name: 'Open Project' });
      expect(submitButton).toBeDisabled();
    });
  });

  describe('loading state', () => {
    it('disables input when loading', () => {
      render(
        <WorkspaceSelector
          onSelectWorkspace={mockOnSelectWorkspace}
          isLoading={true}
          error={null}
        />
      );

      const input = screen.getByPlaceholderText('/home/user/projects/my-app');
      expect(input).toBeDisabled();
    });

    it('shows loading spinner in submit button', () => {
      render(
        <WorkspaceSelector
          onSelectWorkspace={mockOnSelectWorkspace}
          isLoading={true}
          error={null}
        />
      );

      expect(screen.getByText('Opening...')).toBeInTheDocument();
    });

    it('disables submit button when loading', () => {
      render(
        <WorkspaceSelector
          onSelectWorkspace={mockOnSelectWorkspace}
          isLoading={true}
          error={null}
        />
      );

      const submitButton = screen.getByRole('button', { name: /opening/i });
      expect(submitButton).toBeDisabled();
    });
  });

  describe('error state', () => {
    it('displays error message when error prop is set', () => {
      render(
        <WorkspaceSelector
          onSelectWorkspace={mockOnSelectWorkspace}
          isLoading={false}
          error="Workspace not found at specified path"
        />
      );

      expect(
        screen.getByText('Workspace not found at specified path')
      ).toBeInTheDocument();
    });

    it('shows error in a styled error container', () => {
      render(
        <WorkspaceSelector
          onSelectWorkspace={mockOnSelectWorkspace}
          isLoading={false}
          error="Invalid path"
        />
      );

      const errorElement = screen.getByText('Invalid path');
      expect(errorElement).toHaveClass('text-destructive');
    });
  });

  describe('recent workspaces', () => {
    const mockRecentWorkspaces: WorkspaceRegistryItem[] = [
      makeItem({
        id: 'id-a',
        repo_path: '/home/user/project-a',
        name: 'project-a',
        last_opened_at: new Date().toISOString(),
      }),
      makeItem({
        id: 'id-b',
        repo_path: '/home/user/project-b',
        name: 'project-b',
        last_opened_at: new Date(Date.now() - 86400000).toISOString(), // 1 day ago
      }),
    ];

    beforeEach(() => {
      mockHookState.workspaces = mockRecentWorkspaces;
    });

    it('shows recent projects section when there are recent workspaces', () => {
      render(
        <WorkspaceSelector
          onSelectWorkspace={mockOnSelectWorkspace}
          isLoading={false}
          error={null}
        />
      );

      expect(screen.getByText('Recent Projects')).toBeInTheDocument();
    });

    it('displays workspace names and paths', () => {
      render(
        <WorkspaceSelector
          onSelectWorkspace={mockOnSelectWorkspace}
          isLoading={false}
          error={null}
        />
      );

      expect(screen.getByText('project-a')).toBeInTheDocument();
      expect(screen.getByText('/home/user/project-a')).toBeInTheDocument();
      expect(screen.getByText('project-b')).toBeInTheDocument();
      expect(screen.getByText('/home/user/project-b')).toBeInTheDocument();
    });

    it('shows empty state message when no recent workspaces', () => {
      mockHookState.workspaces = [];

      render(
        <WorkspaceSelector
          onSelectWorkspace={mockOnSelectWorkspace}
          isLoading={false}
          error={null}
        />
      );

      expect(screen.getByText('Recent Projects')).toBeInTheDocument();
      expect(screen.getByText(/no recent projects/i)).toBeInTheDocument();
    });

    it('selects workspace when clicking on recent item', async () => {
      render(
        <WorkspaceSelector
          onSelectWorkspace={mockOnSelectWorkspace}
          isLoading={false}
          error={null}
        />
      );

      const projectA = screen.getByText('project-a').closest('[role="button"]');
      await userEvent.click(projectA!);

      expect(mockOnSelectWorkspace).toHaveBeenCalledWith(
        '/home/user/project-a'
      );
    });

    it('selects workspace on Enter key press', async () => {
      render(
        <WorkspaceSelector
          onSelectWorkspace={mockOnSelectWorkspace}
          isLoading={false}
          error={null}
        />
      );

      const projectA = screen.getByText('project-a').closest('[role="button"]');
      projectA?.focus();
      fireEvent.keyDown(projectA!, { key: 'Enter' });

      await waitFor(() => {
        expect(mockOnSelectWorkspace).toHaveBeenCalledWith(
          '/home/user/project-a'
        );
      });
    });

    it('selects workspace on Space key press', async () => {
      render(
        <WorkspaceSelector
          onSelectWorkspace={mockOnSelectWorkspace}
          isLoading={false}
          error={null}
        />
      );

      const projectA = screen.getByText('project-a').closest('[role="button"]');
      projectA?.focus();
      fireEvent.keyDown(projectA!, { key: ' ' });

      await waitFor(() => {
        expect(mockOnSelectWorkspace).toHaveBeenCalledWith(
          '/home/user/project-a'
        );
      });
    });

    it('removes workspace via the server-backed hook when remove button is clicked', async () => {
      render(
        <WorkspaceSelector
          onSelectWorkspace={mockOnSelectWorkspace}
          isLoading={false}
          error={null}
        />
      );

      const removeButtons = screen.getAllByTitle(/remove from recent/i);
      await userEvent.click(removeButtons[0]);

      expect(mockRemoveWorkspace).toHaveBeenCalledWith('id-a');
    });

    it('does not select workspace when remove button is clicked', async () => {
      render(
        <WorkspaceSelector
          onSelectWorkspace={mockOnSelectWorkspace}
          isLoading={false}
          error={null}
        />
      );

      const removeButtons = screen.getAllByTitle(/remove from recent/i);
      await userEvent.click(removeButtons[0]);

      // onSelectWorkspace should not be called because stopPropagation prevents it
      expect(mockOnSelectWorkspace).not.toHaveBeenCalled();
    });

    it('does not open workspace when Enter is pressed on the remove button', async () => {
      render(
        <WorkspaceSelector
          onSelectWorkspace={mockOnSelectWorkspace}
          isLoading={false}
          error={null}
        />
      );

      const removeButton = screen.getAllByTitle(/remove from recent/i)[0];
      fireEvent.keyDown(removeButton, { key: 'Enter' });

      expect(mockOnSelectWorkspace).not.toHaveBeenCalled();
    });

    it('disables recent workspace selection when loading', async () => {
      render(
        <WorkspaceSelector
          onSelectWorkspace={mockOnSelectWorkspace}
          isLoading={true}
          error={null}
        />
      );

      const projectA = screen.getByText('project-a').closest('[role="button"]');
      expect(projectA).toHaveAttribute('aria-disabled', 'true');

      await userEvent.click(projectA!);
      expect(mockOnSelectWorkspace).not.toHaveBeenCalled();
    });

    it('shows a loading state while the server list is being fetched', () => {
      mockHookState.workspaces = [];
      mockHookState.isLoading = true;

      render(
        <WorkspaceSelector
          onSelectWorkspace={mockOnSelectWorkspace}
          isLoading={false}
          error={null}
        />
      );

      expect(screen.getByTestId('workspaces-loading')).toBeInTheDocument();
    });

    it('marks workspaces whose path no longer exists as stale', () => {
      mockHookState.workspaces = [
        makeItem({
          id: 'id-stale',
          repo_path: '/home/user/gone',
          name: 'gone',
          path_exists: false,
        }),
      ];

      render(
        <WorkspaceSelector
          onSelectWorkspace={mockOnSelectWorkspace}
          isLoading={false}
          error={null}
        />
      );

      expect(screen.getByText('Missing')).toBeInTheDocument();
    });
  });
});
