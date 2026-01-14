/**
 * Unit tests for ContextPanel component (T060)
 *
 * Tests:
 * - Renders tier breakdown (HOT/WARM/COLD counts)
 * - Displays token usage with percentage
 * - Shows loading and error states
 *
 * Part of 007-context-management Phase 7 (US5 - Context Visualization)
 */

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { ContextPanel } from '../../src/components/context/ContextPanel';
import * as contextApi from '../../src/api/context';
import type { ContextStats } from '../../src/types/context';

// Mock the API module
jest.mock('../../src/api/context');

const mockFetchContextStats = contextApi.fetchContextStats as jest.MockedFunction<
  typeof contextApi.fetchContextStats
>;

describe('ContextPanel', () => {
  const mockStats: ContextStats = {
    agent_id: 'test-agent-001',
    project_id: 123,
    hot_count: 20,
    warm_count: 50,
    cold_count: 30,
    total_count: 100,
    hot_tokens: 15000,
    warm_tokens: 25000,
    cold_tokens: 10000,
    total_tokens: 50000,
    token_usage_percentage: 27.78,
    calculated_at: '2025-11-14T10:30:00Z',
  };

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('test_renders_tier_breakdown', async () => {
    // ARRANGE
    mockFetchContextStats.mockResolvedValueOnce(mockStats);

    // ACT
    render(<ContextPanel agentId="test-agent-001" projectId={123} />);

    // ASSERT: Wait for loading to complete
    await waitFor(() => {
      expect(screen.queryByText('Loading...')).not.toBeInTheDocument();
    });

    // Verify tier counts are displayed
    expect(screen.getByText('20')).toBeInTheDocument(); // HOT count
    expect(screen.getByText('50')).toBeInTheDocument(); // WARM count
    expect(screen.getByText('30')).toBeInTheDocument(); // COLD count

    // Verify tier labels
    expect(screen.getByText('HOT')).toBeInTheDocument();
    expect(screen.getByText('WARM')).toBeInTheDocument();
    expect(screen.getByText('COLD')).toBeInTheDocument();

    // Verify total count
    expect(screen.getByText(/Total Items:/)).toBeInTheDocument();
    expect(screen.getByText(/100/)).toBeInTheDocument();
  });

  it('test_displays_token_usage', async () => {
    // ARRANGE
    mockFetchContextStats.mockResolvedValueOnce(mockStats);

    // ACT
    render(<ContextPanel agentId="test-agent-001" projectId={123} />);

    // ASSERT: Wait for loading to complete
    await waitFor(() => {
      expect(screen.queryByText('Loading...')).not.toBeInTheDocument();
    });

    // Verify token usage is displayed
    expect(screen.getByText(/50,000 \/ 180,000 tokens/)).toBeInTheDocument();
    expect(screen.getByText(/27\.8%/)).toBeInTheDocument();

    // Verify token counts per tier are shown
    expect(screen.getByText(/15,000 tokens/)).toBeInTheDocument(); // HOT
    expect(screen.getByText(/25,000 tokens/)).toBeInTheDocument(); // WARM
    expect(screen.getByText(/10,000 tokens/)).toBeInTheDocument(); // COLD
  });

  it('test_shows_loading_state', () => {
    // ARRANGE
    mockFetchContextStats.mockImplementation(
      () => new Promise(() => {}) // Never resolves
    );

    // ACT
    render(<ContextPanel agentId="test-agent-001" projectId={123} />);

    // ASSERT: Loading state is shown
    expect(screen.getByText('Loading...')).toBeInTheDocument();
    expect(screen.getByText('Context Overview')).toBeInTheDocument();
  });

  it('test_shows_error_state', async () => {
    // ARRANGE
    const errorMessage = 'Failed to fetch context stats: 500 Internal Server Error';
    mockFetchContextStats.mockRejectedValueOnce(new Error(errorMessage));

    // ACT
    render(<ContextPanel agentId="test-agent-001" projectId={123} />);

    // ASSERT: Wait for error to appear
    await waitFor(() => {
      expect(screen.getByText(errorMessage)).toBeInTheDocument();
    });

    expect(screen.getByText('Context Overview')).toBeInTheDocument();
  });

  it('test_calls_api_with_correct_params', async () => {
    // ARRANGE
    mockFetchContextStats.mockResolvedValueOnce(mockStats);

    // ACT
    render(<ContextPanel agentId="test-agent-001" projectId={123} />);

    // ASSERT: API called with correct parameters
    await waitFor(() => {
      expect(mockFetchContextStats).toHaveBeenCalledWith('test-agent-001', 123);
    });
  });

  it('test_auto_refresh_enabled', async () => {
    // ARRANGE
    mockFetchContextStats.mockResolvedValue(mockStats);

    // Use fake timers
    jest.useFakeTimers();

    // ACT
    render(
      <ContextPanel agentId="test-agent-001" projectId={123} refreshInterval={1000} />
    );

    // Wait for initial load
    await waitFor(() => {
      expect(mockFetchContextStats).toHaveBeenCalledTimes(1);
    });

    // Fast-forward time by 1 second
    jest.advanceTimersByTime(1000);

    // ASSERT: API called again after interval
    await waitFor(() => {
      expect(mockFetchContextStats).toHaveBeenCalledTimes(2);
    });

    // Cleanup
    jest.useRealTimers();
  });
});
