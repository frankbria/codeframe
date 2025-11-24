/**
 * Unit tests for metrics API client (T137)
 *
 * Tests:
 * - All API methods (getProjectTokens, getProjectCosts, getAgentMetrics, etc.)
 * - Error handling for all methods
 *
 * Part of 015-review-polish Phase 5 (Sprint 10 - Metrics & Cost Tracking)
 */

import {
  getProjectTokens,
  getProjectCosts,
  getAgentMetrics,
  getTokenUsageTimeSeries,
  queryTokenUsage,
} from '../../src/api/metrics';
import type {
  TokenUsage,
  CostBreakdown,
  AgentMetrics,
  TokenUsageTimeSeries,
} from '../../src/types/metrics';

// Mock fetch
global.fetch = jest.fn();

const API_BASE_URL = 'http://localhost:8000';

describe('Metrics API Client', () => {
  const mockTokenUsage: TokenUsage = {
    id: 1,
    task_id: 27,
    agent_id: 'backend-001',
    project_id: 123,
    model_name: 'claude-sonnet-4-5-20250929',
    input_tokens: 5000,
    output_tokens: 3000,
    estimated_cost_usd: 0.12,
    actual_cost_usd: 0.12,
    call_type: 'task_execution',
    timestamp: '2025-11-23T10:30:00Z',
  };

  const mockCostBreakdown: CostBreakdown = {
    total_cost_usd: 15.75,
    by_agent: [
      {
        agent_id: 'backend-001',
        cost_usd: 8.25,
        call_count: 150,
        total_tokens: 75000,
      },
    ],
    by_model: [
      {
        model_name: 'claude-sonnet-4-5-20250929',
        cost_usd: 15.75,
        call_count: 150,
        total_tokens: 75000,
      },
    ],
  };

  const mockAgentMetrics: AgentMetrics = {
    agent_id: 'backend-001',
    project_id: 123,
    total_cost_usd: 8.25,
    total_input_tokens: 50000,
    total_output_tokens: 25000,
    total_calls: 150,
    by_call_type: [
      {
        call_type: 'task_execution',
        cost_usd: 6.5,
        call_count: 120,
      },
      {
        call_type: 'code_review',
        cost_usd: 1.75,
        call_count: 30,
      },
    ],
    by_model: [
      {
        model_name: 'claude-sonnet-4-5-20250929',
        cost_usd: 8.25,
        call_count: 150,
        total_tokens: 75000,
      },
    ],
    first_call_at: '2025-11-20T08:00:00Z',
    last_call_at: '2025-11-23T10:30:00Z',
  };

  const mockTimeSeries: TokenUsageTimeSeries[] = [
    {
      timestamp: '2025-11-22T00:00:00Z',
      input_tokens: 5000,
      output_tokens: 3000,
      total_tokens: 8000,
      cost_usd: 0.12,
    },
    {
      timestamp: '2025-11-23T00:00:00Z',
      input_tokens: 7500,
      output_tokens: 4500,
      total_tokens: 12000,
      cost_usd: 0.18,
    },
  ];

  beforeEach(() => {
    jest.clearAllMocks();
    (global.fetch as jest.Mock).mockClear();
  });

  describe('getProjectTokens', () => {
    it('test_get_project_tokens_success', async () => {
      // ARRANGE
      const mockTokens = [mockTokenUsage];
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => mockTokens,
      });

      // ACT
      const result = await getProjectTokens(123);

      // ASSERT
      expect(global.fetch).toHaveBeenCalledWith(
        `${API_BASE_URL}/api/projects/123/metrics/tokens?limit=100`,
        {
          method: 'GET',
          headers: { 'Content-Type': 'application/json' },
        }
      );
      expect(result).toEqual(mockTokens);
    });

    it('test_get_project_tokens_with_date_range', async () => {
      // ARRANGE
      const mockTokens = [mockTokenUsage];
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => mockTokens,
      });

      // ACT
      const result = await getProjectTokens(
        123,
        '2025-11-20T00:00:00Z',
        '2025-11-23T23:59:59Z',
        50
      );

      // ASSERT
      expect(global.fetch).toHaveBeenCalledWith(
        `${API_BASE_URL}/api/projects/123/metrics/tokens?start_date=2025-11-20T00%3A00%3A00Z&end_date=2025-11-23T23%3A59%3A59Z&limit=50`,
        {
          method: 'GET',
          headers: { 'Content-Type': 'application/json' },
        }
      );
      expect(result).toEqual(mockTokens);
    });

    it('test_get_project_tokens_error', async () => {
      // ARRANGE
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 404,
        text: async () => 'Project not found',
      });

      // ACT & ASSERT
      await expect(getProjectTokens(123)).rejects.toThrow(
        'Failed to fetch project tokens: 404 Project not found'
      );
    });

    it('test_get_project_tokens_network_error', async () => {
      // ARRANGE
      (global.fetch as jest.Mock).mockRejectedValueOnce(
        new Error('Network error')
      );

      // ACT & ASSERT
      await expect(getProjectTokens(123)).rejects.toThrow('Network error');
    });
  });

  describe('getProjectCosts', () => {
    it('test_get_project_costs_success', async () => {
      // ARRANGE
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => mockCostBreakdown,
      });

      // ACT
      const result = await getProjectCosts(123);

      // ASSERT
      expect(global.fetch).toHaveBeenCalledWith(
        `${API_BASE_URL}/api/projects/123/metrics/costs`,
        {
          method: 'GET',
          headers: { 'Content-Type': 'application/json' },
        }
      );
      expect(result).toEqual(mockCostBreakdown);
    });

    it('test_get_project_costs_error', async () => {
      // ARRANGE
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 500,
        text: async () => 'Internal server error',
      });

      // ACT & ASSERT
      await expect(getProjectCosts(123)).rejects.toThrow(
        'Failed to fetch project costs: 500 Internal server error'
      );
    });
  });

  describe('getAgentMetrics', () => {
    it('test_get_agent_metrics_success', async () => {
      // ARRANGE
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => mockAgentMetrics,
      });

      // ACT
      const result = await getAgentMetrics('backend-001', 123);

      // ASSERT
      expect(global.fetch).toHaveBeenCalledWith(
        `${API_BASE_URL}/api/agents/backend-001/metrics?project_id=123`,
        {
          method: 'GET',
          headers: { 'Content-Type': 'application/json' },
        }
      );
      expect(result).toEqual(mockAgentMetrics);
    });

    it('test_get_agent_metrics_without_project_id', async () => {
      // ARRANGE
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => mockAgentMetrics,
      });

      // ACT
      const result = await getAgentMetrics('backend-001');

      // ASSERT
      expect(global.fetch).toHaveBeenCalledWith(
        `${API_BASE_URL}/api/agents/backend-001/metrics`,
        {
          method: 'GET',
          headers: { 'Content-Type': 'application/json' },
        }
      );
      expect(result).toEqual(mockAgentMetrics);
    });

    it('test_get_agent_metrics_error', async () => {
      // ARRANGE
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 404,
        text: async () => 'Agent not found',
      });

      // ACT & ASSERT
      await expect(getAgentMetrics('backend-001')).rejects.toThrow(
        'Failed to fetch agent metrics: 404 Agent not found'
      );
    });
  });

  describe('getTokenUsageTimeSeries', () => {
    it('test_get_token_usage_time_series_success', async () => {
      // ARRANGE
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => mockTimeSeries,
      });

      // ACT
      const result = await getTokenUsageTimeSeries(
        123,
        '2025-11-20T00:00:00Z',
        '2025-11-23T23:59:59Z',
        'day'
      );

      // ASSERT
      expect(global.fetch).toHaveBeenCalledWith(
        `${API_BASE_URL}/api/projects/123/metrics/tokens/timeseries?start_date=2025-11-20T00%3A00%3A00Z&end_date=2025-11-23T23%3A59%3A59Z&interval=day`,
        {
          method: 'GET',
          headers: { 'Content-Type': 'application/json' },
        }
      );
      expect(result).toEqual(mockTimeSeries);
    });

    it('test_get_token_usage_time_series_default_interval', async () => {
      // ARRANGE
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => mockTimeSeries,
      });

      // ACT
      const result = await getTokenUsageTimeSeries(
        123,
        '2025-11-20T00:00:00Z',
        '2025-11-23T23:59:59Z'
      );

      // ASSERT
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('interval=day'),
        expect.any(Object)
      );
      expect(result).toEqual(mockTimeSeries);
    });

    it('test_get_token_usage_time_series_error', async () => {
      // ARRANGE
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 400,
        text: async () => 'Invalid date range',
      });

      // ACT & ASSERT
      await expect(
        getTokenUsageTimeSeries(
          123,
          '2025-11-20T00:00:00Z',
          '2025-11-23T23:59:59Z'
        )
      ).rejects.toThrow(
        'Failed to fetch token usage time series: 400 Invalid date range'
      );
    });
  });

  describe('queryTokenUsage', () => {
    it('test_query_token_usage_all_params', async () => {
      // ARRANGE
      const mockTokens = [mockTokenUsage];
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => mockTokens,
      });

      // ACT
      const result = await queryTokenUsage({
        project_id: 123,
        agent_id: 'backend-001',
        start_date: '2025-11-20T00:00:00Z',
        end_date: '2025-11-23T23:59:59Z',
        call_type: 'task_execution',
        limit: 50,
      });

      // ASSERT
      expect(global.fetch).toHaveBeenCalledWith(
        `${API_BASE_URL}/api/metrics/tokens?project_id=123&agent_id=backend-001&start_date=2025-11-20T00%3A00%3A00Z&end_date=2025-11-23T23%3A59%3A59Z&call_type=task_execution&limit=50`,
        {
          method: 'GET',
          headers: { 'Content-Type': 'application/json' },
        }
      );
      expect(result).toEqual(mockTokens);
    });

    it('test_query_token_usage_minimal_params', async () => {
      // ARRANGE
      const mockTokens = [mockTokenUsage];
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: true,
        json: async () => mockTokens,
      });

      // ACT
      const result = await queryTokenUsage({
        project_id: 123,
      });

      // ASSERT
      expect(global.fetch).toHaveBeenCalledWith(
        `${API_BASE_URL}/api/metrics/tokens?project_id=123`,
        {
          method: 'GET',
          headers: { 'Content-Type': 'application/json' },
        }
      );
      expect(result).toEqual(mockTokens);
    });

    it('test_query_token_usage_error', async () => {
      // ARRANGE
      (global.fetch as jest.Mock).mockResolvedValueOnce({
        ok: false,
        status: 422,
        text: async () => 'Invalid query parameters',
      });

      // ACT & ASSERT
      await expect(
        queryTokenUsage({ project_id: 123 })
      ).rejects.toThrow(
        'Failed to query token usage: 422 Invalid query parameters'
      );
    });
  });
});
