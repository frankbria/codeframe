/**
 * API client for metrics and cost tracking operations (T133)
 *
 * Part of 015-review-polish Phase 5 (Sprint 10 - Metrics & Cost Tracking)
 */

import type {
  TokenUsage,
  CostBreakdown,
  AgentMetrics,
  TokenUsageTimeSeries,
  TokenUsageQueryParams,
} from '../types/metrics';

/**
 * Base API URL - defaults to localhost in development
 */
const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

/**
 * Fetch token usage records for a project
 *
 * @param projectId - Project ID to get token usage for
 * @param startDate - Optional start date (ISO string)
 * @param endDate - Optional end date (ISO string)
 * @param limit - Maximum number of records to return (default 100)
 * @returns Promise resolving to array of TokenUsage records
 * @throws Error if request fails
 */
export async function getProjectTokens(
  projectId: number,
  startDate?: string,
  endDate?: string,
  limit: number = 100
): Promise<TokenUsage[]> {
  const params = new URLSearchParams();

  if (startDate) {
    params.append('start_date', startDate);
  }

  if (endDate) {
    params.append('end_date', endDate);
  }

  params.append('limit', limit.toString());

  const url = `${API_BASE_URL}/api/projects/${projectId}/metrics/tokens${
    params.toString() ? `?${params.toString()}` : ''
  }`;

  const response = await fetch(url, {
    method: 'GET',
    headers: {
      'Content-Type': 'application/json',
    },
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(
      `Failed to fetch project tokens: ${response.status} ${errorText}`
    );
  }

  return response.json();
}

/**
 * Fetch cost metrics and breakdown for a project
 *
 * @param projectId - Project ID to get costs for
 * @returns Promise resolving to CostBreakdown
 * @throws Error if request fails
 */
export async function getProjectCosts(
  projectId: number
): Promise<CostBreakdown> {
  const response = await fetch(
    `${API_BASE_URL}/api/projects/${projectId}/metrics/costs`,
    {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
    }
  );

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(
      `Failed to fetch project costs: ${response.status} ${errorText}`
    );
  }

  return response.json();
}

/**
 * Fetch metrics for a specific agent
 *
 * @param agentId - Agent ID to get metrics for
 * @param projectId - Optional project ID to filter by
 * @returns Promise resolving to AgentMetrics
 * @throws Error if request fails
 */
export async function getAgentMetrics(
  agentId: string,
  projectId?: number
): Promise<AgentMetrics> {
  const params = new URLSearchParams();

  if (projectId !== undefined) {
    params.append('project_id', projectId.toString());
  }

  const url = `${API_BASE_URL}/api/agents/${agentId}/metrics${
    params.toString() ? `?${params.toString()}` : ''
  }`;

  const response = await fetch(url, {
    method: 'GET',
    headers: {
      'Content-Type': 'application/json',
    },
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(
      `Failed to fetch agent metrics: ${response.status} ${errorText}`
    );
  }

  return response.json();
}

/**
 * Fetch token usage time series data for charting
 *
 * @param projectId - Project ID to get time series for
 * @param startDate - Start date (ISO string)
 * @param endDate - End date (ISO string)
 * @param interval - Time interval ('hour', 'day', 'week', default 'day')
 * @returns Promise resolving to array of TokenUsageTimeSeries
 * @throws Error if request fails
 */
export async function getTokenUsageTimeSeries(
  projectId: number,
  startDate: string,
  endDate: string,
  interval: 'hour' | 'day' | 'week' = 'day'
): Promise<TokenUsageTimeSeries[]> {
  const params = new URLSearchParams({
    start_date: startDate,
    end_date: endDate,
    interval,
  });

  const response = await fetch(
    `${API_BASE_URL}/api/projects/${projectId}/metrics/tokens/timeseries?${params.toString()}`,
    {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
    }
  );

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(
      `Failed to fetch token usage time series: ${response.status} ${errorText}`
    );
  }

  return response.json();
}

/**
 * Query token usage with flexible filters
 *
 * @param params - Query parameters
 * @returns Promise resolving to array of TokenUsage records
 * @throws Error if request fails
 */
export async function queryTokenUsage(
  params: TokenUsageQueryParams
): Promise<TokenUsage[]> {
  const searchParams = new URLSearchParams();

  if (params.project_id !== undefined) {
    searchParams.append('project_id', params.project_id.toString());
  }

  if (params.agent_id) {
    searchParams.append('agent_id', params.agent_id);
  }

  if (params.start_date) {
    searchParams.append('start_date', params.start_date);
  }

  if (params.end_date) {
    searchParams.append('end_date', params.end_date);
  }

  if (params.call_type) {
    searchParams.append('call_type', params.call_type);
  }

  if (params.limit !== undefined) {
    searchParams.append('limit', params.limit.toString());
  }

  const response = await fetch(
    `${API_BASE_URL}/api/metrics/tokens?${searchParams.toString()}`,
    {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
    }
  );

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(
      `Failed to query token usage: ${response.status} ${errorText}`
    );
  }

  return response.json();
}
