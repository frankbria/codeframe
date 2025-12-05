/**
 * Unit tests for CostDashboard component (T135)
 *
 * Tests:
 * - Renders total project cost
 * - Displays cost breakdown by agent
 * - Displays cost breakdown by model
 * - Shows loading and error states
 * - Handles empty data
 *
 * Part of 015-review-polish Phase 5 (Sprint 10 - Metrics & Cost Tracking)
 */

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { CostDashboard } from '../../src/components/metrics/CostDashboard';
import * as metricsApi from '../../src/api/metrics';
import type { CostBreakdown, TokenUsage } from '../../src/types/metrics';

// Mock the API module
jest.mock('../../src/api/metrics');

const mockGetProjectCosts = metricsApi.getProjectCosts as jest.MockedFunction<
  typeof metricsApi.getProjectCosts
>;

const mockGetProjectTokens = metricsApi.getProjectTokens as jest.MockedFunction<
  typeof metricsApi.getProjectTokens
>;

const mockGetTokenUsageTimeSeries = metricsApi.getTokenUsageTimeSeries as jest.MockedFunction<
  typeof metricsApi.getTokenUsageTimeSeries
>;

describe('CostDashboard', () => {
  const mockCostBreakdown: CostBreakdown = {
    total_cost_usd: 15.75,
    by_agent: [
      {
        agent_id: 'backend-001',
        cost_usd: 8.25,
        call_count: 150,
        total_tokens: 75000,
      },
      {
        agent_id: 'frontend-001',
        cost_usd: 7.5,
        call_count: 120,
        total_tokens: 60000,
      },
    ],
    by_model: [
      {
        model_name: 'claude-sonnet-4-5-20250929',
        cost_usd: 12.0,
        call_count: 200,
        total_tokens: 100000,
      },
      {
        model_name: 'claude-opus-4-20250514',
        cost_usd: 3.75,
        call_count: 70,
        total_tokens: 35000,
      },
    ],
  };

  const mockTokenUsage: TokenUsage[] = [
    {
      id: 1,
      task_id: 27,
      agent_id: 'backend-001',
      project_id: 123,
      model_name: 'claude-sonnet-4-5',
      input_tokens: 1000,
      output_tokens: 500,
      estimated_cost_usd: 0.015,
      call_type: 'task_execution',
      timestamp: '2025-11-23T10:00:00Z',
    },
    {
      id: 2,
      task_id: 28,
      agent_id: 'frontend-001',
      project_id: 123,
      model_name: 'claude-sonnet-4-5',
      input_tokens: 800,
      output_tokens: 400,
      estimated_cost_usd: 0.012,
      call_type: 'task_execution',
      timestamp: '2025-11-23T11:00:00Z',
    },
  ];

  beforeEach(() => {
    jest.clearAllMocks();
    jest.useFakeTimers();

    // Setup default mocks for new API calls
    mockGetProjectTokens.mockResolvedValue(mockTokenUsage);
    mockGetTokenUsageTimeSeries.mockResolvedValue([]);
  });

  afterEach(() => {
    jest.runOnlyPendingTimers();
    jest.useRealTimers();
  });

  it('test_renders_total_cost', async () => {
    // ARRANGE
    mockGetProjectCosts.mockResolvedValueOnce(mockCostBreakdown);

    // ACT
    render(<CostDashboard projectId={123} />);

    // ASSERT: Wait for loading to complete
    await waitFor(() => {
      expect(screen.queryByText('Loading...')).not.toBeInTheDocument();
    });

    // Verify total cost is displayed
    expect(screen.getByText('$15.75')).toBeInTheDocument();
    expect(screen.getByText('Total Project Cost')).toBeInTheDocument();
  });

  it('test_displays_agent_breakdown', async () => {
    // ARRANGE
    mockGetProjectCosts.mockResolvedValueOnce(mockCostBreakdown);

    // ACT
    render(<CostDashboard projectId={123} />);

    // ASSERT: Wait for loading to complete
    await waitFor(() => {
      expect(screen.queryByText('Loading...')).not.toBeInTheDocument();
    });

    // Verify agent breakdown table
    expect(screen.getByText('Cost by Agent')).toBeInTheDocument();
    expect(screen.getByText('backend-001')).toBeInTheDocument();
    expect(screen.getByText('frontend-001')).toBeInTheDocument();

    // Verify agent costs
    expect(screen.getByText('$8.25')).toBeInTheDocument();
    expect(screen.getByText('$7.50')).toBeInTheDocument();

    // Verify call counts and token counts are formatted
    expect(screen.getByText('150')).toBeInTheDocument();
    expect(screen.getByText('120')).toBeInTheDocument();
    expect(screen.getByText('75,000')).toBeInTheDocument();
    expect(screen.getByText('60,000')).toBeInTheDocument();
  });

  it('test_displays_model_breakdown', async () => {
    // ARRANGE
    mockGetProjectCosts.mockResolvedValueOnce(mockCostBreakdown);

    // ACT
    render(<CostDashboard projectId={123} />);

    // ASSERT: Wait for loading to complete
    await waitFor(() => {
      expect(screen.queryByText('Loading...')).not.toBeInTheDocument();
    });

    // Verify model breakdown table
    expect(screen.getByText('Cost by Model')).toBeInTheDocument();
    expect(
      screen.getByText('claude-sonnet-4-5-20250929')
    ).toBeInTheDocument();
    expect(screen.getByText('claude-opus-4-20250514')).toBeInTheDocument();

    // Verify model costs
    expect(screen.getByText('$12.00')).toBeInTheDocument();
    expect(screen.getByText('$3.75')).toBeInTheDocument();

    // Verify call counts
    expect(screen.getByText('200')).toBeInTheDocument();
    expect(screen.getByText('70')).toBeInTheDocument();
  });

  it('test_shows_loading_state', () => {
    // ARRANGE
    mockGetProjectCosts.mockImplementation(
      () => new Promise(() => {}) // Never resolves
    );

    // ACT
    render(<CostDashboard projectId={123} />);

    // ASSERT
    expect(screen.getByText('Loading...')).toBeInTheDocument();
    expect(screen.getByText('Cost Metrics')).toBeInTheDocument();
  });

  it('test_shows_error_state', async () => {
    // ARRANGE
    mockGetProjectCosts.mockRejectedValueOnce(
      new Error('Failed to fetch costs')
    );

    // ACT
    render(<CostDashboard projectId={123} />);

    // ASSERT: Wait for error to appear
    await waitFor(() => {
      expect(screen.queryByText('Loading...')).not.toBeInTheDocument();
    });

    expect(
      screen.getByText(/Error: Failed to fetch costs/)
    ).toBeInTheDocument();
  });

  it('test_handles_empty_agent_data', async () => {
    // ARRANGE
    const emptyAgentBreakdown: CostBreakdown = {
      total_cost_usd: 10.0,
      by_agent: [],
      by_model: mockCostBreakdown.by_model,
    };
    mockGetProjectCosts.mockResolvedValueOnce(emptyAgentBreakdown);

    // ACT
    render(<CostDashboard projectId={123} />);

    // ASSERT: Wait for loading to complete
    await waitFor(() => {
      expect(screen.queryByText('Loading...')).not.toBeInTheDocument();
    });

    // Verify empty state message
    expect(screen.getByText('No agent data available')).toBeInTheDocument();
  });

  it('test_handles_empty_model_data', async () => {
    // ARRANGE
    const emptyModelBreakdown: CostBreakdown = {
      total_cost_usd: 10.0,
      by_agent: mockCostBreakdown.by_agent,
      by_model: [],
    };
    mockGetProjectCosts.mockResolvedValueOnce(emptyModelBreakdown);

    // ACT
    render(<CostDashboard projectId={123} />);

    // ASSERT: Wait for loading to complete
    await waitFor(() => {
      expect(screen.queryByText('Loading...')).not.toBeInTheDocument();
    });

    // Verify empty state message
    expect(screen.getByText('No model data available')).toBeInTheDocument();
  });

  it('test_auto_refreshes', async () => {
    // ARRANGE
    mockGetProjectCosts.mockResolvedValue(mockCostBreakdown);

    // ACT
    render(<CostDashboard projectId={123} refreshInterval={5000} />);

    // ASSERT: Wait for initial load
    await waitFor(() => {
      expect(screen.queryByText('Loading...')).not.toBeInTheDocument();
    });

    // Verify API called once
    expect(mockGetProjectCosts).toHaveBeenCalledTimes(1);

    // Fast-forward time by 5 seconds
    jest.advanceTimersByTime(5000);

    // Verify API called again after refresh interval
    await waitFor(() => {
      expect(mockGetProjectCosts).toHaveBeenCalledTimes(2);
    });
  });

  it('test_formats_currency_correctly', async () => {
    // ARRANGE
    const breakdown: CostBreakdown = {
      total_cost_usd: 1234.567,
      by_agent: [
        {
          agent_id: 'test-agent',
          cost_usd: 0.12,
          call_count: 1,
          total_tokens: 100,
        },
      ],
      by_model: [],
    };
    mockGetProjectCosts.mockResolvedValueOnce(breakdown);

    // ACT
    render(<CostDashboard projectId={123} />);

    // ASSERT: Wait for loading to complete
    await waitFor(() => {
      expect(screen.queryByText('Loading...')).not.toBeInTheDocument();
    });

    // Verify currency formatting (2 decimal places)
    expect(screen.getByText('$1234.57')).toBeInTheDocument();
    expect(screen.getByText('$0.12')).toBeInTheDocument();
  });
});
