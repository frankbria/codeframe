import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useRouter } from 'next/navigation';
import ProjectCreationForm from '../ProjectCreationForm';

// Create mock functions
const mockPost = jest.fn();

// Mock axios
jest.mock('axios', () => {
  const mockAxiosInstance = {
    get: jest.fn(),
    post: (...args: any[]) => mockPost(...args),
    put: jest.fn(),
    delete: jest.fn(),
    patch: jest.fn(),
  };

  return {
    __esModule: true,
    default: {
      create: jest.fn(() => mockAxiosInstance),
    },
  };
});

// Mock Next.js router
const mockPush = jest.fn();
jest.mock('next/navigation', () => ({
  useRouter: jest.fn(),
}));

// Import after mocks are set up
import { projectsApi } from '@/lib/api';

describe('ProjectCreationForm', () => {
  beforeEach(() => {
    mockPost.mockReset();
    mockPush.mockClear();
    (useRouter as jest.Mock).mockReturnValue({
      push: mockPush,
    });
  });

  test('renders form with name input and type select dropdown', () => {
    render(<ProjectCreationForm />);

    expect(screen.getByLabelText(/project name/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/project type/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /create project/i })).toBeInTheDocument();
  });

  test('defaults project type to python', () => {
    render(<ProjectCreationForm />);

    const selectElement = screen.getByLabelText(/project type/i) as HTMLSelectElement;
    expect(selectElement.value).toBe('python');
  });

  test('shows all project type options', () => {
    render(<ProjectCreationForm />);

    const selectElement = screen.getByLabelText(/project type/i);
    const options = Array.from(selectElement.querySelectorAll('option')).map(opt => opt.value);

    expect(options).toEqual(['python', 'javascript', 'typescript', 'java', 'go', 'rust']);
  });

  test('shows validation error when submitting with empty name', async () => {
    const user = userEvent.setup();
    render(<ProjectCreationForm />);

    const submitButton = screen.getByRole('button', { name: /create project/i });
    await user.click(submitButton);

    expect(await screen.findByText(/project name cannot be empty/i)).toBeInTheDocument();
  });

  test('calls createProject with correct data on valid submit', async () => {
    const user = userEvent.setup();

    mockPost.mockResolvedValueOnce({
      status: 201,
      data: {
        id: 1,
        name: 'Test Project',
        project_type: 'typescript',
        status: 'init',
        phase: 'discovery',
        created_at: '2025-01-15T10:00:00Z',
      },
    });

    render(<ProjectCreationForm />);

    const nameInput = screen.getByLabelText(/project name/i);
    const typeSelect = screen.getByLabelText(/project type/i);

    await user.type(nameInput, 'Test Project');
    await user.selectOptions(typeSelect, 'typescript');

    const submitButton = screen.getByRole('button', { name: /create project/i });
    await user.click(submitButton);

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith('/api/projects', {
        project_name: 'Test Project',
        project_type: 'typescript',
      });
    });

    expect(await screen.findByText(/project created successfully/i)).toBeInTheDocument();
  });

  test('shows loading state (disabled submit button) while submitting', async () => {
    const user = userEvent.setup();

    // Create a delayed resolution
    let resolvePost: any;
    const postPromise = new Promise((resolve) => {
      resolvePost = resolve;
    });
    mockPost.mockReturnValueOnce(postPromise);

    render(<ProjectCreationForm />);

    const nameInput = screen.getByLabelText(/project name/i);
    await user.type(nameInput, 'Test Project');

    const submitButton = screen.getByRole('button', { name: /create project/i });
    await user.click(submitButton);

    // Button should be disabled during submission
    expect(submitButton).toBeDisabled();

    // Resolve the promise and wait for state update
    resolvePost({
      status: 201,
      data: {
        id: 1,
        name: 'Test Project',
        status: 'init',
        phase: 'discovery',
        created_at: '2025-01-15T10:00:00Z',
      },
    });

    // Wait for the form to process the response
    await waitFor(() => {
      expect(screen.getByText(/project created successfully/i)).toBeInTheDocument();
    });
  });

  test('shows error message on 400 Bad Request', async () => {
    const user = userEvent.setup();

    mockPost.mockRejectedValueOnce({
      response: {
        status: 400,
        data: { detail: 'Project name cannot be empty' },
      },
    });

    render(<ProjectCreationForm />);

    const nameInput = screen.getByLabelText(/project name/i);
    await user.type(nameInput, 'Test');
    await user.clear(nameInput);

    const submitButton = screen.getByRole('button', { name: /create project/i });
    await user.click(submitButton);

    expect(await screen.findByText(/project name cannot be empty/i)).toBeInTheDocument();
  });

  test('shows error message on 409 Conflict', async () => {
    const user = userEvent.setup();

    mockPost.mockRejectedValueOnce({
      response: {
        status: 409,
        data: { detail: 'Project with this name already exists' },
      },
    });

    render(<ProjectCreationForm />);

    const nameInput = screen.getByLabelText(/project name/i);
    await user.type(nameInput, 'duplicate-project');

    const submitButton = screen.getByRole('button', { name: /create project/i });
    await user.click(submitButton);

    expect(await screen.findByText(/project with this name already exists/i)).toBeInTheDocument();
  });

  test('shows error message on 500 Internal Server Error', async () => {
    const user = userEvent.setup();

    mockPost.mockRejectedValueOnce({
      response: {
        status: 500,
        data: { detail: 'Internal server error' },
      },
    });

    render(<ProjectCreationForm />);

    const nameInput = screen.getByLabelText(/project name/i);
    await user.type(nameInput, 'server-error');

    const submitButton = screen.getByRole('button', { name: /create project/i });
    await user.click(submitButton);

    expect(await screen.findByText(/internal server error/i)).toBeInTheDocument();
  });

  test('shows success state with created project details', async () => {
    const user = userEvent.setup();

    mockPost.mockResolvedValueOnce({
      status: 201,
      data: {
        id: 1,
        name: 'My New Project',
        status: 'init',
        phase: 'discovery',
        created_at: '2025-01-15T10:00:00Z',
      },
    });

    render(<ProjectCreationForm />);

    const nameInput = screen.getByLabelText(/project name/i);
    await user.type(nameInput, 'My New Project');

    const submitButton = screen.getByRole('button', { name: /create project/i });
    await user.click(submitButton);

    await waitFor(() => {
      expect(screen.getByText(/project created successfully/i)).toBeInTheDocument();
      expect(screen.getByText(/my new project/i)).toBeInTheDocument();
    });
  });

  test('shows Start Project button after successful creation', async () => {
    const user = userEvent.setup();

    mockPost.mockResolvedValueOnce({
      status: 201,
      data: {
        id: 1,
        name: 'Test Project',
        status: 'init',
        phase: 'discovery',
        created_at: '2025-01-15T10:00:00Z',
      },
    });

    render(<ProjectCreationForm />);

    const nameInput = screen.getByLabelText(/project name/i);
    await user.type(nameInput, 'Test Project');

    const submitButton = screen.getByRole('button', { name: /create project/i });
    await user.click(submitButton);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /start project/i })).toBeInTheDocument();
    });
  });

  test('calls startProject when Start button is clicked', async () => {
    const user = userEvent.setup();

    // Mock create project response
    mockPost.mockResolvedValueOnce({
      status: 201,
      data: {
        id: 1,
        name: 'Test Project',
        status: 'init',
        phase: 'discovery',
        created_at: '2025-01-15T10:00:00Z',
      },
    });

    render(<ProjectCreationForm />);

    // Create project first
    const nameInput = screen.getByLabelText(/project name/i);
    await user.type(nameInput, 'Test Project');

    const createButton = screen.getByRole('button', { name: /create project/i });
    await user.click(createButton);

    // Wait for Start Project button to appear
    const startButton = await screen.findByRole('button', { name: /start project/i });

    // Mock start project response
    mockPost.mockResolvedValueOnce({
      status: 202,
      data: {
        message: 'Starting Lead Agent for project 1',
        status: 'starting',
      },
    });

    await user.click(startButton);

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith('/api/projects/1/start');
    });
  });

  test('navigates to project page after starting project', async () => {
    const user = userEvent.setup();

    // Mock create project response
    mockPost.mockResolvedValueOnce({
      status: 201,
      data: {
        id: 1,
        name: 'Test Project',
        status: 'init',
        phase: 'discovery',
        created_at: '2025-01-15T10:00:00Z',
      },
    });

    render(<ProjectCreationForm />);

    // Create project
    const nameInput = screen.getByLabelText(/project name/i);
    await user.type(nameInput, 'Test Project');

    const createButton = screen.getByRole('button', { name: /create project/i });
    await user.click(createButton);

    // Start project
    const startButton = await screen.findByRole('button', { name: /start project/i });

    // Mock start project response
    mockPost.mockResolvedValueOnce({
      status: 202,
      data: {
        message: 'Starting Lead Agent for project 1',
        status: 'starting',
      },
    });

    await user.click(startButton);

    // Should navigate to project page
    await waitFor(() => {
      expect(mockPush).toHaveBeenCalledWith('/projects/1');
    });
  });

  test('shows loading state while starting project', async () => {
    const user = userEvent.setup();

    // Mock create project response
    mockPost.mockResolvedValueOnce({
      status: 201,
      data: {
        id: 1,
        name: 'Test Project',
        status: 'init',
        phase: 'discovery',
        created_at: '2025-01-15T10:00:00Z',
      },
    });

    render(<ProjectCreationForm />);

    // Create project
    const nameInput = screen.getByLabelText(/project name/i);
    await user.type(nameInput, 'Test Project');

    const createButton = screen.getByRole('button', { name: /create project/i });
    await user.click(createButton);

    // Start project
    const startButton = await screen.findByRole('button', { name: /start project/i });

    // Create a promise we can control for start project
    let resolveStart: any;
    const startPromise = new Promise((resolve) => {
      resolveStart = resolve;
    });
    mockPost.mockReturnValueOnce(startPromise);

    await user.click(startButton);

    // Button should be disabled while starting
    expect(startButton).toBeDisabled();

    // Resolve the promise
    resolveStart({
      status: 202,
      data: {
        message: 'Starting Lead Agent for project 1',
        status: 'starting',
      },
    });

    // Should navigate after completion
    await waitFor(() => {
      expect(mockPush).toHaveBeenCalledWith('/projects/1');
    });
  });
});
