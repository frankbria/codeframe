/**
 * Unit tests for TokenUsageChart component (T136)
 *
 * Tests:
 * - Renders chart with token usage data
 * - Displays summary statistics
 * - Date range filtering (7, 14, 30 days)
 * - Shows loading and error states
 * - Handles empty data
 *
 * Part of 015-review-polish Phase 5 (Sprint 10 - Metrics & Cost Tracking)
 */

import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { TokenUsageChart } from '../../src/components/metrics/TokenUsageChart';
import * as metricsApi from '../../src/api/metrics';
import type { TokenUsageTimeSeries } from '../../src/types/metrics';

// Mock the API module
jest.mock('../../src/api/metrics');

const mockGetTokenUsageTimeSeries =
  metricsApi.getTokenUsageTimeSeries as jest.MockedFunction<
    typeof metricsApi.getTokenUsageTimeSeries
  >;

describe('TokenUsageChart', () => {
  const mockTimeSeries: TokenUsageTimeSeries[] = [
    {
      timestamp: '2025-11-16T00:00:00Z',
      input_tokens: 5000,
      output_tokens: 3000,
      total_tokens: 8000,
      cost_usd: 0.12,
    },
    {
      timestamp: '2025-11-17T00:00:00Z',
      input_tokens: 7500,
      output_tokens: 4500,
      total_tokens: 12000,
      cost_usd: 0.18,
    },
    {
      timestamp: '2025-11-18T00:00:00Z',
      input_tokens: 6000,
      output_tokens: 3500,
      total_tokens: 9500,
      cost_usd: 0.14,
    },
  ];

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('test_renders_chart_with_data', async () => {
    // ARRANGE
    mockGetTokenUsageTimeSeries.mockResolvedValueOnce(mockTimeSeries);

    // ACT
    const { container } = render(<TokenUsageChart projectId={123} />);

    // ASSERT: Wait for loading to complete
    await waitFor(() => {
      expect(screen.queryByText('Loading...')).not.toBeInTheDocument();
    });

    // Verify title and legend
    expect(screen.getByText('Token Usage Over Time')).toBeInTheDocument();
    expect(screen.getByText('Input Tokens')).toBeInTheDocument();
    expect(screen.getByText('Output Tokens')).toBeInTheDocument();

    // Verify chart bars are rendered
    const chartBars = container.querySelectorAll('.chart-bar-group');
    expect(chartBars.length).toBe(3); // One for each day in mockTimeSeries
  });

  it('test_displays_summary_stats', async () => {
    // ARRANGE
    mockGetTokenUsageTimeSeries.mockResolvedValueOnce(mockTimeSeries);

    // ACT
    render(<TokenUsageChart projectId={123} />);

    // ASSERT: Wait for loading to complete
    await waitFor(() => {
      expect(screen.queryByText('Loading...')).not.toBeInTheDocument();
    });

    // Calculate expected totals
    // Total input: 5000 + 7500 + 6000 = 18,500
    // Total output: 3000 + 4500 + 3500 = 11,000
    // Total cost: 0.12 + 0.18 + 0.14 = 0.44

    // Verify summary stats
    expect(screen.getByText('Total Input Tokens')).toBeInTheDocument();
    expect(screen.getByText('18,500')).toBeInTheDocument();

    expect(screen.getByText('Total Output Tokens')).toBeInTheDocument();
    expect(screen.getByText('11,000')).toBeInTheDocument();

    expect(screen.getByText('Total Cost')).toBeInTheDocument();
    expect(screen.getByText('$0.44')).toBeInTheDocument();
  });

  it('test_date_range_7_days', async () => {
    // ARRANGE
    mockGetTokenUsageTimeSeries.mockResolvedValue(mockTimeSeries);

    // ACT
    render(<TokenUsageChart projectId={123} defaultDays={7} />);

    // ASSERT: Wait for loading to complete
    await waitFor(() => {
      expect(screen.queryByText('Loading...')).not.toBeInTheDocument();
    });

    // Verify API called with correct date range (7 days)
    expect(mockGetTokenUsageTimeSeries).toHaveBeenCalledWith(
      123,
      expect.any(String), // startDate
      expect.any(String), // endDate
      'day'
    );

    // Verify 7 Days button is active
    const sevenDaysButton = screen.getByText('7 Days');
    expect(sevenDaysButton).toHaveClass('bg-blue-600');
  });

  it('test_date_range_14_days', async () => {
    // ARRANGE
    mockGetTokenUsageTimeSeries.mockResolvedValue(mockTimeSeries);

    // ACT
    render(<TokenUsageChart projectId={123} defaultDays={7} />);

    // Wait for initial load
    await waitFor(() => {
      expect(screen.queryByText('Loading...')).not.toBeInTheDocument();
    });

    // ACT: Click 14 Days button
    const fourteenDaysButton = screen.getByText('14 Days');
    fireEvent.click(fourteenDaysButton);

    // ASSERT: Verify button is now active
    await waitFor(() => {
      expect(fourteenDaysButton).toHaveClass('bg-blue-600');
    });

    // Verify API called again with new date range
    expect(mockGetTokenUsageTimeSeries).toHaveBeenCalledTimes(2);
  });

  it('test_date_range_30_days', async () => {
    // ARRANGE
    mockGetTokenUsageTimeSeries.mockResolvedValue(mockTimeSeries);

    // ACT
    render(<TokenUsageChart projectId={123} defaultDays={7} />);

    // Wait for initial load
    await waitFor(() => {
      expect(screen.queryByText('Loading...')).not.toBeInTheDocument();
    });

    // ACT: Click 30 Days button
    const thirtyDaysButton = screen.getByText('30 Days');
    fireEvent.click(thirtyDaysButton);

    // ASSERT: Verify button is now active
    await waitFor(() => {
      expect(thirtyDaysButton).toHaveClass('bg-blue-600');
    });

    // Verify API called again with new date range
    expect(mockGetTokenUsageTimeSeries).toHaveBeenCalledTimes(2);
  });

  it('test_shows_loading_state', () => {
    // ARRANGE
    mockGetTokenUsageTimeSeries.mockImplementation(
      () => new Promise(() => {}) // Never resolves
    );

    // ACT
    render(<TokenUsageChart projectId={123} />);

    // ASSERT
    expect(screen.getByText('Loading...')).toBeInTheDocument();
    expect(screen.getByText('Token Usage Over Time')).toBeInTheDocument();
  });

  it('test_shows_error_state', async () => {
    // ARRANGE
    mockGetTokenUsageTimeSeries.mockRejectedValueOnce(
      new Error('Failed to load data')
    );

    // ACT
    render(<TokenUsageChart projectId={123} />);

    // ASSERT: Wait for error to appear
    await waitFor(() => {
      expect(screen.queryByText('Loading...')).not.toBeInTheDocument();
    });

    expect(
      screen.getByText(/Error: Failed to load data/)
    ).toBeInTheDocument();
  });

  it('test_handles_empty_data', async () => {
    // ARRANGE
    mockGetTokenUsageTimeSeries.mockResolvedValueOnce([]);

    // ACT
    render(<TokenUsageChart projectId={123} />);

    // ASSERT: Wait for loading to complete
    await waitFor(() => {
      expect(screen.queryByText('Loading...')).not.toBeInTheDocument();
    });

    // Verify empty state message
    expect(
      screen.getByText('No token usage data available')
    ).toBeInTheDocument();
  });

  it('test_handles_zero_tokens', async () => {
    // ARRANGE
    const zeroTokensSeries: TokenUsageTimeSeries[] = [
      {
        timestamp: '2025-11-16T00:00:00Z',
        input_tokens: 0,
        output_tokens: 0,
        total_tokens: 0,
        cost_usd: 0.0,
      },
    ];
    mockGetTokenUsageTimeSeries.mockResolvedValueOnce(zeroTokensSeries);

    // ACT
    render(<TokenUsageChart projectId={123} />);

    // ASSERT: Wait for loading to complete
    await waitFor(() => {
      expect(screen.queryByText('Loading...')).not.toBeInTheDocument();
    });

    // Verify zero values are displayed (use getAllByText since there are multiple "0"s)
    const zeroElements = screen.getAllByText('0');
    expect(zeroElements.length).toBeGreaterThan(0); // At least one "0" displayed
    expect(screen.getByText('$0.00')).toBeInTheDocument();
  });

  it('test_formats_large_numbers', async () => {
    // ARRANGE
    const largeNumbersSeries: TokenUsageTimeSeries[] = [
      {
        timestamp: '2025-11-16T00:00:00Z',
        input_tokens: 1234567,
        output_tokens: 987654,
        total_tokens: 2222221,
        cost_usd: 33.44,
      },
    ];
    mockGetTokenUsageTimeSeries.mockResolvedValueOnce(largeNumbersSeries);

    // ACT
    render(<TokenUsageChart projectId={123} />);

    // ASSERT: Wait for loading to complete
    await waitFor(() => {
      expect(screen.queryByText('Loading...')).not.toBeInTheDocument();
    });

    // Verify number formatting with commas
    expect(screen.getByText('1,234,567')).toBeInTheDocument();
    expect(screen.getByText('987,654')).toBeInTheDocument();
    expect(screen.getByText('$33.44')).toBeInTheDocument();
  });

  it('test_renders_chart_bars', async () => {
    // ARRANGE
    mockGetTokenUsageTimeSeries.mockResolvedValueOnce(mockTimeSeries);

    // ACT
    const { container } = render(<TokenUsageChart projectId={123} />);

    // ASSERT: Wait for loading to complete
    await waitFor(() => {
      expect(screen.queryByText('Loading...')).not.toBeInTheDocument();
    });

    // Verify chart bars are rendered (CSS classes for visualization)
    const chartBars = container.querySelectorAll('.chart-bar-group');
    expect(chartBars.length).toBe(3); // One for each day in mockTimeSeries
  });
});
