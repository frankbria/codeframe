import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import useSWR from 'swr';
import CostsPage from '@/app/costs/page';
import * as storage from '@/lib/workspace-storage';
import type {
  CostSummaryResponse,
  TaskCostsResponse,
  AgentCostsResponse,
} from '@/types';

jest.mock('swr');
jest.mock('@/lib/workspace-storage', () => ({
  getSelectedWorkspacePath: jest.fn(),
  setSelectedWorkspacePath: jest.fn(),
}));
jest.mock('@/lib/api', () => ({
  costsApi: {
    getSummary: jest.fn(),
    getTopTasks: jest.fn(),
    getByAgent: jest.fn(),
  },
  workspaceApi: {
    checkExists: jest.fn(),
    init: jest.fn(),
  },
}));
jest.mock('@/components/workspace/WorkspaceSelector', () => ({
  WorkspaceSelector: () => <div data-testid="workspace-selector" />,
}));
jest.mock('@/components/costs/SpendBarChart', () => ({
  SpendBarChart: ({ daily, days }: { daily: unknown[]; days: number }) => (
    <div data-testid="spend-chart-mock" data-days={days} data-points={daily.length} />
  ),
}));
jest.mock('@/components/costs/TopTasksTable', () => ({
  TopTasksTable: ({ tasks, isLoading }: { tasks: unknown[]; isLoading?: boolean }) => (
    <div
      data-testid="top-tasks-mock"
      data-count={tasks.length}
      data-loading={isLoading ? 'true' : 'false'}
    />
  ),
}));
jest.mock('@/components/costs/AgentCostBars', () => ({
  AgentCostBars: ({ data, isLoading }: { data: AgentCostsResponse; isLoading?: boolean }) => (
    <div
      data-testid="agent-bars-mock"
      data-agents={data.by_agent.length}
      data-input={data.total_input_tokens}
      data-output={data.total_output_tokens}
      data-loading={isLoading ? 'true' : 'false'}
    />
  ),
}));

const mockUseSWR = useSWR as jest.MockedFunction<typeof useSWR>;
const mockGetWorkspace = storage.getSelectedWorkspacePath as jest.MockedFunction<
  typeof storage.getSelectedWorkspacePath
>;

const WORKSPACE = '/home/user/project';

function makeSummary(overrides: Partial<CostSummaryResponse> = {}): CostSummaryResponse {
  return {
    total_spend_usd: 1.2345,
    total_tasks: 4,
    avg_cost_per_task: 0.3086,
    daily: [
      { date: '2026-04-01', cost_usd: 0.5 },
      { date: '2026-04-02', cost_usd: 0.7345 },
    ],
    ...overrides,
  };
}

function makeTopTasks(overrides: Partial<TaskCostsResponse> = {}): TaskCostsResponse {
  return {
    tasks: [
      {
        task_id: 't-1',
        task_title: 'Build login',
        agent_id: 'react-agent',
        input_tokens: 1000,
        output_tokens: 500,
        total_cost_usd: 0.42,
      },
    ],
    ...overrides,
  };
}

function makeByAgent(overrides: Partial<AgentCostsResponse> = {}): AgentCostsResponse {
  return {
    by_agent: [
      {
        agent_id: 'claude-code',
        input_tokens: 800,
        output_tokens: 400,
        total_cost_usd: 0.30,
        call_count: 2,
      },
    ],
    total_input_tokens: 1000,
    total_output_tokens: 500,
    ...overrides,
  };
}

/**
 * Set up useSWR mock to return different data based on cache key.
 * Page passes a key like ['/api/v2/costs/summary', workspace, days].
 */
function setupSwr(opts: {
  summary?: CostSummaryResponse | undefined;
  tasks?: TaskCostsResponse | undefined;
  byAgent?: AgentCostsResponse | undefined;
  error?: { detail: string; status_code: number };
  isLoading?: boolean;
}) {
  mockUseSWR.mockImplementation((key: unknown) => {
    const arr = Array.isArray(key) ? key : [];
    const path = arr[0] as string | undefined;
    if (path === '/api/v2/costs/tasks') {
      return {
        data: opts.tasks,
        error: undefined,
        isLoading: opts.isLoading ?? false,
      } as ReturnType<typeof useSWR>;
    }
    if (path === '/api/v2/costs/by-agent') {
      return {
        data: opts.byAgent,
        error: undefined,
        isLoading: opts.isLoading ?? false,
      } as ReturnType<typeof useSWR>;
    }
    // summary endpoint (or null key when no workspace selected)
    return {
      data: opts.summary,
      error: opts.error,
      isLoading: opts.isLoading ?? false,
    } as ReturnType<typeof useSWR>;
  });
}

describe('CostsPage', () => {
  beforeEach(() => {
    mockGetWorkspace.mockReturnValue(WORKSPACE);
  });
  afterEach(() => jest.clearAllMocks());

  it('shows the workspace selector when no workspace is set', () => {
    mockGetWorkspace.mockReturnValue(null);
    setupSwr({});
    render(<CostsPage />);
    expect(screen.getByTestId('workspace-selector')).toBeInTheDocument();
  });

  it('renders summary cards from the API response', () => {
    setupSwr({ summary: makeSummary(), tasks: makeTopTasks(), byAgent: makeByAgent() });
    render(<CostsPage />);
    expect(screen.getByTestId('total-spend')).toHaveTextContent('$1.2345');
    expect(screen.getByTestId('total-tasks')).toHaveTextContent('4');
    expect(screen.getByTestId('avg-cost')).toHaveTextContent('$0.3086');
  });

  it('renders the spend chart with the daily series and days prop', () => {
    setupSwr({ summary: makeSummary(), tasks: makeTopTasks(), byAgent: makeByAgent() });
    render(<CostsPage />);
    const chart = screen.getByTestId('spend-chart-mock');
    expect(chart.getAttribute('data-days')).toBe('30');
    expect(chart.getAttribute('data-points')).toBe('2');
  });

  it('updates the time range when the selector changes', () => {
    setupSwr({ summary: makeSummary(), tasks: makeTopTasks(), byAgent: makeByAgent() });
    render(<CostsPage />);
    const select = screen.getByTestId('time-range-select') as HTMLSelectElement;
    expect(select.value).toBe('30');

    fireEvent.change(select, { target: { value: '7' } });
    expect(select.value).toBe('7');

    fireEvent.change(select, { target: { value: '90' } });
    expect(select.value).toBe('90');
  });

  it('shows the loading skeleton when no data has arrived yet', () => {
    setupSwr({ isLoading: true });
    render(<CostsPage />);
    expect(screen.getByTestId('costs-loading')).toBeInTheDocument();
  });

  it('shows an error banner on fetch failure', () => {
    setupSwr({ error: { detail: 'Boom', status_code: 500 } });
    render(<CostsPage />);
    expect(screen.getByTestId('costs-error')).toHaveTextContent('Boom');
  });

  // ─── Issue #558 sections ─────────────────────────────────────────────

  it('renders the top tasks section with data from the costs/tasks endpoint', () => {
    setupSwr({ summary: makeSummary(), tasks: makeTopTasks(), byAgent: makeByAgent() });
    render(<CostsPage />);
    const top = screen.getByTestId('top-tasks-mock');
    expect(top.getAttribute('data-count')).toBe('1');
    expect(screen.getByRole('heading', { name: /top tasks by cost/i })).toBeInTheDocument();
  });

  it('renders the per-agent section with totals', () => {
    setupSwr({ summary: makeSummary(), tasks: makeTopTasks(), byAgent: makeByAgent() });
    render(<CostsPage />);
    const agents = screen.getByTestId('agent-bars-mock');
    expect(agents.getAttribute('data-agents')).toBe('1');
    expect(agents.getAttribute('data-input')).toBe('1000');
    expect(agents.getAttribute('data-output')).toBe('500');
    expect(screen.getByRole('heading', { name: /cost by agent/i })).toBeInTheDocument();
  });

  it('passes a zero-state fallback to AgentCostBars when no data has loaded yet', () => {
    setupSwr({
      summary: makeSummary(),
      tasks: makeTopTasks(),
      byAgent: undefined,
    });
    render(<CostsPage />);
    const agents = screen.getByTestId('agent-bars-mock');
    expect(agents.getAttribute('data-agents')).toBe('0');
    expect(agents.getAttribute('data-input')).toBe('0');
  });
});
