import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { WorkspaceHeader } from '@/components/workspace/WorkspaceHeader';
import type { WorkspaceResponse } from '@/types';

describe('WorkspaceHeader', () => {
  const mockWorkspace: WorkspaceResponse = {
    id: 'ws-123',
    repo_path: '/home/user/projects/my-app',
    state_dir: '/home/user/projects/my-app/.codeframe',
    tech_stack: 'Python with FastAPI',
    created_at: '2026-02-04T10:00:00Z',
  };

  const mockOnInitialize = jest.fn();

  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('when workspace exists', () => {
    it('displays the repository path', () => {
      render(
        <WorkspaceHeader
          workspace={mockWorkspace}
          isLoading={false}
          onInitialize={mockOnInitialize}
        />
      );

      expect(screen.getByText('CodeFRAME')).toBeInTheDocument();
      expect(screen.getByText(/my-app/)).toBeInTheDocument();
    });

    it('does not show initialize button when workspace exists', () => {
      render(
        <WorkspaceHeader
          workspace={mockWorkspace}
          isLoading={false}
          onInitialize={mockOnInitialize}
        />
      );

      expect(
        screen.queryByRole('button', { name: /initialize/i })
      ).not.toBeInTheDocument();
    });
  });

  describe('when workspace does not exist', () => {
    it('shows initialize button', () => {
      render(
        <WorkspaceHeader
          workspace={null}
          isLoading={false}
          onInitialize={mockOnInitialize}
        />
      );

      expect(
        screen.getByRole('button', { name: /initialize workspace/i })
      ).toBeInTheDocument();
    });

    it('calls onInitialize when button is clicked', async () => {
      mockOnInitialize.mockResolvedValueOnce(undefined);

      render(
        <WorkspaceHeader
          workspace={null}
          isLoading={false}
          onInitialize={mockOnInitialize}
        />
      );

      const button = screen.getByRole('button', { name: /initialize workspace/i });
      fireEvent.click(button);

      await waitFor(() => {
        expect(mockOnInitialize).toHaveBeenCalledTimes(1);
      });
    });

    it('displays "No workspace" message', () => {
      render(
        <WorkspaceHeader
          workspace={null}
          isLoading={false}
          onInitialize={mockOnInitialize}
        />
      );

      expect(screen.getByText(/no workspace initialized/i)).toBeInTheDocument();
    });
  });

  describe('loading state', () => {
    it('disables initialize button when loading', () => {
      render(
        <WorkspaceHeader
          workspace={null}
          isLoading={true}
          onInitialize={mockOnInitialize}
        />
      );

      const button = screen.getByRole('button', { name: /initializing/i });
      expect(button).toBeDisabled();
    });

    it('shows loading text on button', () => {
      render(
        <WorkspaceHeader
          workspace={null}
          isLoading={true}
          onInitialize={mockOnInitialize}
        />
      );

      expect(screen.getByText(/initializing/i)).toBeInTheDocument();
    });
  });
});
