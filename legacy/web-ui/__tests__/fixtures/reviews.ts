/**
 * Test fixtures for review data (Sprint 10 Phase 2)
 * Used across review component tests
 */

import type { CodeReview, ReviewResult } from '@/types/reviews';
import { Severity, ReviewCategory } from '@/types/reviews';

/**
 * Mock critical security finding
 */
export const mockCriticalSecurityFinding: CodeReview = {
  id: 1,
  task_id: 123,
  agent_id: 'review-agent-001',
  project_id: 1,
  file_path: 'src/auth/login.ts',
  line_number: 45,
  severity: Severity.CRITICAL,
  category: ReviewCategory.SECURITY,
  message: 'SQL injection vulnerability detected in login query',
  recommendation: 'Use parameterized queries instead of string concatenation',
  code_snippet: 'const query = `SELECT * FROM users WHERE username="${username}"`',
  created_at: '2025-11-23T10:00:00Z',
};

/**
 * Mock high performance finding
 */
export const mockHighPerformanceFinding: CodeReview = {
  id: 2,
  task_id: 123,
  agent_id: 'review-agent-001',
  project_id: 1,
  file_path: 'src/utils/data.ts',
  line_number: 120,
  severity: Severity.HIGH,
  category: ReviewCategory.PERFORMANCE,
  message: 'N+1 query detected in loop - fetching user data for each item',
  recommendation: 'Batch fetch all user IDs before the loop',
  code_snippet: null,
  created_at: '2025-11-23T10:01:00Z',
};

/**
 * Mock medium quality finding
 */
export const mockMediumQualityFinding: CodeReview = {
  id: 3,
  task_id: 123,
  agent_id: 'review-agent-001',
  project_id: 1,
  file_path: 'src/components/Dashboard.tsx',
  line_number: 200,
  severity: Severity.MEDIUM,
  category: ReviewCategory.QUALITY,
  message: 'Component complexity exceeds threshold (cyclomatic complexity: 15)',
  recommendation: 'Split into smaller sub-components',
  code_snippet: null,
  created_at: '2025-11-23T10:02:00Z',
};

/**
 * Mock low maintainability finding
 */
export const mockLowMaintainabilityFinding: CodeReview = {
  id: 4,
  task_id: 123,
  agent_id: 'review-agent-001',
  project_id: 1,
  file_path: 'src/lib/utils.ts',
  line_number: 78,
  severity: Severity.LOW,
  category: ReviewCategory.MAINTAINABILITY,
  message: 'Magic number detected - use named constant',
  recommendation: 'Define constant MAX_RETRY_ATTEMPTS = 3',
  code_snippet: 'const maxRetries = 3; // Magic number',
  created_at: '2025-11-23T10:03:00Z',
};

/**
 * Mock info style finding
 */
export const mockInfoStyleFinding: CodeReview = {
  id: 5,
  task_id: 123,
  agent_id: 'review-agent-001',
  project_id: 1,
  file_path: 'src/api/client.ts',
  line_number: null,
  severity: Severity.INFO,
  category: ReviewCategory.STYLE,
  message: 'Consider adding JSDoc comments to exported functions',
  recommendation: null,
  code_snippet: null,
  created_at: '2025-11-23T10:04:00Z',
};

/**
 * Mock finding without line number (file-level)
 */
export const mockFileLevelFinding: CodeReview = {
  id: 6,
  task_id: 123,
  agent_id: 'review-agent-001',
  project_id: 1,
  file_path: 'src/config/database.ts',
  line_number: null,
  severity: Severity.HIGH,
  category: ReviewCategory.SECURITY,
  message: 'Database credentials hardcoded in source file',
  recommendation: 'Move credentials to environment variables',
  code_snippet: null,
  created_at: '2025-11-23T10:05:00Z',
};

/**
 * All mock findings
 */
export const mockAllFindings: CodeReview[] = [
  mockCriticalSecurityFinding,
  mockHighPerformanceFinding,
  mockMediumQualityFinding,
  mockLowMaintainabilityFinding,
  mockInfoStyleFinding,
  mockFileLevelFinding,
];

/**
 * Mock review result with blocking findings
 */
export const mockReviewResultBlocking: ReviewResult = {
  findings: mockAllFindings,
  total_count: 6,
  severity_counts: {
    critical: 1,
    high: 2,
    medium: 1,
    low: 1,
    info: 1,
  },
  category_counts: {
    security: 2,
    performance: 1,
    quality: 1,
    maintainability: 1,
    style: 1,
  },
  has_blocking_findings: true,
  task_id: 123,
};

/**
 * Mock review result without blocking findings (only low/info)
 */
export const mockReviewResultNonBlocking: ReviewResult = {
  findings: [mockLowMaintainabilityFinding, mockInfoStyleFinding],
  total_count: 2,
  severity_counts: {
    critical: 0,
    high: 0,
    medium: 0,
    low: 1,
    info: 1,
  },
  category_counts: {
    security: 0,
    performance: 0,
    quality: 0,
    maintainability: 1,
    style: 1,
  },
  has_blocking_findings: false,
  task_id: 123,
};

/**
 * Mock empty review result (no findings)
 */
export const mockReviewResultEmpty: ReviewResult = {
  findings: [],
  total_count: 0,
  severity_counts: {
    critical: 0,
    high: 0,
    medium: 0,
    low: 0,
    info: 0,
  },
  category_counts: {
    security: 0,
    performance: 0,
    quality: 0,
    maintainability: 0,
    style: 0,
  },
  has_blocking_findings: false,
  task_id: 123,
};

/**
 * Mock critical-only findings
 */
export const mockCriticalOnlyFindings: CodeReview[] = [
  mockCriticalSecurityFinding,
];

/**
 * Mock high-only findings
 */
export const mockHighOnlyFindings: CodeReview[] = [
  mockHighPerformanceFinding,
  mockFileLevelFinding,
];

/**
 * Mock medium-only findings
 */
export const mockMediumOnlyFindings: CodeReview[] = [
  mockMediumQualityFinding,
];
