/**
 * Unit tests for WebSocket message mapper
 *
 * Tests the mapping of WebSocket messages from backend format to reducer actions.
 * Covers all message types (T050-T061).
 */

import { mapWebSocketMessageToAction } from '@/lib/websocketMessageMapper';

describe('mapWebSocketMessageToAction', () => {
  const projectId = 1;
  const baseTimestamp = 1699999999000;

  describe('agent_created message (T050)', () => {
    it('should map agent_created message with all fields', () => {
      const message = {
        type: 'agent_created' as const,
        project_id: projectId,
        timestamp: baseTimestamp,
        agent_id: 'backend-worker-1',
        agent_type: 'backend-worker',
        provider: 'anthropic',
      };

      const action = mapWebSocketMessageToAction(message);

      expect(action).toEqual({
        type: 'AGENT_CREATED',
        payload: {
          id: 'backend-worker-1',
          type: 'backend-worker',
          status: 'idle',
          provider: 'anthropic',
          maturity: 'directive',
          context_tokens: 0,
          tasks_completed: 0,
          timestamp: baseTimestamp,
        },
      });
    });

    it('should default provider to "anthropic" if not provided', () => {
      const message = {
        type: 'agent_created' as const,
        project_id: projectId,
        timestamp: baseTimestamp,
        agent_id: 'lead-1',
        agent_type: 'lead',
      };

      const action = mapWebSocketMessageToAction(message);

      expect(action?.payload).toMatchObject({
        provider: 'anthropic',
      });
    });

    it('should parse string timestamp to number', () => {
      const message = {
        type: 'agent_created' as const,
        project_id: projectId,
        timestamp: '2023-11-14T12:00:00Z',
        agent_id: 'test-engineer-1',
        agent_type: 'test-engineer',
      };

      const action = mapWebSocketMessageToAction(message);

      expect(action?.payload).toMatchObject({
        timestamp: expect.any(Number),
      });
      expect((action?.payload as any).timestamp).toBeGreaterThan(0);
    });
  });

  describe('agent_status_changed message (T051)', () => {
    it('should map agent_status_changed message with status only', () => {
      const message = {
        type: 'agent_status_changed' as const,
        project_id: projectId,
        timestamp: baseTimestamp,
        agent_id: 'backend-worker-1',
        status: 'working',
      };

      const action = mapWebSocketMessageToAction(message);

      expect(action).toEqual({
        type: 'AGENT_UPDATED',
        payload: {
          agentId: 'backend-worker-1',
          updates: {
            status: 'working',
          },
          timestamp: baseTimestamp,
        },
      });
    });

    it('should include current_task when provided', () => {
      const message = {
        type: 'agent_status_changed' as const,
        project_id: projectId,
        timestamp: baseTimestamp,
        agent_id: 'frontend-specialist-1',
        status: 'working',
        current_task: {
          id: 123,
          title: 'Build dashboard component',
        },
      };

      const action = mapWebSocketMessageToAction(message);

      expect(action?.payload).toMatchObject({
        updates: {
          status: 'working',
          current_task: {
            id: 123,
            title: 'Build dashboard component',
          },
        },
      });
    });

    it('should include progress when provided', () => {
      const message = {
        type: 'agent_status_changed' as const,
        project_id: projectId,
        timestamp: baseTimestamp,
        agent_id: 'test-engineer-1',
        status: 'working',
        progress: 75,
      };

      const action = mapWebSocketMessageToAction(message);

      expect(action?.payload).toMatchObject({
        updates: {
          status: 'working',
          progress: 75,
        },
      });
    });
  });

  describe('agent_retired message (T052)', () => {
    it('should map agent_retired message', () => {
      const message = {
        type: 'agent_retired' as const,
        project_id: projectId,
        timestamp: baseTimestamp,
        agent_id: 'backend-worker-1',
      };

      const action = mapWebSocketMessageToAction(message);

      expect(action).toEqual({
        type: 'AGENT_RETIRED',
        payload: {
          agentId: 'backend-worker-1',
          timestamp: baseTimestamp,
        },
      });
    });
  });

  describe('task_assigned message (T053)', () => {
    it('should map task_assigned message with task title', () => {
      const message = {
        type: 'task_assigned' as const,
        project_id: projectId,
        timestamp: baseTimestamp,
        task_id: 456,
        agent_id: 'backend-worker-1',
        task_title: 'Implement authentication',
      };

      const action = mapWebSocketMessageToAction(message);

      expect(action).toEqual({
        type: 'TASK_ASSIGNED',
        payload: {
          taskId: 456,
          agentId: 'backend-worker-1',
          taskTitle: 'Implement authentication',
          projectId: projectId,
          timestamp: baseTimestamp,
        },
      });
    });

    it('should handle task_assigned without task title', () => {
      const message = {
        type: 'task_assigned' as const,
        project_id: projectId,
        timestamp: baseTimestamp,
        task_id: 789,
        agent_id: 'frontend-specialist-1',
      };

      const action = mapWebSocketMessageToAction(message);

      expect(action).toEqual({
        type: 'TASK_ASSIGNED',
        payload: {
          taskId: 789,
          agentId: 'frontend-specialist-1',
          taskTitle: undefined,
          projectId: projectId,
          timestamp: baseTimestamp,
        },
      });
    });
  });

  describe('task_status_changed message (T054)', () => {
    it('should map task_status_changed message with progress', () => {
      const message = {
        type: 'task_status_changed' as const,
        project_id: projectId,
        timestamp: baseTimestamp,
        task_id: 123,
        status: 'in_progress',
        progress: 50,
      };

      const action = mapWebSocketMessageToAction(message);

      expect(action).toEqual({
        type: 'TASK_STATUS_CHANGED',
        payload: {
          taskId: 123,
          status: 'in_progress',
          progress: 50,
          timestamp: baseTimestamp,
        },
      });
    });

    it('should map task_status_changed without progress', () => {
      const message = {
        type: 'task_status_changed' as const,
        project_id: projectId,
        timestamp: baseTimestamp,
        task_id: 456,
        status: 'completed',
      };

      const action = mapWebSocketMessageToAction(message);

      expect(action).toEqual({
        type: 'TASK_STATUS_CHANGED',
        payload: {
          taskId: 456,
          status: 'completed',
          progress: undefined,
          timestamp: baseTimestamp,
        },
      });
    });
  });

  describe('task_blocked and task_unblocked messages (T055)', () => {
    it('should map task_blocked message', () => {
      const message = {
        type: 'task_blocked' as const,
        project_id: projectId,
        timestamp: baseTimestamp,
        task_id: 789,
        blocked_by: [123, 456],
      };

      const action = mapWebSocketMessageToAction(message);

      expect(action).toEqual({
        type: 'TASK_BLOCKED',
        payload: {
          taskId: 789,
          blockedBy: [123, 456],
          timestamp: baseTimestamp,
        },
      });
    });

    it('should map task_unblocked message', () => {
      const message = {
        type: 'task_unblocked' as const,
        project_id: projectId,
        timestamp: baseTimestamp,
        task_id: 789,
      };

      const action = mapWebSocketMessageToAction(message);

      expect(action).toEqual({
        type: 'TASK_UNBLOCKED',
        payload: {
          taskId: 789,
          timestamp: baseTimestamp,
        },
      });
    });
  });

  describe('activity_update message (T056)', () => {
    it('should map activity_update message with all fields', () => {
      const message = {
        type: 'activity_update' as const,
        project_id: projectId,
        timestamp: '2023-11-14T12:00:00Z',
        activity_type: 'task_completed',
        agent: 'backend-worker-1',
        message: 'Completed authentication implementation',
      };

      const action = mapWebSocketMessageToAction(message);

      expect(action).toEqual({
        type: 'ACTIVITY_ADDED',
        payload: {
          timestamp: '2023-11-14T12:00:00Z',
          type: 'task_completed',
          agent: 'backend-worker-1',
          message: 'Completed authentication implementation',
        },
      });
    });

    it('should default activity_type to "activity_update" if not provided', () => {
      const message = {
        type: 'activity_update' as const,
        project_id: projectId,
        timestamp: '2023-11-14T12:00:00Z',
        message: 'System maintenance completed',
      };

      const action = mapWebSocketMessageToAction(message);

      expect(action?.payload).toMatchObject({
        type: 'activity_update',
        agent: 'system',
        message: 'System maintenance completed',
      });
    });

    it('should default agent to "system" if not provided', () => {
      const message = {
        type: 'activity_update' as const,
        project_id: projectId,
        timestamp: '2023-11-14T12:00:00Z',
        activity_type: 'blocker_resolved',
        message: 'All blockers resolved',
      };

      const action = mapWebSocketMessageToAction(message);

      expect(action?.payload).toMatchObject({
        agent: 'system',
      });
    });
  });

  describe('progress_update message (T057)', () => {
    it('should map progress_update message', () => {
      const message = {
        type: 'progress_update' as const,
        project_id: projectId,
        timestamp: baseTimestamp,
        completed_tasks: 25,
        total_tasks: 100,
        percentage: 25,
      };

      const action = mapWebSocketMessageToAction(message);

      expect(action).toEqual({
        type: 'PROGRESS_UPDATED',
        payload: {
          completed_tasks: 25,
          total_tasks: 100,
          percentage: 25,
        },
      });
    });

    it('should handle progress_update with 100% completion', () => {
      const message = {
        type: 'progress_update' as const,
        project_id: projectId,
        timestamp: baseTimestamp,
        completed_tasks: 50,
        total_tasks: 50,
        percentage: 100,
      };

      const action = mapWebSocketMessageToAction(message);

      expect(action?.payload).toMatchObject({
        percentage: 100,
      });
    });
  });

  describe('timestamp parsing (T058)', () => {
    it('should parse string timestamp to Unix milliseconds', () => {
      const message = {
        type: 'agent_created',
        project_id: projectId,
        timestamp: '2023-11-14T12:00:00Z',
        agent_id: 'test-agent',
        agent_type: 'lead' as const,
      };

      const action = mapWebSocketMessageToAction(message);

      expect((action?.payload as any).timestamp).toBe(new Date('2023-11-14T12:00:00Z').getTime());
    });

    it('should pass through numeric timestamp unchanged', () => {
      const message = {
        type: 'agent_created',
        project_id: projectId,
        timestamp: 1699999999000,
        agent_id: 'test-agent',
        agent_type: 'lead' as const,
      };

      const action = mapWebSocketMessageToAction(message);

      expect((action?.payload as any).timestamp).toBe(1699999999000);
    });

    it('should handle ISO 8601 timestamp with milliseconds', () => {
      const message = {
        type: 'agent_created',
        project_id: projectId,
        timestamp: '2023-11-14T12:00:00.123Z',
        agent_id: 'test-agent',
        agent_type: 'lead' as const,
      };

      const action = mapWebSocketMessageToAction(message);

      expect((action?.payload as any).timestamp).toBe(new Date('2023-11-14T12:00:00.123Z').getTime());
    });
  });

  describe('unknown message types', () => {
    it('should return null for unknown message type', () => {
      const message = {
        type: 'unknown_message_type',
        project_id: projectId,
        timestamp: baseTimestamp,
      };

      const action = mapWebSocketMessageToAction(message);

      expect(action).toBeNull();
    });

    it('should log warning for unknown message type', () => {
      // Save original process.env
      const originalEnv = process.env;

      // Set to development to enable logging
      process.env = { ...originalEnv, NODE_ENV: 'development' };

      const consoleSpy = jest.spyOn(console, 'warn').mockImplementation();

      const message = {
        type: 'invalid_type',
        project_id: projectId,
        timestamp: baseTimestamp,
      };

      mapWebSocketMessageToAction(message);

      expect(consoleSpy).toHaveBeenCalledWith(
        expect.stringContaining('Unknown WebSocket message type: invalid_type')
      );

      consoleSpy.mockRestore();

      // Restore original process.env
      process.env = originalEnv;
    });
  });

  describe('edge cases and error handling', () => {
    it('should return null when agent_id is missing (required field)', () => {
      const message = {
        type: 'agent_created',
        project_id: projectId,
        timestamp: baseTimestamp,
        // Missing agent_id (required)
      };

      const action = mapWebSocketMessageToAction(message);

      // Should return null when required field is missing
      expect(action).toBeNull();
    });

    it('should handle malformed timestamp gracefully', () => {
      const message = {
        type: 'agent_created',
        project_id: projectId,
        timestamp: 'invalid-date',
        agent_id: 'test-agent',
        agent_type: 'lead' as const,
      };

      const action = mapWebSocketMessageToAction(message);

      // Should still parse, Date constructor returns NaN for invalid dates
      expect(action).toBeTruthy();
      expect((action?.payload as any).timestamp).toBeNaN();
    });

    it('should handle empty blocked_by array', () => {
      const message = {
        type: 'task_blocked' as const,
        project_id: projectId,
        timestamp: baseTimestamp,
        task_id: 123,
        blocked_by: [],
      };

      const action = mapWebSocketMessageToAction(message);

      expect(action?.payload).toMatchObject({
        blockedBy: [],
      });
    });

    it('should validate and coerce invalid agent_type to "lead"', () => {
      const message = {
        type: 'agent_created' as const,
        project_id: projectId,
        timestamp: baseTimestamp,
        agent_id: 'test-agent-1',
        agent_type: 'invalid-type', // Invalid type
      };

      const action = mapWebSocketMessageToAction(message);

      expect(action).toBeTruthy();
      expect((action?.payload as any).type).toBe('lead'); // Fallback to 'lead'
    });

    it('should use provider from message with fallback to anthropic', () => {
      const messageWithProvider = {
        type: 'agent_created' as const,
        project_id: projectId,
        timestamp: baseTimestamp,
        agent_id: 'test-agent-1',
        agent_type: 'backend-worker',
        provider: 'openai',
      };

      const actionWithProvider = mapWebSocketMessageToAction(messageWithProvider);
      expect((actionWithProvider?.payload as any).provider).toBe('openai');

      const messageWithoutProvider = {
        type: 'agent_created' as const,
        project_id: projectId,
        timestamp: baseTimestamp,
        agent_id: 'test-agent-2',
        agent_type: 'backend-worker',
      };

      const actionWithoutProvider = mapWebSocketMessageToAction(messageWithoutProvider);
      expect((actionWithoutProvider?.payload as any).provider).toBe('anthropic');
    });

    it('should normalize context_tokens and tasks_completed to numbers', () => {
      const message = {
        type: 'agent_created' as const,
        project_id: projectId,
        timestamp: baseTimestamp,
        agent_id: 'test-agent-1',
        agent_type: 'backend-worker',
        context_tokens: '1500', // String instead of number
        tasks_completed: '5',   // String instead of number
      };

      const action = mapWebSocketMessageToAction(message);

      expect((action?.payload as any).context_tokens).toBe(1500);
      expect((action?.payload as any).tasks_completed).toBe(5);
      expect(typeof (action?.payload as any).context_tokens).toBe('number');
      expect(typeof (action?.payload as any).tasks_completed).toBe('number');
    });

    it('should default to 0 for invalid numeric fields', () => {
      const message = {
        type: 'agent_created' as const,
        project_id: projectId,
        timestamp: baseTimestamp,
        agent_id: 'test-agent-1',
        agent_type: 'backend-worker',
        context_tokens: 'invalid',
        tasks_completed: null,
      };

      const action = mapWebSocketMessageToAction(message);

      expect((action?.payload as any).context_tokens).toBe(0);
      expect((action?.payload as any).tasks_completed).toBe(0);
    });
  });

  describe('integration tests (T059-T061)', () => {
    it('should handle multiple messages in sequence', () => {
      const messages = [
        {
          type: 'agent_created',
          project_id: projectId,
          timestamp: baseTimestamp,
          agent_id: 'agent-1',
          agent_type: 'lead' as const,
        },
        {
          type: 'task_assigned',
          project_id: projectId,
          timestamp: baseTimestamp + 1000,
          task_id: 1,
          agent_id: 'agent-1',
          task_title: 'Task 1',
        },
        {
          type: 'task_status_changed',
          project_id: projectId,
          timestamp: baseTimestamp + 2000,
          task_id: 1,
          status: 'completed' as const,
        },
      ];

      const actions = messages.map(mapWebSocketMessageToAction);

      expect(actions).toHaveLength(3);
      expect(actions[0]?.type).toBe('AGENT_CREATED');
      expect(actions[1]?.type).toBe('TASK_ASSIGNED');
      expect(actions[2]?.type).toBe('TASK_STATUS_CHANGED');
    });

    it('should handle out-of-order messages (timestamps)', () => {
      const messages = [
        {
          type: 'agent_status_changed',
          project_id: projectId,
          timestamp: baseTimestamp + 2000, // Newer
          agent_id: 'agent-1',
          status: 'working' as const,
        },
        {
          type: 'agent_status_changed',
          project_id: projectId,
          timestamp: baseTimestamp + 1000, // Older
          agent_id: 'agent-1',
          status: 'idle' as const,
        },
      ];

      const actions = messages.map(mapWebSocketMessageToAction);

      // Both should map successfully
      expect((actions[0]?.payload as any).timestamp).toBe(baseTimestamp + 2000);
      expect((actions[1]?.payload as any).timestamp).toBe(baseTimestamp + 1000);

      // Reducer will handle conflict resolution based on timestamps
    });

    it('should handle rapid-fire updates for multiple agents', () => {
      const messages = Array.from({ length: 10 }, (_, i) => ({
        type: 'agent_status_changed',
        project_id: projectId,
        timestamp: baseTimestamp + i * 100,
        agent_id: `agent-${i}`,
        status: 'working' as const,
      }));

      const actions = messages.map(mapWebSocketMessageToAction);

      expect(actions).toHaveLength(10);
      actions.forEach((action, i) => {
        expect(action?.type).toBe('AGENT_UPDATED');
        expect((action?.payload as any).agentId).toBe(`agent-${i}`);
      });
    });
  });

  describe('commit_created message validation (Ticket #272)', () => {
    it('should map commit_created message with all required fields', () => {
      const message = {
        type: 'commit_created' as const,
        project_id: projectId,
        timestamp: '2023-11-14T12:00:00Z',
        commit_hash: 'abc123def456',
        commit_message: 'feat: Add new feature',
        agent: 'backend-worker-1',
        task_id: 123,
        files_changed: ['file1.ts', 'file2.ts'],
      };

      const action = mapWebSocketMessageToAction(message);

      expect(action).toEqual({
        type: 'COMMIT_CREATED',
        payload: {
          commit: {
            hash: 'abc123def456',
            short_hash: 'abc123d',
            message: 'feat: Add new feature',
            author: 'backend-worker-1',
            timestamp: '2023-11-14T12:00:00Z',
            files_changed: 2,
          },
          taskId: 123,
          timestamp: new Date('2023-11-14T12:00:00Z').getTime(),
        },
      });
    });

    it('should return null when commit_hash is missing', () => {
      const message = {
        type: 'commit_created' as const,
        project_id: projectId,
        timestamp: baseTimestamp,
        commit_message: 'feat: Add new feature',
        // Missing commit_hash
      };

      const action = mapWebSocketMessageToAction(message);

      expect(action).toBeNull();
    });

    it('should return null when commit_message is missing', () => {
      const message = {
        type: 'commit_created' as const,
        project_id: projectId,
        timestamp: baseTimestamp,
        commit_hash: 'abc123def456',
        // Missing commit_message
      };

      const action = mapWebSocketMessageToAction(message);

      expect(action).toBeNull();
    });

    it('should log warning when required fields are missing in development', () => {
      const originalEnv = process.env;
      process.env = { ...originalEnv, NODE_ENV: 'development' };

      const consoleSpy = jest.spyOn(console, 'warn').mockImplementation();

      const message = {
        type: 'commit_created' as const,
        project_id: projectId,
        timestamp: baseTimestamp,
        // Missing required fields
      };

      mapWebSocketMessageToAction(message);

      expect(consoleSpy).toHaveBeenCalledWith(
        expect.stringContaining('commit_created message missing required fields'),
        expect.anything()
      );

      consoleSpy.mockRestore();
      process.env = originalEnv;
    });
  });

  describe('branch_created message validation (Ticket #272)', () => {
    it('should map branch_created message with all required fields', () => {
      const message = {
        type: 'branch_created' as const,
        project_id: projectId,
        timestamp: '2023-11-14T12:00:00Z',
        data: {
          id: 1,
          branch_name: 'feature/auth',
          issue_id: 42,
        },
      };

      const action = mapWebSocketMessageToAction(message);

      expect(action).toEqual({
        type: 'BRANCH_CREATED',
        payload: {
          branch: {
            id: 1,
            branch_name: 'feature/auth',
            issue_id: 42,
            status: 'active',
            created_at: '2023-11-14T12:00:00Z',
          },
          timestamp: new Date('2023-11-14T12:00:00Z').getTime(),
        },
      });
    });

    it('should return null when data.id is missing', () => {
      const message = {
        type: 'branch_created' as const,
        project_id: projectId,
        timestamp: baseTimestamp,
        data: {
          branch_name: 'feature/auth',
          // Missing id
        },
      };

      const action = mapWebSocketMessageToAction(message);

      expect(action).toBeNull();
    });

    it('should return null when data.branch_name is missing', () => {
      const message = {
        type: 'branch_created' as const,
        project_id: projectId,
        timestamp: baseTimestamp,
        data: {
          id: 1,
          // Missing branch_name
        },
      };

      const action = mapWebSocketMessageToAction(message);

      expect(action).toBeNull();
    });

    it('should return null when data is missing entirely', () => {
      const message = {
        type: 'branch_created' as const,
        project_id: projectId,
        timestamp: baseTimestamp,
        // Missing data
      };

      const action = mapWebSocketMessageToAction(message);

      expect(action).toBeNull();
    });

    it('should default issue_id to 0 when not provided', () => {
      const message = {
        type: 'branch_created' as const,
        project_id: projectId,
        timestamp: baseTimestamp,
        data: {
          id: 1,
          branch_name: 'feature/auth',
          // Missing issue_id
        },
      };

      const action = mapWebSocketMessageToAction(message);

      expect(action).toBeTruthy();
      expect((action?.payload as any).branch.issue_id).toBe(0);
    });

    it('should log warning when required fields are missing in development', () => {
      const originalEnv = process.env;
      process.env = { ...originalEnv, NODE_ENV: 'development' };

      const consoleSpy = jest.spyOn(console, 'warn').mockImplementation();

      const message = {
        type: 'branch_created' as const,
        project_id: projectId,
        timestamp: baseTimestamp,
        data: {
          // Missing required fields
        },
      };

      mapWebSocketMessageToAction(message);

      expect(consoleSpy).toHaveBeenCalledWith(
        expect.stringContaining('branch_created message missing required fields'),
        expect.anything()
      );

      consoleSpy.mockRestore();
      process.env = originalEnv;
    });
  });
});