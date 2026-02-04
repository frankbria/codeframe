import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import WorkspacePage from '@/app/page';

// Mock localStorage
const localStorageMock = (() => {
  let store: Record<string, string> = {};
  return {
    getItem: (key: string) => store[key] || null,
    setItem: (key: string, value: string) => {
      store[key] = value;
    },
    removeItem: (key: string) => {
      delete store[key];
    },
    clear: () => {
      store = {};
    },
  };
})();

Object.defineProperty(window, 'localStorage', { value: localStorageMock });

// Mock the API module
jest.mock('@/lib/api', () => ({
  workspaceApi: {
    getByPath: jest.fn(),
    checkExists: jest.fn(),
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
import { workspaceApi } from '@/lib/api';

const mockUseSWR = useSWR as jest.MockedFunction<typeof useSWR>;
const mockWorkspaceApi = workspaceApi as jest.Mocked<typeof workspaceApi>;

describe('WorkspacePage', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    localStorageMock.clear();
  });

  describe('workspace selector (no workspace selected)', () => {
    beforeEach(() => {
      mockUseSWR.mockImplementation(() => {
        return {
          data: undefined,
          error: undefined,
          isLoading: false,
          mutate: jest.fn(),
        } as any;
      });
    });

    it('shows workspace selector when no path stored', async () => {
      render(<WorkspacePage />);

      await waitFor(() => {
        expect(screen.getByText('Select a project to get started')).toBeInTheDocument();
        expect(screen.getByRole('button', { name: 'Open Project' })).toBeInTheDocument();
        expect(screen.getByPlaceholderText('/home/user/projects/my-app')).toBeInTheDocument();
      });
    });

    it('allows entering a workspace path', async () => {
      render(<WorkspacePage />);

      const input = screen.getByPlaceholderText('/home/user/projects/my-app');
      fireEvent.change(input, { target: { value: '/home/user/test-project' } });

      expect(input).toHaveValue('/home/user/test-project');
    });
  });

  describe('when workspace is selected and exists', () => {
    beforeEach(() => {
      // Set workspace path in localStorage
      localStorageMock.setItem('codeframe_workspace_path', '/home/user/my-app');

      mockUseSWR.mockImplementation((key: string | null) => {
        if (key && key.includes('/api/v2/workspaces/current')) {
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
        if (key && key.includes('/api/v2/tasks')) {
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

    it('shows switch project button', async () => {
      render(<WorkspacePage />);

      await waitFor(() => {
        expect(screen.getByText('← Switch project')).toBeInTheDocument();
      });
    });
  });

  describe('loading state', () => {
    beforeEach(() => {
      localStorageMock.setItem('codeframe_workspace_path', '/home/user/my-app');

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

      expect(screen.getByTestId('workspace-loading')).toBeInTheDocument();
    });
  });

  describe('error state', () => {
    beforeEach(() => {
      localStorageMock.setItem('codeframe_workspace_path', '/home/user/my-app');

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

    it('shows option to select different project', async () => {
      render(<WorkspacePage />);

      await waitFor(() => {
        expect(screen.getByText('← Select a different project')).toBeInTheDocument();
      });
    });
  });
});
