/**
 * API Client for Agent Assignment Operations
 *
 * Provides type-safe API calls for managing agent-to-project assignments
 * in the multi-agent per project architecture.
 *
 * Phase: Multi-Agent Per Project Architecture (Phase 3)
 * Date: 2025-12-03
 */

import { authFetch } from '@/lib/api-client';
import type {
  AgentAssignmentRequest,
  AgentRoleUpdateRequest,
  AgentAssignment,
  ProjectAssignment,
  AssignmentCreatedResponse,
} from '../types/agentAssignment';

/**
 * Base API URL (from environment or default to localhost)
 */
const API_BASE_URL =
  (typeof window !== 'undefined' &&
    (window as Window & { VITE_API_URL?: string }).VITE_API_URL) ||
  'http://localhost:8002';

/**
 * Get all agents assigned to a project
 *
 * @param projectId - Project ID
 * @param isActive - Filter by active/inactive assignments (optional)
 * @returns Array of agent assignments
 * @throws Error if API request fails
 */
export async function getAgentsForProject(
  projectId: number,
  isActive?: boolean
): Promise<AgentAssignment[]> {
  const params = new URLSearchParams();
  if (isActive !== undefined) {
    params.append('is_active', String(isActive));
  }

  const url = `${API_BASE_URL}/api/projects/${projectId}/agents${
    params.toString() ? `?${params.toString()}` : ''
  }`;

  return authFetch<AgentAssignment[]>(url);
}

/**
 * Assign an agent to a project
 *
 * @param projectId - Project ID
 * @param request - Agent assignment request (agent_id, role)
 * @returns Assignment created response
 * @throws Error if API request fails
 */
export async function assignAgentToProject(
  projectId: number,
  request: AgentAssignmentRequest
): Promise<AssignmentCreatedResponse> {
  return authFetch<AssignmentCreatedResponse>(
    `${API_BASE_URL}/api/projects/${projectId}/agents`,
    {
      method: 'POST',
      body: request,
    }
  );
}

/**
 * Unassign an agent from a project
 *
 * @param projectId - Project ID
 * @param agentId - Agent ID
 * @throws Error if API request fails
 */
export async function unassignAgentFromProject(
  projectId: number,
  agentId: string
): Promise<void> {
  await authFetch<void>(
    `${API_BASE_URL}/api/projects/${projectId}/agents/${agentId}`,
    { method: 'DELETE' }
  );
}

/**
 * Update an agent's role on a project
 *
 * @param projectId - Project ID
 * @param agentId - Agent ID
 * @param request - Role update request
 * @returns Updated assignment data
 * @throws Error if API request fails
 */
export async function updateAgentRole(
  projectId: number,
  agentId: string,
  request: AgentRoleUpdateRequest
): Promise<AgentAssignment> {
  return authFetch<AgentAssignment>(
    `${API_BASE_URL}/api/projects/${projectId}/agents/${agentId}/role`,
    {
      method: 'PUT',
      body: request,
    }
  );
}

/**
 * Get all projects assigned to an agent
 *
 * @param agentId - Agent ID
 * @param isActive - Filter by active/inactive assignments (optional)
 * @returns Array of project assignments
 * @throws Error if API request fails
 */
export async function getProjectsForAgent(
  agentId: string,
  isActive?: boolean
): Promise<ProjectAssignment[]> {
  const params = new URLSearchParams();
  if (isActive !== undefined) {
    params.append('is_active', String(isActive));
  }

  const url = `${API_BASE_URL}/api/agents/${agentId}/projects${
    params.toString() ? `?${params.toString()}` : ''
  }`;

  return authFetch<ProjectAssignment[]>(url);
}
