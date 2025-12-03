/**
 * API Client for Agent Assignment Operations
 *
 * Provides type-safe API calls for managing agent-to-project assignments
 * in the multi-agent per project architecture.
 *
 * Phase: Multi-Agent Per Project Architecture (Phase 3)
 * Date: 2025-12-03
 */

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
  (typeof window !== 'undefined' && (window as any).VITE_API_URL) ||
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

  const response = await fetch(url, {
    method: 'GET',
    headers: {
      'Content-Type': 'application/json',
    },
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(
      errorData.detail || `Failed to fetch agents for project ${projectId}`
    );
  }

  return response.json();
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
  const response = await fetch(
    `${API_BASE_URL}/api/projects/${projectId}/agents`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(request),
    }
  );

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(
      errorData.detail || `Failed to assign agent to project ${projectId}`
    );
  }

  return response.json();
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
  const response = await fetch(
    `${API_BASE_URL}/api/projects/${projectId}/agents/${agentId}`,
    {
      method: 'DELETE',
      headers: {
        'Content-Type': 'application/json',
      },
    }
  );

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(
      errorData.detail ||
        `Failed to unassign agent ${agentId} from project ${projectId}`
    );
  }
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
  const response = await fetch(
    `${API_BASE_URL}/api/projects/${projectId}/agents/${agentId}/role`,
    {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(request),
    }
  );

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(
      errorData.detail ||
        `Failed to update role for agent ${agentId} on project ${projectId}`
    );
  }

  return response.json();
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

  const response = await fetch(url, {
    method: 'GET',
    headers: {
      'Content-Type': 'application/json',
    },
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(
      errorData.detail || `Failed to fetch projects for agent ${agentId}`
    );
  }

  return response.json();
}
