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
    startProject: jest.fn(),
  },
}));

// Mock ProjectCreationForm component
jest.mock('@/components/ProjectCreationForm', () => {
  return function MockProjectCreationForm({
    onSuccess,
    onSubmit,
  }: {
    onSuccess: (projectId: number) => void;
    onSubmit?: () => void;
    onError?: () => void;
  }) {
    return (
      <div data-testid="project-creation-form">
        <button
          onClick={() => {
            onSubmit?.();
            // Simulate async success after a brief delay
            setTimeout(() => onSuccess(3), 50);
          }}
        >
          Submit Form
        </button>
      </div>
    );
  };
});

// Mock Spinner component
jest.mock('@/components/Spinner', () => ({
  Spinner: ({ size }: { size: string }) => (
    <div data-testid="spinner" data-size={size}>Loading...</div>
  ),
}));

// Mock Hugeicons
jest.mock('@hugeicons/react', () => ({
  Add01Icon: ({ className }: { className?: string }) => (
    <svg data-testid="add-icon" className={className} />
  ),
}));

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
    (projectsApi.startProject as jest.Mock).mockResolvedValue({});
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
      expect(screen.getByText(/No projects yet/i)).toBeInTheDocument();
    });

    // Also check for the CTA text
    expect(screen.getByText(/Create your first project/i)).toBeInTheDocument();
  });

  test('shows "Create New Project" button', async () => {
    (projectsApi.list as jest.Mock).mockResolvedValue({
      data: { projects: [] },
    });

    renderWithSWR(<ProjectList />);

    await waitFor(() => {
      expect(screen.getByTestId('create-project-button')).toBeInTheDocument();
    });
  });

  test('shows ProjectCreationForm when Create button is clicked', async () => {
    (projectsApi.list as jest.Mock).mockResolvedValue({
      data: { projects: [] },
    });

    renderWithSWR(<ProjectList />);

    await waitFor(() => {
      expect(screen.getByTestId('create-project-button')).toBeInTheDocument();
    });

    const createButton = screen.getByTestId('create-project-button');
    await userEvent.click(createButton);

    expect(screen.getByTestId('project-creation-form')).toBeInTheDocument();
  });

  test('navigates to project dashboard after creation', async () => {
    (projectsApi.list as jest.Mock).mockResolvedValue({
      data: { projects: [] },
    });

    renderWithSWR(<ProjectList />);

    await waitFor(() => {
      expect(screen.getByTestId('create-project-button')).toBeInTheDocument();
    });

    // Show form
    const createButton = screen.getByTestId('create-project-button');
    await userEvent.click(createButton);

    expect(screen.getByTestId('project-creation-form')).toBeInTheDocument();

    // Submit form
    const submitButton = screen.getByText('Submit Form');
    await userEvent.click(submitButton);

    // Should navigate to project dashboard
    await waitFor(() => {
      expect(mockPush).toHaveBeenCalledWith('/projects/3');
    });
  });

  test('starts discovery after project creation', async () => {
    (projectsApi.list as jest.Mock).mockResolvedValue({
      data: { projects: [] },
    });

    renderWithSWR(<ProjectList />);

    await waitFor(() => {
      expect(screen.getByTestId('create-project-button')).toBeInTheDocument();
    });

    // Show form and submit
    const createButton = screen.getByTestId('create-project-button');
    await userEvent.click(createButton);

    const submitButton = screen.getByText('Submit Form');
    await userEvent.click(submitButton);

    // Should call startProject
    await waitFor(() => {
      expect(projectsApi.startProject).toHaveBeenCalledWith(3);
    });
  });

  test('shows error state if fetch fails', async () => {
    const consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation();

    (projectsApi.list as jest.Mock).mockRejectedValue(
      new Error('Failed to fetch projects')
    );

    renderWithSWR(<ProjectList />);

    await waitFor(() => {
      expect(
        screen.getByText(/Failed to load projects/i)
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
