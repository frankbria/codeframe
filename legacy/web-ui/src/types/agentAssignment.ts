/**
 * Agent Assignment Type Definitions
 *
 * TypeScript interfaces for the multi-agent per project architecture.
 * These types support the many-to-many relationship between agents and projects.
 *
 * Phase: Multi-Agent Per Project Architecture (Phase 3)
 * Date: 2025-12-03
 */

// ============================================================================
// Request Types
// ============================================================================

/**
 * Request to assign an agent to a project
 */
export interface AgentAssignmentRequest {
  /** Agent ID to assign */
  agent_id: string;
  /** Agent's role in this project (e.g., 'primary_backend', 'code_reviewer') */
  role?: string;
}

/**
 * Request to update an agent's role on a project
 */
export interface AgentRoleUpdateRequest {
  /** New role for the agent (e.g., 'primary_backend', 'secondary_backend') */
  role: string;
}

// ============================================================================
// Response Types
// ============================================================================

/**
 * Agent assignment data from project perspective
 * Returned when querying agents for a specific project
 */
export interface AgentAssignment {
  /** Agent ID */
  agent_id: string;
  /** Agent type (lead, backend, frontend, test, review) */
  type: string;
  /** LLM provider (claude, gpt4) */
  provider: string | null;
  /** Agent maturity level */
  maturity_level: string | null;
  /** Agent status (idle, working, blocked, offline) */
  status: string | null;
  /** Current task ID if agent is working */
  current_task_id: number | null;
  /** Last activity timestamp (ISO 8601) */
  last_heartbeat: string | null;
  /** Role in this project */
  role: string;
  /** Assignment timestamp (ISO 8601) */
  assigned_at: string;
  /** Unassignment timestamp (ISO 8601) - null if still assigned */
  unassigned_at: string | null;
  /** Whether agent is currently assigned to project */
  is_active: boolean;
}

/**
 * Project assignment data from agent perspective
 * Returned when querying projects for a specific agent
 */
export interface ProjectAssignment {
  /** Project ID */
  project_id: number;
  /** Project name */
  name: string;
  /** Project description */
  description: string | null;
  /** Project status */
  status: string;
  /** Project phase */
  phase: string;
  /** Agent's role in this project */
  role: string;
  /** Assignment timestamp (ISO 8601) */
  assigned_at: string;
  /** Unassignment timestamp (ISO 8601) - null if still assigned */
  unassigned_at: string | null;
  /** Whether assignment is active */
  is_active: boolean;
}

/**
 * Response when assigning an agent to a project
 */
export interface AssignmentCreatedResponse {
  /** Assignment record ID */
  assignment_id: number;
  /** Success message */
  message: string;
}

// ============================================================================
// API Client Types
// ============================================================================

/**
 * Parameters for getting agents assigned to a project
 */
export interface GetAgentsForProjectParams {
  /** Project ID */
  project_id: number;
  /** Filter by active/inactive assignments */
  is_active?: boolean;
}

/**
 * Parameters for getting projects assigned to an agent
 */
export interface GetProjectsForAgentParams {
  /** Agent ID */
  agent_id: string;
  /** Filter by active/inactive assignments */
  is_active?: boolean;
}

/**
 * Parameters for unassigning an agent from a project
 */
export interface UnassignAgentParams {
  /** Project ID */
  project_id: number;
  /** Agent ID */
  agent_id: string;
}
