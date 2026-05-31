/**
 * TypeScript types for CodeFRAME PRD and Discovery API responses.
 *
 * These mirror the Pydantic models in:
 *   - codeframe/ui/routers/prd_v2.py
 *   - codeframe/ui/routers/discovery_v2.py
 */

// ---------------------------------------------------------------------------
// PRD types
// ---------------------------------------------------------------------------

export interface PrdResponse {
  id: string;
  workspace_id: string;
  title: string;
  content: string;
  metadata: Record<string, unknown>;
  created_at: string;
  version: number;
  parent_id: string | null;
  change_summary: string | null;
  chain_id: string | null;
}

export interface PrdSummaryResponse {
  id: string;
  workspace_id: string;
  title: string;
  created_at: string;
  version: number;
  chain_id: string | null;
}

export interface PrdListResponse {
  prds: PrdSummaryResponse[];
  total: number;
}

export interface PrdDiffResponse {
  version1: number;
  version2: number;
  diff: string;
}

// ---------------------------------------------------------------------------
// Discovery types
// ---------------------------------------------------------------------------

export interface StartDiscoveryResponse {
  session_id: string;
  state: string;
  question: Record<string, unknown>;
}

export interface AnswerResponse {
  accepted: boolean;
  feedback: string;
  follow_up: string | null;
  is_complete: boolean;
  next_question: Record<string, unknown> | null;
  coverage: Record<string, unknown> | null;
}

export interface DiscoveryStatusResponse {
  state: string;
  session_id: string | null;
  progress: Record<string, unknown>;
  current_question: Record<string, unknown> | null;
  error: string | null;
}

export interface GeneratePrdResponse {
  prd_id: string;
  title: string;
  preview: string;
}

export interface GenerateTasksResponse {
  task_count: number;
  tasks: Record<string, unknown>[];
}

// ---------------------------------------------------------------------------
// UI-specific types (not direct API mirrors)
// ---------------------------------------------------------------------------

export type DiscoveryRole = 'user' | 'assistant';

export interface DiscoveryMessage {
  role: DiscoveryRole;
  content: string;
  timestamp: string;
}

export type DiscoveryState = 'idle' | 'discovering' | 'completed';

// ---------------------------------------------------------------------------
// PRD stress-test SSE event types (mirror stress_test_prd_stream in
// codeframe/core/prd_stress_test.py, streamed by GET /api/v2/prd/stress-test)
// ---------------------------------------------------------------------------

export type StressTestEventType =
  | 'goals_extracted'
  | 'goal_analyzed'
  | 'complete'
  | 'error';

export interface StressTestGoalsExtractedEvent {
  type: 'goals_extracted';
  goals: string[];
}

export interface StressTestGoalAnalyzedEvent {
  type: 'goal_analyzed';
  goal: string;
  classification: 'atomic' | 'composite' | 'ambiguous';
  ambiguities_so_far: number;
}

export type AmbiguitySeverity = 'blocking' | 'warning';

/** A single ambiguity surfaced by the stress-test, rendered as an answerable
 *  card in the results view (issue #562). Mirrors `ambiguity_to_dict` in
 *  codeframe/core/prd_stress_test.py. */
export interface StressTestAmbiguity {
  id: string;
  label: string;
  source_node_title: string;
  questions: string[];
  recommendation: string;
  severity: AmbiguitySeverity;
  resolved_answer: string | null;
}

export interface StressTestCompleteEvent {
  type: 'complete';
  ambiguity_count: number;
  ambiguities: StressTestAmbiguity[];
  tech_spec_markdown: string;
  ambiguity_report: string;
}

export interface StressTestErrorEvent {
  type: 'error';
  message: string;
}

export type StressTestEvent =
  | StressTestGoalsExtractedEvent
  | StressTestGoalAnalyzedEvent
  | StressTestCompleteEvent
  | StressTestErrorEvent;
