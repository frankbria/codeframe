import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import useSWR from 'swr';
import CostsPage from '@/app/costs/page';
import * as storage from '@/lib/workspace-storage';
import type { CostSummaryResponse } from '@/types';

jest.mock('swr');
jest.mock('@/lib/workspace-storage', () => ({
  getSelectedWorkspacePath: jest.fn(),
  setSelectedWorkspacePath: jest.fn(),
}));
jest.mock('@/lib/api', () => ({
  costsApi: {
    getSummary: jest.fn(),
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

describe('CostsPage', () => {
  beforeEach(() => {
    mockGetWorkspace.mockReturnValue(WORKSPACE);
  });
  afterEach(() => jest.clearAllMocks());

  it('shows the workspace selector when no workspace is set', () => {
    mockGetWorkspace.mockReturnValue(null);
    mockUseSWR.mockReturnValue({
      data: undefined,
      error: undefined,
      isLoading: false,
    } as ReturnType<typeof useSWR>);
    render(<CostsPage />);
    expect(screen.getByTestId('workspace-selector')).toBeInTheDocument();
  });

  it('renders summary cards from the API response', () => {
    mockUseSWR.mockReturnValue({
      data: makeSummary(),
      error: undefined,
      isLoading: false,
    } as ReturnType<typeof useSWR>);
    render(<CostsPage />);
    expect(screen.getByTestId('total-spend')).toHaveTextContent('$1.2345');
    expect(screen.getByTestId('total-tasks')).toHaveTextContent('4');
    expect(screen.getByTestId('avg-cost')).toHaveTextContent('$0.3086');
  });

  it('renders the spend chart with the daily series and days prop', () => {
    mockUseSWR.mockReturnValue({
      data: makeSummary(),
      error: undefined,
      isLoading: false,
    } as ReturnType<typeof useSWR>);
    render(<CostsPage />);
    const chart = screen.getByTestId('spend-chart-mock');
    expect(chart.getAttribute('data-days')).toBe('30');
    expect(chart.getAttribute('data-points')).toBe('2');
  });

  it('updates the time range when the selector changes', () => {
    mockUseSWR.mockReturnValue({
      data: makeSummary(),
      error: undefined,
      isLoading: false,
    } as ReturnType<typeof useSWR>);
    render(<CostsPage />);
    const select = screen.getByTestId('time-range-select') as HTMLSelectElement;
    expect(select.value).toBe('30');

    fireEvent.change(select, { target: { value: '7' } });
    expect(select.value).toBe('7');

    fireEvent.change(select, { target: { value: '90' } });
    expect(select.value).toBe('90');
  });

  it('shows the loading skeleton when no data has arrived yet', () => {
    mockUseSWR.mockReturnValue({
      data: undefined,
      error: undefined,
      isLoading: true,
    } as ReturnType<typeof useSWR>);
    render(<CostsPage />);
    expect(screen.getByTestId('costs-loading')).toBeInTheDocument();
  });

  it('shows an error banner on fetch failure', () => {
    mockUseSWR.mockReturnValue({
      data: undefined,
      error: { detail: 'Boom', status_code: 500 },
      isLoading: false,
    } as ReturnType<typeof useSWR>);
    render(<CostsPage />);
    expect(screen.getByTestId('costs-error')).toHaveTextContent('Boom');
  });
});
