import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import useSWR from 'swr';
import { toast } from 'sonner';
import PrdPage from '@/app/prd/page';
import { discoveryApi } from '@/lib/api';
import * as storage from '@/lib/workspace-storage';

// ── Mocks ────────────────────────────────────────────────────────────────

jest.mock('swr');
jest.mock('sonner', () => ({
  toast: {
    success: jest.fn(),
    error: jest.fn(),
  },
}));

jest.mock('@/lib/workspace-storage', () => ({
  getSelectedWorkspacePath: jest.fn(),
}));

jest.mock('@/lib/api', () => ({
  prdApi: { getLatest: jest.fn(), createVersion: jest.fn() },
  tasksApi: { getAll: jest.fn() },
  discoveryApi: { generateTasks: jest.fn() },
}));


// Stub out heavy child components
jest.mock('@/components/prd', () => ({
  PRDView: ({
    onGenerateTasks,
    isGeneratingTasks,
    onStressTest,
  }: {
    onGenerateTasks: () => void;
    isGeneratingTasks: boolean;
    onStressTest?: () => void;
  }) => (
    <div>
      <button onClick={onGenerateTasks} disabled={isGeneratingTasks}>
        Generate Tasks
      </button>
      <button onClick={onStressTest}>Stress Test</button>
    </div>
  ),
}));

jest.mock('@/components/prd/UploadPRDModal', () => ({
  UploadPRDModal: () => null,
}));

// Capture the props passed to StressTestModal so we can assert open state.
const stressTestModalProps: { open?: boolean } = {};
jest.mock('@/components/prd/StressTestModal', () => ({
  StressTestModal: ({ open }: { open: boolean }) => {
    stressTestModalProps.open = open;
    return open ? <div>stress-test-modal-open</div> : null;
  },
}));

jest.mock('next/link', () => {
  const MockLink = ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  );
  MockLink.displayName = 'MockLink';
  return MockLink;
});

// ── Helpers ───────────────────────────────────────────────────────────────

const mockUseSWR = useSWR as jest.MockedFunction<typeof useSWR>;
const mockGetSelectedWorkspacePath = storage.getSelectedWorkspacePath as jest.MockedFunction<
  typeof storage.getSelectedWorkspacePath
>;
const mockGenerateTasks = discoveryApi.generateTasks as jest.MockedFunction<
  typeof discoveryApi.generateTasks
>;

const WORKSPACE = '/home/user/project';

const fakePrd = {
  id: 'prd-1',
  title: 'My PRD',
  content: '# Overview',
  version: 1,
  created_at: '2026-01-01T00:00:00Z',
  workspace_path: WORKSPACE,
};

function setupSWR() {
  mockUseSWR.mockImplementation((key) => {
    if (typeof key === 'string' && key.includes('prd')) {
      return { data: fakePrd, error: undefined, isLoading: false, mutate: jest.fn() } as ReturnType<typeof useSWR>;
    }
    return { data: { tasks: [], by_status: {} }, error: undefined, isLoading: false, mutate: jest.fn() } as ReturnType<typeof useSWR>;
  });
}

// ── Tests ─────────────────────────────────────────────────────────────────

describe('PrdPage — handleGenerateTasks', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockGetSelectedWorkspacePath.mockReturnValue(WORKSPACE);
    setupSWR();
  });

  it('shows success toast with task count after generation', async () => {
    mockGenerateTasks.mockResolvedValueOnce({ task_count: 8, tasks: [] });

    render(<PrdPage />);

    fireEvent.click(screen.getByRole('button', { name: /generate tasks/i }));

    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith(
        'Generated 8 tasks from PRD',
        expect.objectContaining({
          duration: 4000,
          action: expect.objectContaining({ label: 'Go to Tasks →' }),
        })
      );
    });
  });

  it('uses singular "task" when count is 1', async () => {
    mockGenerateTasks.mockResolvedValueOnce({ task_count: 1, tasks: [] });

    render(<PrdPage />);
    fireEvent.click(screen.getByRole('button', { name: /generate tasks/i }));

    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith(
        'Generated 1 task from PRD',
        expect.anything()
      );
    });
  });

  it('shows error toast with API error detail on failure', async () => {
    mockGenerateTasks.mockRejectedValueOnce({ detail: 'No PRD content found' });

    render(<PrdPage />);
    fireEvent.click(screen.getByRole('button', { name: /generate tasks/i }));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('No PRD content found');
    });
  });

  it('shows fallback error message when no detail provided', async () => {
    mockGenerateTasks.mockRejectedValueOnce({});

    render(<PrdPage />);
    fireEvent.click(screen.getByRole('button', { name: /generate tasks/i }));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith(
        'Failed to generate tasks. Please try again.'
      );
    });
  });
});

describe('PrdPage — Stress Test wiring', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    delete stressTestModalProps.open;
    mockGetSelectedWorkspacePath.mockReturnValue(WORKSPACE);
    setupSWR();
  });

  it('renders the stress-test modal closed by default', () => {
    render(<PrdPage />);
    expect(stressTestModalProps.open).toBe(false);
    expect(screen.queryByText('stress-test-modal-open')).not.toBeInTheDocument();
  });

  it('opens the stress-test modal when the button is clicked', async () => {
    render(<PrdPage />);
    fireEvent.click(screen.getByRole('button', { name: /stress test/i }));

    await waitFor(() => {
      expect(screen.getByText('stress-test-modal-open')).toBeInTheDocument();
    });
    expect(stressTestModalProps.open).toBe(true);
  });
});
