import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { WorkspaceSelector } from '@/components/workspace/WorkspaceSelector';
import * as storage from '@/lib/workspace-storage';

jest.mock('@/lib/workspace-storage', () => ({
  getRecentWorkspaces: jest.fn(),
  removeFromRecentWorkspaces: jest.fn(),
}));

const mockGetRecent = storage.getRecentWorkspaces as jest.MockedFunction<typeof storage.getRecentWorkspaces>;
const mockRemove = storage.removeFromRecentWorkspaces as jest.MockedFunction<typeof storage.removeFromRecentWorkspaces>;

const RECENT = [
  { path: '/home/user/project-b', name: 'project-b', lastUsed: '2026-04-02T10:00:00Z' },
  { path: '/home/user/project-a', name: 'project-a', lastUsed: '2026-04-01T10:00:00Z' },
];

describe('WorkspaceSelector', () => {
  const onSelect = jest.fn();

  beforeEach(() => {
    jest.clearAllMocks();
    mockGetRecent.mockReturnValue([]);
  });

  it('renders the open project form', () => {
    render(<WorkspaceSelector onSelectWorkspace={onSelect} isLoading={false} error={null} />);
    expect(screen.getByLabelText(/repository path/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /open project/i })).toBeInTheDocument();
  });

  it('calls onSelectWorkspace with trimmed path on submit', async () => {
    render(<WorkspaceSelector onSelectWorkspace={onSelect} isLoading={false} error={null} />);
    fireEvent.change(screen.getByLabelText(/repository path/i), {
      target: { value: '  /home/user/my-app  ' },
    });
    fireEvent.click(screen.getByRole('button', { name: /open project/i }));
    await waitFor(() => expect(onSelect).toHaveBeenCalledWith('/home/user/my-app'));
  });

  it('does not submit when path is empty', () => {
    render(<WorkspaceSelector onSelectWorkspace={onSelect} isLoading={false} error={null} />);
    fireEvent.click(screen.getByRole('button', { name: /open project/i }));
    expect(onSelect).not.toHaveBeenCalled();
  });

  it('shows error message when error prop is set', () => {
    render(
      <WorkspaceSelector onSelectWorkspace={onSelect} isLoading={false} error="Path not found" />
    );
    expect(screen.getByText('Path not found')).toBeInTheDocument();
  });

  it('shows loading spinner and disables button while loading', () => {
    render(<WorkspaceSelector onSelectWorkspace={onSelect} isLoading={true} error={null} />);
    expect(screen.getByRole('button', { name: /opening/i })).toBeDisabled();
  });

  describe('Recent Projects section', () => {
    it('always renders the Recent Projects card', () => {
      mockGetRecent.mockReturnValue([]);
      render(<WorkspaceSelector onSelectWorkspace={onSelect} isLoading={false} error={null} />);
      expect(screen.getByText('Recent Projects')).toBeInTheDocument();
    });

    it('shows empty state message when no recent workspaces', () => {
      mockGetRecent.mockReturnValue([]);
      render(<WorkspaceSelector onSelectWorkspace={onSelect} isLoading={false} error={null} />);
      expect(screen.getByText(/no recent projects/i)).toBeInTheDocument();
    });

    it('renders recent workspace names and paths', () => {
      mockGetRecent.mockReturnValue(RECENT);
      render(<WorkspaceSelector onSelectWorkspace={onSelect} isLoading={false} error={null} />);
      expect(screen.getByText('project-b')).toBeInTheDocument();
      expect(screen.getByText('/home/user/project-b')).toBeInTheDocument();
      expect(screen.getByText('project-a')).toBeInTheDocument();
    });

    it('calls onSelectWorkspace when a recent workspace is clicked', async () => {
      mockGetRecent.mockReturnValue(RECENT);
      render(<WorkspaceSelector onSelectWorkspace={onSelect} isLoading={false} error={null} />);
      fireEvent.click(screen.getByText('project-b').closest('[role="button"]')!);
      await waitFor(() => expect(onSelect).toHaveBeenCalledWith('/home/user/project-b'));
    });

    it('calls removeFromRecentWorkspaces when remove button is clicked', () => {
      mockGetRecent.mockReturnValue(RECENT);
      render(<WorkspaceSelector onSelectWorkspace={onSelect} isLoading={false} error={null} />);
      const removeBtn = screen.getByRole('button', { name: /remove project-b/i });
      fireEvent.click(removeBtn);
      expect(mockRemove).toHaveBeenCalledWith('/home/user/project-b');
    });

    it('does not trigger workspace open when remove button is clicked', () => {
      mockGetRecent.mockReturnValue(RECENT);
      render(<WorkspaceSelector onSelectWorkspace={onSelect} isLoading={false} error={null} />);
      const removeBtn = screen.getByRole('button', { name: /remove project-b/i });
      fireEvent.click(removeBtn);
      expect(onSelect).not.toHaveBeenCalled();
    });

    it('recent items are not clickable while loading', () => {
      mockGetRecent.mockReturnValue(RECENT);
      render(<WorkspaceSelector onSelectWorkspace={onSelect} isLoading={true} error={null} />);
      fireEvent.click(screen.getByText('project-b').closest('[role="button"]')!);
      expect(onSelect).not.toHaveBeenCalled();
    });
  });
});
