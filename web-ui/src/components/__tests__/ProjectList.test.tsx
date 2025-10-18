import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SWRConfig } from 'swr';
import { useRouter } from 'next/navigation';
import ProjectList from '@/components/ProjectList';
import { projectsApi } from '@/lib/api';

// Mock Next.js router
jest.mock('next/navigation', () => ({
  useRouter: jest.fn(),
}));

// Mock projectsApi
jest.mock('@/lib/api', () => ({
  projectsApi: {
    list: jest.fn(),
  },
}));

// Mock ProjectCreationForm component
jest.mock('@/components/ProjectCreationForm', () => {
  return function MockProjectCreationForm({ onSuccess }: { onSuccess: (project: any) => void }) {
    return (
      <div data-testid="project-creation-form">
        <button
          onClick={() =>
            onSuccess({
              id: 3,
              name: 'New Project',
              status: 'init',
              phase: 'discovery',
              created_at: '2025-01-16T10:00:00Z',
            })
          }
        >
          Submit Form
        </button>
      </div>
    );
  };
});

// Helper to render with SWR wrapper
const renderWithSWR = (component: React.ReactElement) => {
  return render(
    <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>
      {component}
    </SWRConfig>
  );
};

describe('ProjectList', () => {
  const mockPush = jest.fn();

  beforeEach(() => {
    jest.clearAllMocks();
    (useRouter as jest.Mock).mockReturnValue({
      push: mockPush,
    });
  });

  test('shows loading state while fetching projects', () => {
    (projectsApi.list as jest.Mock).mockImplementation(
      () => new Promise(() => {}) // Never resolves
    );

    renderWithSWR(<ProjectList />);

    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  test('renders project cards with correct data (name, status, phase, date)', async () => {
    const mockProjects = [
      {
        id: 1,
        name: 'Project A',
        status: 'init',
        phase: 'discovery',
        created_at: '2025-01-15T10:00:00Z',
      },
      {
        id: 2,
        name: 'Project B',
        status: 'running',
        phase: 'planning',
        created_at: '2025-01-14T09:00:00Z',
      },
    ];

    (projectsApi.list as jest.Mock).mockResolvedValue({
      data: { projects: mockProjects },
    });

    renderWithSWR(<ProjectList />);

    await waitFor(() => {
      expect(screen.getByText('Project A')).toBeInTheDocument();
    });

    expect(screen.getByText('Project B')).toBeInTheDocument();
    // Check for status and phase values (text is split across elements)
    const allText = screen.getByText('Project A').closest('div')!.textContent;
    expect(allText).toContain('Status:');
    expect(allText).toContain('init');
    expect(allText).toContain('Phase:');
    expect(allText).toContain('discovery');

    const projectBText = screen.getByText('Project B').closest('div')!.textContent;
    expect(projectBText).toContain('running');
    expect(projectBText).toContain('planning');
  });

  test('navigates to project page when card is clicked', async () => {
    const mockProjects = [
      {
        id: 1,
        name: 'Project A',
        status: 'init',
        phase: 'discovery',
        created_at: '2025-01-15T10:00:00Z',
      },
    ];

    (projectsApi.list as jest.Mock).mockResolvedValue({
      data: { projects: mockProjects },
    });

    renderWithSWR(<ProjectList />);

    await waitFor(() => {
      expect(screen.getByText('Project A')).toBeInTheDocument();
    });

    const projectCard = screen.getByText('Project A').closest('div');
    await userEvent.click(projectCard!);

    expect(mockPush).toHaveBeenCalledWith('/projects/1');
  });

  test('shows empty state when no projects exist', async () => {
    (projectsApi.list as jest.Mock).mockResolvedValue({
      data: { projects: [] },
    });

    renderWithSWR(<ProjectList />);

    await waitFor(() => {
      expect(
        screen.getByText(/No projects yet. Create your first project!/i)
      ).toBeInTheDocument();
    });
  });

  test('shows "Create New Project" button', async () => {
    (projectsApi.list as jest.Mock).mockResolvedValue({
      data: { projects: [] },
    });

    renderWithSWR(<ProjectList />);

    await waitFor(() => {
      expect(screen.getByText(/Create New Project/i)).toBeInTheDocument();
    });
  });

  test('shows ProjectCreationForm when Create button is clicked', async () => {
    (projectsApi.list as jest.Mock).mockResolvedValue({
      data: { projects: [] },
    });

    renderWithSWR(<ProjectList />);

    await waitFor(() => {
      expect(screen.getByText(/Create New Project/i)).toBeInTheDocument();
    });

    const createButton = screen.getByText(/Create New Project/i);
    await userEvent.click(createButton);

    expect(screen.getByTestId('project-creation-form')).toBeInTheDocument();
  });

  test('hides form after project is created', async () => {
    (projectsApi.list as jest.Mock).mockResolvedValue({
      data: { projects: [] },
    });

    renderWithSWR(<ProjectList />);

    await waitFor(() => {
      expect(screen.getByText(/Create New Project/i)).toBeInTheDocument();
    });

    // Show form
    const createButton = screen.getByText(/Create New Project/i);
    await userEvent.click(createButton);

    expect(screen.getByTestId('project-creation-form')).toBeInTheDocument();

    // Submit form
    const submitButton = screen.getByText('Submit Form');
    await userEvent.click(submitButton);

    // Form should be hidden
    expect(screen.queryByTestId('project-creation-form')).not.toBeInTheDocument();
  });

  test('refreshes project list after creating new project', async () => {
    const initialProjects = [
      {
        id: 1,
        name: 'Existing Project',
        status: 'init',
        phase: 'discovery',
        created_at: '2025-01-15T10:00:00Z',
      },
    ];

    const updatedProjects = [
      ...initialProjects,
      {
        id: 3,
        name: 'New Project',
        status: 'init',
        phase: 'discovery',
        created_at: '2025-01-16T10:00:00Z',
      },
    ];

    // First call returns initial projects
    (projectsApi.list as jest.Mock)
      .mockResolvedValueOnce({ data: { projects: initialProjects } })
      .mockResolvedValueOnce({ data: { projects: updatedProjects } });

    renderWithSWR(<ProjectList />);

    await waitFor(() => {
      expect(screen.getByText('Existing Project')).toBeInTheDocument();
    });

    // Show form and submit
    const createButton = screen.getByText(/Create New Project/i);
    await userEvent.click(createButton);

    const submitButton = screen.getByText('Submit Form');
    await userEvent.click(submitButton);

    // Wait for the list to refresh
    await waitFor(() => {
      expect(screen.getByText('New Project')).toBeInTheDocument();
    });

    // Verify list was refreshed (second call to projectsApi.list)
    expect(projectsApi.list).toHaveBeenCalledTimes(2);
  });

  test('shows error state if fetch fails', async () => {
    const consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation();

    (projectsApi.list as jest.Mock).mockRejectedValue(
      new Error('Failed to fetch projects')
    );

    renderWithSWR(<ProjectList />);

    await waitFor(() => {
      expect(
        screen.getByText(/Failed to load projects. Please try again./i)
      ).toBeInTheDocument();
    });

    consoleErrorSpy.mockRestore();
  });

  test('formats created_at date in readable format', async () => {
    const mockProjects = [
      {
        id: 1,
        name: 'Project A',
        status: 'init',
        phase: 'discovery',
        created_at: '2025-01-15T10:00:00Z',
      },
    ];

    (projectsApi.list as jest.Mock).mockResolvedValue({
      data: { projects: mockProjects },
    });

    renderWithSWR(<ProjectList />);

    await waitFor(() => {
      expect(screen.getByText(/January 15, 2025/)).toBeInTheDocument();
    });
  });
});
