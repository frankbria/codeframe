/**
 * TypeScript types for Review Agent functionality (Sprint 10 Phase 2)
 *
 * Maps to backend Pydantic models in codeframe/core/models.py
 * Tasks: T039
 */

import {
  LockIcon,
  FlashIcon,
  SparklesIcon,
  Settings01Icon,
  PaintBrush01Icon,
} from '@hugeicons/react';

/**
 * Severity enum matching backend Severity enum
 */
export enum Severity {
  CRITICAL = "critical",
  HIGH = "high",
  MEDIUM = "medium",
  LOW = "low",
  INFO = "info",
}

/**
 * Review category enum matching backend ReviewCategory enum
 */
export enum ReviewCategory {
  SECURITY = "security",
  PERFORMANCE = "performance",
  QUALITY = "quality",
  MAINTAINABILITY = "maintainability",
  STYLE = "style",
}

/**
 * Code review finding interface matching backend CodeReview model
 */
export interface CodeReview {
  /** Unique ID of the review finding */
  id?: number;

  /** Task ID this review is associated with */
  task_id: number;

  /** Agent ID that performed the review */
  agent_id: string;

  /** Project ID */
  project_id: number;

  /** Relative path from project root */
  file_path: string;

  /** Line number (null for file-level findings) */
  line_number: number | null;

  /** Severity level */
  severity: Severity;

  /** Category of the finding */
  category: ReviewCategory;

  /** Description of the issue */
  message: string;

  /** Optional recommendation for fixing */
  recommendation: string | null;

  /** Optional code snippet for context */
  code_snippet: string | null;

  /** ISO timestamp when review was created */
  created_at: string;
}

/**
 * Review result containing findings list and blocking status
 */
export interface ReviewResult {
  /** List of all review findings */
  findings: CodeReview[];

  /** Total count of findings */
  total_count: number;

  /** Count by severity */
  severity_counts: {
    critical: number;
    high: number;
    medium: number;
    low: number;
    info: number;
  };

  /** Count by category */
  category_counts: {
    security: number;
    performance: number;
    quality: number;
    maintainability: number;
    style: number;
  };

  /** Whether critical or high severity findings exist */
  has_blocking_findings: boolean;

  /** Task ID reviewed */
  task_id: number;
}

/**
 * Severity color mapping for UI (Nova palette)
 */
export const SEVERITY_COLORS: Record<Severity, string> = {
  [Severity.CRITICAL]: "bg-destructive text-destructive-foreground border-destructive",
  [Severity.HIGH]: "bg-destructive/80 text-destructive-foreground border-destructive",
  [Severity.MEDIUM]: "bg-muted text-foreground border-border",
  [Severity.LOW]: "bg-secondary text-secondary-foreground border-border",
  [Severity.INFO]: "bg-muted text-muted-foreground border-border",
};

/**
 * Category icon component mapping for UI
 * Returns React components for each review category
 */
export function getCategoryIcon(category: ReviewCategory): JSX.Element {
  const iconProps = { className: 'h-4 w-4', 'aria-hidden': true as const };
  switch (category) {
    case ReviewCategory.SECURITY:
      return <LockIcon {...iconProps} />;
    case ReviewCategory.PERFORMANCE:
      return <FlashIcon {...iconProps} />;
    case ReviewCategory.QUALITY:
      return <SparklesIcon {...iconProps} />;
    case ReviewCategory.MAINTAINABILITY:
      return <Settings01Icon {...iconProps} />;
    case ReviewCategory.STYLE:
      return <PaintBrush01Icon {...iconProps} />;
    default:
      return <SparklesIcon {...iconProps} />;
  }
}

/**
 * Category icon mapping for UI (deprecated - use getCategoryIcon() instead)
 * @deprecated Use getCategoryIcon() function for proper React component rendering
 */
export const CATEGORY_ICONS: Record<ReviewCategory, string> = {
  [ReviewCategory.SECURITY]: "🔒",
  [ReviewCategory.PERFORMANCE]: "⚡",
  [ReviewCategory.QUALITY]: "✨",
  [ReviewCategory.MAINTAINABILITY]: "🔧",
  [ReviewCategory.STYLE]: "🎨",
};
