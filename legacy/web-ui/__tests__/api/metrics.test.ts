/**
 * Unit tests for metrics API client (T137)
 *
 * Tests:
 * - All API methods (getProjectTokens, getProjectCosts, getAgentMetrics, etc.)
 * - Error handling for all methods
 *
 * Part of 015-review-polish Phase 5 (Sprint 10 - Metrics & Cost Tracking)
 */

// Mock the api-client module BEFORE imports
jest.mock('../../src/lib/api-client', () => ({
  authFetch: jest.fn(),
}));

import {
  getProjectTokens,
  getProjectCosts,
  getAgentMetrics,
  getTokenUsageTimeSeries,
  queryTokenUsage,
} from '../../src/api/metrics';
import { authFetch } from '../../src/lib/api-client';
import type {
  TokenUsage,
  CostBreakdown,
  AgentMetrics,
  TokenUsageTimeSeries,
} from '../../src/types/metrics';

const mockAuthFetch = authFetch as jest.MockedFunction<typeof authFetch>;

const API_BASE_URL = 'http://localhost:8080';

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
  });

  describe('getProjectTokens', () => {
    it('test_get_project_tokens_success', async () => {
      // ARRANGE
      const mockTokens = [mockTokenUsage];
      mockAuthFetch.mockResolvedValueOnce(mockTokens);

      // ACT
      const result = await getProjectTokens(123);

      // ASSERT
      expect(mockAuthFetch).toHaveBeenCalledWith(
        `${API_BASE_URL}/api/projects/123/metrics/tokens?limit=100`
      );
      expect(result).toEqual(mockTokens);
    });

    it('test_get_project_tokens_with_date_range', async () => {
      // ARRANGE
      const mockTokens = [mockTokenUsage];
      mockAuthFetch.mockResolvedValueOnce(mockTokens);

      // ACT
      const result = await getProjectTokens(
        123,
        '2025-11-20T00:00:00Z',
        '2025-11-23T23:59:59Z',
        50
      );

      // ASSERT
      expect(mockAuthFetch).toHaveBeenCalledWith(
        `${API_BASE_URL}/api/projects/123/metrics/tokens?start_date=2025-11-20T00%3A00%3A00Z&end_date=2025-11-23T23%3A59%3A59Z&limit=50`
      );
      expect(result).toEqual(mockTokens);
    });

    it('test_get_project_tokens_error', async () => {
      // ARRANGE
      mockAuthFetch.mockRejectedValueOnce(
        new Error('Request failed: 404 Project not found')
      );

      // ACT & ASSERT
      await expect(getProjectTokens(123)).rejects.toThrow(
        'Project not found'
      );
    });

    it('test_get_project_tokens_network_error', async () => {
      // ARRANGE
      mockAuthFetch.mockRejectedValueOnce(new Error('Network error'));

      // ACT & ASSERT
      await expect(getProjectTokens(123)).rejects.toThrow('Network error');
    });
  });

  describe('getProjectCosts', () => {
    it('test_get_project_costs_success', async () => {
      // ARRANGE
      mockAuthFetch.mockResolvedValueOnce(mockCostBreakdown);

      // ACT
      const result = await getProjectCosts(123);

      // ASSERT
      expect(mockAuthFetch).toHaveBeenCalledWith(
        `${API_BASE_URL}/api/projects/123/metrics/costs`
      );
      expect(result).toEqual(mockCostBreakdown);
    });

    it('test_get_project_costs_error', async () => {
      // ARRANGE
      mockAuthFetch.mockRejectedValueOnce(
        new Error('Request failed: 500 Internal server error')
      );

      // ACT & ASSERT
      await expect(getProjectCosts(123)).rejects.toThrow(
        'Internal server error'
      );
    });
  });

  describe('getAgentMetrics', () => {
    it('test_get_agent_metrics_success', async () => {
      // ARRANGE
      mockAuthFetch.mockResolvedValueOnce(mockAgentMetrics);

      // ACT
      const result = await getAgentMetrics('backend-001', 123);

      // ASSERT
      expect(mockAuthFetch).toHaveBeenCalledWith(
        `${API_BASE_URL}/api/agents/backend-001/metrics?project_id=123`
      );
      expect(result).toEqual(mockAgentMetrics);
    });

    it('test_get_agent_metrics_without_project_id', async () => {
      // ARRANGE
      mockAuthFetch.mockResolvedValueOnce(mockAgentMetrics);

      // ACT
      const result = await getAgentMetrics('backend-001');

      // ASSERT
      expect(mockAuthFetch).toHaveBeenCalledWith(
        `${API_BASE_URL}/api/agents/backend-001/metrics`
      );
      expect(result).toEqual(mockAgentMetrics);
    });

    it('test_get_agent_metrics_error', async () => {
      // ARRANGE
      mockAuthFetch.mockRejectedValueOnce(
        new Error('Request failed: 404 Agent not found')
      );

      // ACT & ASSERT
      await expect(getAgentMetrics('backend-001')).rejects.toThrow(
        'Agent not found'
      );
    });
  });

  describe('getTokenUsageTimeSeries', () => {
    it('test_get_token_usage_time_series_success', async () => {
      // ARRANGE
      mockAuthFetch.mockResolvedValueOnce(mockTimeSeries);

      // ACT
      const result = await getTokenUsageTimeSeries(
        123,
        '2025-11-20T00:00:00Z',
        '2025-11-23T23:59:59Z',
        'day'
      );

      // ASSERT
      expect(mockAuthFetch).toHaveBeenCalledWith(
        `${API_BASE_URL}/api/projects/123/metrics/tokens/timeseries?start_date=2025-11-20T00%3A00%3A00Z&end_date=2025-11-23T23%3A59%3A59Z&interval=day`
      );
      expect(result).toEqual(mockTimeSeries);
    });

    it('test_get_token_usage_time_series_default_interval', async () => {
      // ARRANGE
      mockAuthFetch.mockResolvedValueOnce(mockTimeSeries);

      // ACT
      const result = await getTokenUsageTimeSeries(
        123,
        '2025-11-20T00:00:00Z',
        '2025-11-23T23:59:59Z'
      );

      // ASSERT
      expect(mockAuthFetch).toHaveBeenCalledWith(
        expect.stringContaining('interval=day')
      );
      expect(result).toEqual(mockTimeSeries);
    });

    it('test_get_token_usage_time_series_error', async () => {
      // ARRANGE
      mockAuthFetch.mockRejectedValueOnce(
        new Error('Request failed: 400 Invalid date range')
      );

      // ACT & ASSERT
      await expect(
        getTokenUsageTimeSeries(
          123,
          '2025-11-20T00:00:00Z',
          '2025-11-23T23:59:59Z'
        )
      ).rejects.toThrow('Invalid date range');
    });
  });

  describe('queryTokenUsage', () => {
    it('test_query_token_usage_all_params', async () => {
      // ARRANGE
      const mockTokens = [mockTokenUsage];
      mockAuthFetch.mockResolvedValueOnce(mockTokens);

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
      expect(mockAuthFetch).toHaveBeenCalledWith(
        `${API_BASE_URL}/api/metrics/tokens?project_id=123&agent_id=backend-001&start_date=2025-11-20T00%3A00%3A00Z&end_date=2025-11-23T23%3A59%3A59Z&call_type=task_execution&limit=50`
      );
      expect(result).toEqual(mockTokens);
    });

    it('test_query_token_usage_minimal_params', async () => {
      // ARRANGE
      const mockTokens = [mockTokenUsage];
      mockAuthFetch.mockResolvedValueOnce(mockTokens);

      // ACT
      const result = await queryTokenUsage({
        project_id: 123,
      });

      // ASSERT
      expect(mockAuthFetch).toHaveBeenCalledWith(
        `${API_BASE_URL}/api/metrics/tokens?project_id=123`
      );
      expect(result).toEqual(mockTokens);
    });

    it('test_query_token_usage_error', async () => {
      // ARRANGE
      mockAuthFetch.mockRejectedValueOnce(
        new Error('Request failed: 422 Invalid query parameters')
      );

      // ACT & ASSERT
      await expect(queryTokenUsage({ project_id: 123 })).rejects.toThrow(
        'Invalid query parameters'
      );
    });
  });

  describe('Error handling edge cases', () => {
    it('test_handles_not_authenticated', async () => {
      // ARRANGE
      mockAuthFetch.mockRejectedValueOnce(new Error('Not authenticated'));

      // ACT & ASSERT
      await expect(getProjectTokens(123)).rejects.toThrow('Not authenticated');
    });

    it('test_handles_network_timeout', async () => {
      // ARRANGE
      mockAuthFetch.mockRejectedValueOnce(new Error('Timeout'));

      // ACT & ASSERT
      await expect(getProjectCosts(123)).rejects.toThrow('Timeout');
    });
  });
});
