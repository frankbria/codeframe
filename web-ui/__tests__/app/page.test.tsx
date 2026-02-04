import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import WorkspacePage from '@/app/page';
import { workspaceApi, tasksApi } from '@/lib/api';

// Mock the API module
jest.mock('@/lib/api', () => ({
  workspaceApi: {
    getCurrent: jest.fn(),
    init: jest.fn(),
  },
  tasksApi: {
    getAll: jest.fn(),
  },
}));

// Mock SWR
jest.mock('swr', () => {
  return {
    __esModule: true,
    default: jest.fn(),
  };
});

import useSWR from 'swr';

const mockUseSWR = useSWR as jest.MockedFunction<typeof useSWR>;

describe('WorkspacePage', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('when workspace exists', () => {
    beforeEach(() => {
      mockUseSWR.mockImplementation((key: string | null) => {
        if (key === '/api/v2/workspaces/current') {
          return {
            data: {
              id: 'ws-123',
              repo_path: '/home/user/my-app',
              state_dir: '/home/user/my-app/.codeframe',
              tech_stack: 'Python with FastAPI',
              created_at: '2026-02-04T10:00:00Z',
            },
            error: undefined,
            isLoading: false,
            mutate: jest.fn(),
          } as any;
        }
        if (key === '/api/v2/tasks') {
          return {
            data: {
              tasks: [],
              total: 15,
              by_status: {
                BACKLOG: 5,
                READY: 3,
                IN_PROGRESS: 2,
                DONE: 4,
                BLOCKED: 1,
                FAILED: 0,
              },
            },
            error: undefined,
            isLoading: false,
            mutate: jest.fn(),
          } as any;
        }
        return { data: undefined, error: undefined, isLoading: false, mutate: jest.fn() } as any;
      });
    });

    it('renders workspace header with path', async () => {
      render(<WorkspacePage />);

      await waitFor(() => {
        expect(screen.getByText('CodeFRAME')).toBeInTheDocument();
      });
    });

    it('renders tech stack card', async () => {
      render(<WorkspacePage />);

      await waitFor(() => {
        expect(screen.getByText('Tech Stack')).toBeInTheDocument();
        expect(screen.getByText('Python with FastAPI')).toBeInTheDocument();
      });
    });

    it('renders task stats', async () => {
      render(<WorkspacePage />);

      await waitFor(() => {
        expect(screen.getByText('Tasks')).toBeInTheDocument();
        expect(screen.getByText('15 total')).toBeInTheDocument();
      });
    });

    it('renders quick actions', async () => {
      render(<WorkspacePage />);

      await waitFor(() => {
        expect(screen.getByText('Quick Actions')).toBeInTheDocument();
      });
    });

    it('renders recent activity feed', async () => {
      render(<WorkspacePage />);

      await waitFor(() => {
        expect(screen.getByText('Recent Activity')).toBeInTheDocument();
      });
    });
  });

  describe('when workspace does not exist', () => {
    beforeEach(() => {
      mockUseSWR.mockImplementation(() => {
        return {
          data: undefined,
          error: { detail: 'Workspace not found', status_code: 404 },
          isLoading: false,
          mutate: jest.fn(),
        } as any;
      });
    });

    it('shows initialization prompt', async () => {
      render(<WorkspacePage />);

      await waitFor(() => {
        expect(screen.getByText(/no workspace initialized/i)).toBeInTheDocument();
        expect(
          screen.getByRole('button', { name: /initialize workspace/i })
        ).toBeInTheDocument();
      });
    });
  });

  describe('loading state', () => {
    beforeEach(() => {
      mockUseSWR.mockImplementation(() => {
        return {
          data: undefined,
          error: undefined,
          isLoading: true,
          mutate: jest.fn(),
        } as any;
      });
    });

    it('shows loading skeleton', async () => {
      render(<WorkspacePage />);

      // Should show some loading indicator
      expect(screen.getByTestId('workspace-loading')).toBeInTheDocument();
    });
  });

  describe('error state', () => {
    beforeEach(() => {
      mockUseSWR.mockImplementation(() => {
        return {
          data: undefined,
          error: { detail: 'Server error', status_code: 500 },
          isLoading: false,
          mutate: jest.fn(),
        } as any;
      });
    });

    it('shows error message', async () => {
      render(<WorkspacePage />);

      await waitFor(() => {
        expect(screen.getByRole('heading', { name: /error/i })).toBeInTheDocument();
        expect(screen.getByText(/server error/i)).toBeInTheDocument();
      });
    });
  });
});
