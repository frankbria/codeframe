/**
 * TypeScript types for context management (T062)
 *
 * Part of 007-context-management Phase 7 (US5 - Context Visualization)
 */

/**
 * Context tier levels for agent memory management
 */
export type ContextTier = 'HOT' | 'WARM' | 'COLD';

/**
 * Individual context item stored for an agent
 */
export interface ContextItem {
  /** Unique identifier for the context item */
  id: number;

  /** Project ID this context belongs to */
  project_id: number;

  /** Agent ID that owns this context */
  agent_id: string;

  /** Type of context item (TASK, CODE, PRD_SECTION, etc.) */
  item_type: string;

  /** Actual content of the context item */
  content: string;

  /** Importance score (0.0 - 1.0) */
  importance_score: number;

  /** Current tier assignment */
  current_tier: ContextTier;

  /** Number of times this item has been accessed */
  access_count: number;

  /** ISO timestamp when item was created */
  created_at: string;

  /** ISO timestamp when item was last accessed */
  last_accessed: string;
}

/**
 * Statistics about an agent's context breakdown
 */
export interface ContextStats {
  /** Agent ID these stats belong to */
  agent_id: string;

  /** Project ID */
  project_id: number;

  /** Number of HOT tier items */
  hot_count: number;

  /** Number of WARM tier items */
  warm_count: number;

  /** Number of COLD tier items */
  cold_count: number;

  /** Total number of context items */
  total_count: number;

  /** Number of tokens in HOT tier */
  hot_tokens: number;

  /** Number of tokens in WARM tier */
  warm_tokens: number;

  /** Number of tokens in COLD tier */
  cold_tokens: number;

  /** Total tokens across all tiers */
  total_tokens: number;

  /** Percentage of token limit used (0-100) */
  token_usage_percentage: number;

  /** ISO timestamp when stats were calculated */
  calculated_at: string;
}

/**
 * Response from flash save operation
 */
export interface FlashSaveResponse {
  /** ID of the created checkpoint */
  checkpoint_id: number;

  /** Token count before archival */
  tokens_before: number;

  /** Token count after archival */
  tokens_after: number;

  /** Percentage reduction in tokens */
  reduction_percentage: number;

  /** Number of items archived (deleted) */
  items_archived: number;

  /** Number of HOT items retained */
  hot_items_retained: number;

  /** Number of WARM items retained */
  warm_items_retained: number;
}

/**
 * Checkpoint metadata (without full checkpoint_data)
 */
export interface CheckpointMetadata {
  /** Unique checkpoint ID */
  id: number;

  /** Agent ID this checkpoint belongs to */
  agent_id: string;

  /** Total number of items when checkpoint was created */
  items_count: number;

  /** Number of items archived during flash save */
  items_archived: number;

  /** Number of HOT items retained */
  hot_items_retained: number;

  /** Total token count when checkpoint was created */
  token_count: number;

  /** ISO timestamp when checkpoint was created */
  created_at: string;
}
