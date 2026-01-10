/**
 * Tests for phase-aware data utilities
 *
 * These utilities help components select the appropriate data source based on
 * project phase (planning vs development/review).
 *
 * Part of the "late-joining user" bug fix (Phase-Awareness Pattern)
 */

import {
  isPlanningPhase,
  extractTasksFromIssuesData,
  calculateProgressFromIssuesData,
  getPlanningPhaseMessage,
} from '../../src/lib/phaseAwareData';
import type { IssuesResponse, Issue, Task as ApiTask } from '../../src/types/api';

describe('phaseAwareData utilities', () => {
  // Sample issues data for testing
  const createMockIssue = (
    id: string,
    taskCount: number,
    taskStatuses: Array<'pending' | 'in_progress' | 'completed' | 'blocked'> = []
  ): Issue => ({
    id,
    issue_number: id,
    title: `Issue ${id}`,
    description: 'Test issue',
    status: 'pending',
    priority: 1,
    depends_on: [],
    proposed_by: 'agent',
    created_at: '2025-01-01T00:00:00Z',
    updated_at: '2025-01-01T00:00:00Z',
    completed_at: null,
    tasks: taskStatuses.length > 0
      ? taskStatuses.map((status, i) => ({
          id: `${id}-task-${i}`,
          task_number: `${id}.${i + 1}`,
          title: `Task ${i + 1}`,
          description: 'Test task',
          status,
          depends_on: [],
          proposed_by: 'agent' as const,
          created_at: '2025-01-01T00:00:00Z',
          updated_at: '2025-01-01T00:00:00Z',
          completed_at: status === 'completed' ? '2025-01-01T01:00:00Z' : null,
        }))
      : undefined,
  });

  const createMockIssuesResponse = (
    issues: Issue[],
    totalTasks: number
  ): IssuesResponse => ({
    issues,
    total_issues: issues.length,
    total_tasks: totalTasks,
  });

  describe('isPlanningPhase', () => {
    it('returns true for planning phase', () => {
      expect(isPlanningPhase('planning')).toBe(true);
    });

    it('returns false for development phase', () => {
      expect(isPlanningPhase('development')).toBe(false);
    });

    it('returns false for active phase (normalized development)', () => {
      expect(isPlanningPhase('active')).toBe(false);
    });

    it('returns false for review phase', () => {
      expect(isPlanningPhase('review')).toBe(false);
    });

    it('returns false for discovery phase', () => {
      expect(isPlanningPhase('discovery')).toBe(false);
    });

    it('returns false for complete phase', () => {
      expect(isPlanningPhase('complete')).toBe(false);
    });

    it('returns false for undefined phase', () => {
      expect(isPlanningPhase(undefined)).toBe(false);
    });

    it('returns false for empty string', () => {
      expect(isPlanningPhase('')).toBe(false);
    });
  });

  describe('extractTasksFromIssuesData', () => {
    it('extracts tasks from issues with nested tasks', () => {
      const issuesData = createMockIssuesResponse(
        [
          createMockIssue('1', 2, ['pending', 'completed']),
          createMockIssue('2', 1, ['in_progress']),
        ],
        3
      );

      const tasks = extractTasksFromIssuesData(issuesData);

      expect(tasks).toHaveLength(3);
      expect(tasks[0]).toMatchObject({
        id: '1-task-0',
        status: 'pending',
      });
      expect(tasks[1]).toMatchObject({
        id: '1-task-1',
        status: 'completed',
      });
      expect(tasks[2]).toMatchObject({
        id: '2-task-0',
        status: 'in_progress',
      });
    });

    it('returns empty array for undefined issuesData', () => {
      expect(extractTasksFromIssuesData(undefined)).toEqual([]);
    });

    it('returns empty array for issues without tasks arrays', () => {
      const issuesData = createMockIssuesResponse(
        [createMockIssue('1', 0)],
        0
      );

      const tasks = extractTasksFromIssuesData(issuesData);
      expect(tasks).toEqual([]);
    });

    it('handles mixed issues with and without tasks', () => {
      const issueWithTasks = createMockIssue('1', 2, ['pending', 'completed']);
      const issueWithoutTasks = createMockIssue('2', 0);

      const issuesData = createMockIssuesResponse(
        [issueWithTasks, issueWithoutTasks],
        2
      );

      const tasks = extractTasksFromIssuesData(issuesData);
      expect(tasks).toHaveLength(2);
    });

    it('preserves all task properties', () => {
      const issuesData = createMockIssuesResponse(
        [createMockIssue('1', 1, ['completed'])],
        1
      );

      const tasks = extractTasksFromIssuesData(issuesData);
      expect(tasks[0]).toHaveProperty('id');
      expect(tasks[0]).toHaveProperty('task_number');
      expect(tasks[0]).toHaveProperty('title');
      expect(tasks[0]).toHaveProperty('description');
      expect(tasks[0]).toHaveProperty('status');
      expect(tasks[0]).toHaveProperty('depends_on');
      expect(tasks[0]).toHaveProperty('proposed_by');
      expect(tasks[0]).toHaveProperty('created_at');
      expect(tasks[0]).toHaveProperty('updated_at');
      expect(tasks[0]).toHaveProperty('completed_at');
    });
  });

  describe('calculateProgressFromIssuesData', () => {
    it('calculates progress from total_tasks field', () => {
      const issuesData = createMockIssuesResponse([], 10);

      const progress = calculateProgressFromIssuesData(issuesData);

      expect(progress).toEqual({
        totalTasks: 10,
        completedTasks: 0,
        percentage: 0,
      });
    });

    it('counts completed tasks from nested task arrays', () => {
      const issuesData = createMockIssuesResponse(
        [
          createMockIssue('1', 3, ['completed', 'completed', 'pending']),
          createMockIssue('2', 2, ['completed', 'in_progress']),
        ],
        5
      );

      const progress = calculateProgressFromIssuesData(issuesData);

      expect(progress).toEqual({
        totalTasks: 5,
        completedTasks: 3,
        percentage: 60,
      });
    });

    it('returns zero progress for undefined issuesData', () => {
      const progress = calculateProgressFromIssuesData(undefined);

      expect(progress).toEqual({
        totalTasks: 0,
        completedTasks: 0,
        percentage: 0,
      });
    });

    it('handles 100% completion', () => {
      const issuesData = createMockIssuesResponse(
        [createMockIssue('1', 3, ['completed', 'completed', 'completed'])],
        3
      );

      const progress = calculateProgressFromIssuesData(issuesData);

      expect(progress).toEqual({
        totalTasks: 3,
        completedTasks: 3,
        percentage: 100,
      });
    });

    it('handles empty issues array with total_tasks', () => {
      // This replicates the production scenario where API returns total_tasks
      // but doesn't populate nested task arrays
      const issuesData: IssuesResponse = {
        issues: [],
        total_issues: 0,
        total_tasks: 24,
      };

      const progress = calculateProgressFromIssuesData(issuesData);

      expect(progress).toEqual({
        totalTasks: 24,
        completedTasks: 0,
        percentage: 0,
      });
    });

    it('handles undefined total_tasks gracefully', () => {
      const issuesData = {
        issues: [],
        total_issues: 0,
      } as unknown as IssuesResponse;

      const progress = calculateProgressFromIssuesData(issuesData);

      expect(progress).toEqual({
        totalTasks: 0,
        completedTasks: 0,
        percentage: 0,
      });
    });

    it('clamps percentage to 0-100 range', () => {
      // Edge case: more completed tasks than total (shouldn't happen, but be safe)
      const issuesData = createMockIssuesResponse(
        [createMockIssue('1', 5, ['completed', 'completed', 'completed', 'completed', 'completed'])],
        3 // total_tasks is less than actual completed (edge case)
      );

      const progress = calculateProgressFromIssuesData(issuesData);

      // Should cap at 100%
      expect(progress.percentage).toBeLessThanOrEqual(100);
    });
  });

  describe('getPlanningPhaseMessage', () => {
    it('returns agent message for agent-list component', () => {
      const message = getPlanningPhaseMessage('agent-list');
      expect(message).toBe('Agents will be created automatically when development begins');
    });

    it('returns quality-gates message', () => {
      const message = getPlanningPhaseMessage('quality-gates');
      expect(message).toBe('Quality gates will be evaluated during development phase');
    });

    it('returns cost-dashboard message', () => {
      const message = getPlanningPhaseMessage('cost-dashboard');
      expect(message).toBe('Cost metrics will be available during development phase');
    });

    it('returns task count message with issuesData', () => {
      const issuesData = createMockIssuesResponse([], 24);
      const message = getPlanningPhaseMessage('agent-list', issuesData);
      expect(message).toContain('24');
      expect(message).toContain('tasks');
    });

    it('returns generic message for unknown component', () => {
      const message = getPlanningPhaseMessage('unknown-component');
      expect(message).toBe('This feature is available during development phase');
    });
  });
});
