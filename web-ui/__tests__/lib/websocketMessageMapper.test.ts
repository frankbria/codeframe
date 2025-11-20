/**
 * Unit tests for WebSocket message mapper
 *
 * Tests the mapping of WebSocket messages from backend format to reducer actions.
 * Covers all message types (T050-T061).
 */

import { mapWebSocketMessageToAction } from '@/lib/websocketMessageMapper';
import type { WebSocketMessage } from '@/types';
import type { AgentAction } from '@/types/agentState';

describe('mapWebSocketMessageToAction', () => {
  const projectId = 1;
  const baseTimestamp = 1699999999000;

  describe('agent_created message (T050)', () => {
    it('should map agent_created message with all fields', () => {
      const message: any = {
        type: 'agent_created',
        project_id: projectId,
        timestamp: baseTimestamp.toString(),
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
          timestamp: baseTimestamp.toString(),
        },
      });
    });

    it('should default provider to "anthropic" if not provided', () => {
      const message: Partial<WebSocketMessage> = {
        type: 'agent_created',
        project_id: projectId,
        timestamp: baseTimestamp.toString(),
        agent_id: 'lead-1',
        agent_type: 'lead',
      };

      const action = mapWebSocketMessageToAction(message);

      expect(action?.payload).toMatchObject({
        provider: 'anthropic',
      });
    });

    it('should parse string timestamp to number', () => {
      const message: Partial<WebSocketMessage> = {
        type: 'agent_created',
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
      const message: Partial<WebSocketMessage> = {
        type: 'agent_status_changed',
        project_id: projectId,
        timestamp: baseTimestamp.toString(),
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
          timestamp: baseTimestamp.toString(),
        },
      });
    });

    it('should include current_task when provided', () => {
      const message: Partial<WebSocketMessage> = {
        type: 'agent_status_changed',
        project_id: projectId,
        timestamp: baseTimestamp.toString(),
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
      const message: Partial<WebSocketMessage> = {
        type: 'agent_status_changed',
        project_id: projectId,
        timestamp: baseTimestamp.toString(),
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
      const message: Partial<WebSocketMessage> = {
        type: 'agent_retired',
        project_id: projectId,
        timestamp: baseTimestamp.toString(),
        agent_id: 'backend-worker-1',
      };

      const action = mapWebSocketMessageToAction(message);

      expect(action).toEqual({
        type: 'AGENT_RETIRED',
        payload: {
          agentId: 'backend-worker-1',
          timestamp: baseTimestamp.toString(),
        },
      });
    });
  });

  describe('task_assigned message (T053)', () => {
    it('should map task_assigned message with task title', () => {
      const message: Partial<WebSocketMessage> = {
        type: 'task_assigned',
        project_id: projectId,
        timestamp: baseTimestamp.toString(),
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
          timestamp: baseTimestamp.toString(),
        },
      });
    });

    it('should handle task_assigned without task title', () => {
      const message: Partial<WebSocketMessage> = {
        type: 'task_assigned',
        project_id: projectId,
        timestamp: baseTimestamp.toString(),
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
          timestamp: baseTimestamp.toString(),
        },
      });
    });
  });

  describe('task_status_changed message (T054)', () => {
    it('should map task_status_changed message with progress', () => {
      const message: Partial<WebSocketMessage> = {
        type: 'task_status_changed',
        project_id: projectId,
        timestamp: baseTimestamp.toString(),
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
          timestamp: baseTimestamp.toString(),
        },
      });
    });

    it('should map task_status_changed without progress', () => {
      const message: Partial<WebSocketMessage> = {
        type: 'task_status_changed',
        project_id: projectId,
        timestamp: baseTimestamp.toString(),
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
          timestamp: baseTimestamp.toString(),
        },
      });
    });
  });

  describe('task_blocked and task_unblocked messages (T055)', () => {
    it('should map task_blocked message', () => {
      const message: Partial<WebSocketMessage> = {
        type: 'task_blocked',
        project_id: projectId,
        timestamp: baseTimestamp.toString(),
        task_id: 789,
        blocked_by: [123, 456],
      };

      const action = mapWebSocketMessageToAction(message);

      expect(action).toEqual({
        type: 'TASK_BLOCKED',
        payload: {
          taskId: 789,
          blockedBy: [123, 456],
          timestamp: baseTimestamp.toString(),
        },
      });
    });

    it('should map task_unblocked message', () => {
      const message: Partial<WebSocketMessage> = {
        type: 'task_unblocked',
        project_id: projectId,
        timestamp: baseTimestamp.toString(),
        task_id: 789,
      };

      const action = mapWebSocketMessageToAction(message);

      expect(action).toEqual({
        type: 'TASK_UNBLOCKED',
        payload: {
          taskId: 789,
          timestamp: baseTimestamp.toString(),
        },
      });
    });
  });

  describe('activity_update message (T056)', () => {
    it('should map activity_update message with all fields', () => {
      const message: Partial<WebSocketMessage> = {
        type: 'activity_update',
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
      const message: Partial<WebSocketMessage> = {
        type: 'activity_update',
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
      const message: Partial<WebSocketMessage> = {
        type: 'activity_update',
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
      const message: Partial<WebSocketMessage> = {
        type: 'progress_update',
        project_id: projectId,
        timestamp: baseTimestamp.toString(),
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
      const message: Partial<WebSocketMessage> = {
        type: 'progress_update',
        project_id: projectId,
        timestamp: baseTimestamp.toString(),
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
        timestamp: baseTimestamp.toString(),
      };

      const action = mapWebSocketMessageToAction(message);

      expect(action).toBeNull();
    });

    it('should log warning for unknown message type', () => {
      const consoleSpy = jest.spyOn(console, 'warn').mockImplementation();

      const message = {
        type: 'invalid_type',
        project_id: projectId,
        timestamp: baseTimestamp.toString(),
      };

      mapWebSocketMessageToAction(message);

      expect(consoleSpy).toHaveBeenCalledWith(
        expect.stringContaining('Unknown WebSocket message type: invalid_type')
      );

      consoleSpy.mockRestore();
    });
  });

  describe('edge cases and error handling', () => {
    it('should handle message with missing required fields gracefully', () => {
      const message = {
        type: 'agent_created',
        project_id: projectId,
        timestamp: baseTimestamp.toString(),
        // Missing agent_id and agent_type
      };

      const action = mapWebSocketMessageToAction(message);

      // Should still create action, even if data is incomplete
      expect(action).toBeTruthy();
      expect(action?.type).toBe('AGENT_CREATED');
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
      const message: Partial<WebSocketMessage> = {
        type: 'task_blocked',
        project_id: projectId,
        timestamp: baseTimestamp.toString(),
        task_id: 123,
        blocked_by: [],
      };

      const action = mapWebSocketMessageToAction(message);

      expect(action?.payload).toMatchObject({
        blockedBy: [],
      });
    });
  });

  describe('integration tests (T059-T061)', () => {
    it('should handle multiple messages in sequence', () => {
      const messages = [
        {
          type: 'agent_created',
          project_id: projectId,
          timestamp: baseTimestamp.toString(),
          agent_id: 'agent-1',
          agent_type: 'lead' as const,
        },
        {
          type: 'task_assigned',
          project_id: projectId,
          timestamp: (baseTimestamp + 1000).toString(),
          task_id: 1,
          agent_id: 'agent-1',
          task_title: 'Task 1',
        },
        {
          type: 'task_status_changed',
          project_id: projectId,
          timestamp: (baseTimestamp + 2000).toString(),
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
          timestamp: (baseTimestamp + 2000).toString(), // Newer
          agent_id: 'agent-1',
          status: 'working' as const,
        },
        {
          type: 'agent_status_changed',
          project_id: projectId,
          timestamp: (baseTimestamp + 1000).toString(), // Older
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
        timestamp: (baseTimestamp + i * 100).toString(),
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
});