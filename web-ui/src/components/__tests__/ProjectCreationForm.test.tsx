/**
 * Tests for ProjectCreationForm Component
 * Feature: 011-project-creation-flow
 * Sprint: 9.5 - Critical UX Fixes
 */

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ProjectCreationForm from '../ProjectCreationForm';

// Create mock functions
const mockPost = jest.fn();

// Mock axios
jest.mock('axios', () => {
  const mockAxiosInstance = {
    get: jest.fn(),
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
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

describe('ProjectCreationForm', () => {
  const mockOnSuccess = jest.fn();
  const mockOnSubmit = jest.fn();
  const mockOnError = jest.fn();

  beforeEach(() => {
    mockPost.mockReset();
    mockOnSuccess.mockClear();
    mockOnSubmit.mockClear();
    mockOnError.mockClear();
  });

  describe('Basic Rendering', () => {
    test('renders form with all required fields', () => {
      render(<ProjectCreationForm onSuccess={mockOnSuccess} />);

      expect(screen.getByLabelText(/project name/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/description/i)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /create project & start discovery/i })).toBeInTheDocument();
    });

    test('shows character counter for description', () => {
      render(<ProjectCreationForm onSuccess={mockOnSuccess} />);

      expect(screen.getByText(/0 \/ 500 characters \(min 10\)/i)).toBeInTheDocument();
    });

    test('shows hint text below submit button', () => {
      render(<ProjectCreationForm onSuccess={mockOnSuccess} />);

      expect(screen.getByText(/after creation, you'll begin socratic discovery/i)).toBeInTheDocument();
    });
  });

  describe('Validation - Project Name', () => {
    test('shows error when name is empty on blur', async () => {
      const user = userEvent.setup();
      render(<ProjectCreationForm onSuccess={mockOnSuccess} />);

      const nameInput = screen.getByLabelText(/project name/i);
      await user.click(nameInput);
      await user.tab(); // Blur

      expect(await screen.findByText(/project name is required/i)).toBeInTheDocument();
    });

    test('shows error when name is too short on blur', async () => {
      const user = userEvent.setup();
      render(<ProjectCreationForm onSuccess={mockOnSuccess} />);

      const nameInput = screen.getByLabelText(/project name/i);
      await user.type(nameInput, 'ab');
      await user.tab(); // Blur

      expect(await screen.findByText(/project name must be at least 3 characters/i)).toBeInTheDocument();
    });

    test('shows error when name has invalid characters on blur', async () => {
      const user = userEvent.setup();
      render(<ProjectCreationForm onSuccess={mockOnSuccess} />);

      const nameInput = screen.getByLabelText(/project name/i);
      await user.type(nameInput, 'My Project!');
      await user.tab(); // Blur

      expect(await screen.findByText(/only lowercase letters, numbers, hyphens, and underscores allowed/i)).toBeInTheDocument();
    });

    test('shows error when name has uppercase letters', async () => {
      const user = userEvent.setup();
      render(<ProjectCreationForm onSuccess={mockOnSuccess} />);

      const nameInput = screen.getByLabelText(/project name/i);
      await user.type(nameInput, 'MyProject');
      await user.tab(); // Blur

      expect(await screen.findByText(/only lowercase letters, numbers, hyphens, and underscores allowed/i)).toBeInTheDocument();
    });

    test('accepts valid name with lowercase, numbers, hyphens, underscores', async () => {
      const user = userEvent.setup();
      render(<ProjectCreationForm onSuccess={mockOnSuccess} />);

      const nameInput = screen.getByLabelText(/project name/i);
      await user.type(nameInput, 'my-project_123');
      await user.tab(); // Blur

      expect(screen.queryByText(/project name/i, { selector: '.text-red-600' })).not.toBeInTheDocument();
    });

    test('shows red border on name field when error exists', async () => {
      const user = userEvent.setup();
      render(<ProjectCreationForm onSuccess={mockOnSuccess} />);

      const nameInput = screen.getByLabelText(/project name/i);
      await user.type(nameInput, 'AB');
      await user.tab();

      await waitFor(() => {
        expect(nameInput).toHaveClass('border-red-500');
      });
    });
  });

  describe('Validation - Description', () => {
    test('shows error when description is empty on blur', async () => {
      const user = userEvent.setup();
      render(<ProjectCreationForm onSuccess={mockOnSuccess} />);

      const descInput = screen.getByLabelText(/description/i);
      await user.click(descInput);
      await user.tab(); // Blur

      expect(await screen.findByText(/project description is required/i)).toBeInTheDocument();
    });

    test('shows error when description is too short on blur', async () => {
      const user = userEvent.setup();
      render(<ProjectCreationForm onSuccess={mockOnSuccess} />);

      const descInput = screen.getByLabelText(/description/i);
      await user.type(descInput, 'Short');
      await user.tab(); // Blur

      expect(await screen.findByText(/description must be at least 10 characters/i)).toBeInTheDocument();
    });

    test('updates character counter as user types', async () => {
      const user = userEvent.setup();
      render(<ProjectCreationForm onSuccess={mockOnSuccess} />);

      const descInput = screen.getByLabelText(/description/i);
      await user.type(descInput, 'Test description');

      expect(screen.getByText(/16 \/ 500 characters/i)).toBeInTheDocument();
    });

    test('shows red border on description field when error exists', async () => {
      const user = userEvent.setup();
      render(<ProjectCreationForm onSuccess={mockOnSuccess} />);

      const descInput = screen.getByLabelText(/description/i);
      await user.type(descInput, 'Short');
      await user.tab();

      await waitFor(() => {
        expect(descInput).toHaveClass('border-red-500');
      });
    });
  });

  describe('Submit Button State', () => {
    test('submit button is disabled when form is invalid', () => {
      render(<ProjectCreationForm onSuccess={mockOnSuccess} />);

      const submitButton = screen.getByRole('button', { name: /create project & start discovery/i });
      expect(submitButton).toBeDisabled();
    });

    test('submit button is enabled when form is valid', async () => {
      const user = userEvent.setup();
      render(<ProjectCreationForm onSuccess={mockOnSuccess} />);

      const nameInput = screen.getByLabelText(/project name/i);
      const descInput = screen.getByLabelText(/description/i);

      await user.type(nameInput, 'my-project');
      await user.type(descInput, 'This is a valid description');

      await waitFor(() => {
        const submitButton = screen.getByRole('button', { name: /create project & start discovery/i });
        expect(submitButton).not.toBeDisabled();
      });
    });

    test('submit button is disabled during submission', async () => {
      const user = userEvent.setup();

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      let resolvePost: any;
      const postPromise = new Promise((resolve) => {
        resolvePost = resolve;
      });
      mockPost.mockReturnValueOnce(postPromise);

      render(<ProjectCreationForm onSuccess={mockOnSuccess} />);

      const nameInput = screen.getByLabelText(/project name/i);
      const descInput = screen.getByLabelText(/description/i);

      await user.type(nameInput, 'my-project');
      await user.type(descInput, 'This is a valid description');

      const submitButton = screen.getByRole('button', { name: /create project & start discovery/i });
      await user.click(submitButton);

      expect(submitButton).toBeDisabled();
      expect(submitButton).toHaveTextContent(/creating/i);

      // Resolve the promise
      resolvePost({
        status: 201,
        data: {
          id: 1,
          name: 'my-project',
          status: 'init',
          phase: 'discovery',
          created_at: '2025-01-15T10:00:00Z',
        },
      });
    });

    test('all inputs are disabled during submission', async () => {
      const user = userEvent.setup();

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      let resolvePost: any;
      const postPromise = new Promise((resolve) => {
        resolvePost = resolve;
      });
      mockPost.mockReturnValueOnce(postPromise);

      render(<ProjectCreationForm onSuccess={mockOnSuccess} />);

      const nameInput = screen.getByLabelText(/project name/i);
      const descInput = screen.getByLabelText(/description/i);

      await user.type(nameInput, 'my-project');
      await user.type(descInput, 'This is a valid description');

      const submitButton = screen.getByRole('button', { name: /create project & start discovery/i });
      await user.click(submitButton);

      expect(nameInput).toBeDisabled();
      expect(descInput).toBeDisabled();

      // Resolve the promise
      resolvePost({
        status: 201,
        data: {
          id: 1,
          name: 'my-project',
          status: 'init',
          phase: 'discovery',
          created_at: '2025-01-15T10:00:00Z',
        },
      });
    });
  });

  describe('Form Submission', () => {
    test('calls API with correct data on valid submit', async () => {
      const user = userEvent.setup();

      mockPost.mockResolvedValueOnce({
        status: 201,
        data: {
          id: 1,
          name: 'test-project',
          status: 'init',
          phase: 'discovery',
          created_at: '2025-01-15T10:00:00Z',
        },
      });

      render(<ProjectCreationForm onSuccess={mockOnSuccess} />);

      const nameInput = screen.getByLabelText(/project name/i);
      const descInput = screen.getByLabelText(/description/i);

      await user.type(nameInput, 'test-project');
      await user.type(descInput, 'This is a test project description');

      const submitButton = screen.getByRole('button', { name: /create project & start discovery/i });
      await user.click(submitButton);

      await waitFor(() => {
        expect(mockPost).toHaveBeenCalledWith('/api/projects', {
          name: 'test-project',
          description: 'This is a test project description',
          source_type: 'empty',
        });
      });
    });

    test('calls onSubmit callback before API request', async () => {
      const user = userEvent.setup();

      mockPost.mockResolvedValueOnce({
        status: 201,
        data: {
          id: 1,
          name: 'test-project',
          status: 'init',
          phase: 'discovery',
          created_at: '2025-01-15T10:00:00Z',
        },
      });

      render(<ProjectCreationForm onSuccess={mockOnSuccess} onSubmit={mockOnSubmit} />);

      const nameInput = screen.getByLabelText(/project name/i);
      const descInput = screen.getByLabelText(/description/i);

      await user.type(nameInput, 'test-project');
      await user.type(descInput, 'This is a test project description');

      const submitButton = screen.getByRole('button', { name: /create project & start discovery/i });
      await user.click(submitButton);

      await waitFor(() => {
        expect(mockOnSubmit).toHaveBeenCalled();
      });
    });

    test('calls onSuccess with project ID on successful creation', async () => {
      const user = userEvent.setup();

      mockPost.mockResolvedValueOnce({
        status: 201,
        data: {
          id: 42,
          name: 'test-project',
          status: 'init',
          phase: 'discovery',
          created_at: '2025-01-15T10:00:00Z',
        },
      });

      render(<ProjectCreationForm onSuccess={mockOnSuccess} />);

      const nameInput = screen.getByLabelText(/project name/i);
      const descInput = screen.getByLabelText(/description/i);

      await user.type(nameInput, 'test-project');
      await user.type(descInput, 'This is a test project description');

      const submitButton = screen.getByRole('button', { name: /create project & start discovery/i });
      await user.click(submitButton);

      await waitFor(() => {
        expect(mockOnSuccess).toHaveBeenCalledWith(42);
      });
    });

    test('does not submit if name validation fails', async () => {
      const user = userEvent.setup();

      render(<ProjectCreationForm onSuccess={mockOnSuccess} />);

      const nameInput = screen.getByLabelText(/project name/i);
      const descInput = screen.getByLabelText(/description/i);

      await user.type(nameInput, 'ab'); // Too short
      await user.type(descInput, 'This is a valid description');

      const submitButton = screen.getByRole('button', { name: /create project & start discovery/i });
      await user.click(submitButton);

      expect(mockPost).not.toHaveBeenCalled();
    });

    test('does not submit if description validation fails', async () => {
      const user = userEvent.setup();

      render(<ProjectCreationForm onSuccess={mockOnSuccess} />);

      const nameInput = screen.getByLabelText(/project name/i);
      const descInput = screen.getByLabelText(/description/i);

      await user.type(nameInput, 'test-project');
      await user.type(descInput, 'Short'); // Too short

      const submitButton = screen.getByRole('button', { name: /create project & start discovery/i });
      await user.click(submitButton);

      expect(mockPost).not.toHaveBeenCalled();
    });
  });

  describe('Error Handling', () => {
    test('shows error for duplicate project name (409)', async () => {
      const user = userEvent.setup();

      mockPost.mockRejectedValueOnce({
        response: {
          status: 409,
          data: { detail: "Project with name 'test-project' already exists" },
        },
      });

      render(<ProjectCreationForm onSuccess={mockOnSuccess} onError={mockOnError} />);

      const nameInput = screen.getByLabelText(/project name/i);
      const descInput = screen.getByLabelText(/description/i);

      await user.type(nameInput, 'test-project');
      await user.type(descInput, 'This is a test project description');

      const submitButton = screen.getByRole('button', { name: /create project & start discovery/i });
      await user.click(submitButton);

      expect(await screen.findByText(/project 'test-project' already exists/i)).toBeInTheDocument();
      expect(mockOnError).toHaveBeenCalled();
    });

    test('shows error for validation error (400)', async () => {
      const user = userEvent.setup();

      mockPost.mockRejectedValueOnce({
        response: {
          status: 400,
          data: { detail: 'Invalid project name format' },
        },
      });

      render(<ProjectCreationForm onSuccess={mockOnSuccess} onError={mockOnError} />);

      const nameInput = screen.getByLabelText(/project name/i);
      const descInput = screen.getByLabelText(/description/i);

      await user.type(nameInput, 'test-project');
      await user.type(descInput, 'This is a test project description');

      const submitButton = screen.getByRole('button', { name: /create project & start discovery/i });
      await user.click(submitButton);

      expect(await screen.findByText(/invalid project name format/i)).toBeInTheDocument();
      expect(mockOnError).toHaveBeenCalled();
    });

    test('shows error for server error (500)', async () => {
      const user = userEvent.setup();

      mockPost.mockRejectedValueOnce({
        response: {
          status: 500,
          data: { detail: 'Internal server error' },
        },
      });

      render(<ProjectCreationForm onSuccess={mockOnSuccess} onError={mockOnError} />);

      const nameInput = screen.getByLabelText(/project name/i);
      const descInput = screen.getByLabelText(/description/i);

      await user.type(nameInput, 'test-project');
      await user.type(descInput, 'This is a test project description');

      const submitButton = screen.getByRole('button', { name: /create project & start discovery/i });
      await user.click(submitButton);

      expect(await screen.findByText(/server error occurred/i)).toBeInTheDocument();
      expect(mockOnError).toHaveBeenCalled();
    });

    test('shows error for network failure', async () => {
      const user = userEvent.setup();

      mockPost.mockRejectedValueOnce({
        message: 'Network Error',
      });

      render(<ProjectCreationForm onSuccess={mockOnSuccess} onError={mockOnError} />);

      const nameInput = screen.getByLabelText(/project name/i);
      const descInput = screen.getByLabelText(/description/i);

      await user.type(nameInput, 'test-project');
      await user.type(descInput, 'This is a test project description');

      const submitButton = screen.getByRole('button', { name: /create project & start discovery/i });
      await user.click(submitButton);

      expect(await screen.findByText(/failed to create project.*check your connection/i)).toBeInTheDocument();
      expect(mockOnError).toHaveBeenCalled();
    });
  });
});
