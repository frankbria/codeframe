/**
 * Unit tests for agent state synchronization
 *
 * Tests the full state resync functionality for WebSocket reconnection.
 * Covers API calls, parallel fetches, and error handling (T078-T080).
 */

import { fullStateResync } from '@/lib/agentStateSync';
import { agentsApi, tasksApi, activityApi } from '@/lib/api';
import type { Agent, Task, ActivityItem } from '@/types/agentState';

// Mock the API modules
jest.mock('@/lib/api', () => ({
  agentsApi: {
    list: jest.fn(),
  },
  tasksApi: {
    list: jest.fn(),
  },
  activityApi: {
    list: jest.fn(),
  },
}));

describe('fullStateResync', () => {
  const projectId = 1;
  const mockAgents: Agent[] = [
    {
      id: 'agent-1',
      type: 'backend-worker',
      status: 'working',
      provider: 'anthropic',
      maturity: 'directive',
      context_tokens: 1000,
      tasks_completed: 5,
      timestamp: Date.now(),
    },
  ];

  const mockTasks: Task[] = [
    {
      id: 1,
      title: 'Implement authentication',
      status: 'in_progress',
      agent_id: 'agent-1',
      timestamp: Date.now(),
    },
  ];

  const mockActivity: ActivityItem[] = [
    {
      timestamp: new Date().toISOString(),
      type: 'task_assigned',
      agent: 'agent-1',
      message: 'Task assigned to agent-1',
    },
  ];

  beforeEach(() => {
    jest.clearAllMocks();
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  describe('API call (T078)', () => {
    it('should fetch all three data sources', async () => {
      // Mock API responses
      (agentsApi.list as jest.Mock).mockResolvedValue({
        data: { agents: mockAgents },
      });
      (tasksApi.list as jest.Mock).mockResolvedValue({
        data: { tasks: mockTasks },
      });
      (activityApi.list as jest.Mock).mockResolvedValue({
        data: { activity: mockActivity },
      });

      await fullStateResync(projectId);

      expect(agentsApi.list).toHaveBeenCalledWith(projectId);
      expect(tasksApi.list).toHaveBeenCalledWith(projectId, { limit: 100 });
      expect(activityApi.list).toHaveBeenCalledWith(projectId, 50);
    });

    it('should return complete state with timestamp', async () => {
      const now = Date.now();
      jest.setSystemTime(now);

      (agentsApi.list as jest.Mock).mockResolvedValue({
        data: { agents: mockAgents },
      });
      (tasksApi.list as jest.Mock).mockResolvedValue({
        data: { tasks: mockTasks },
      });
      (activityApi.list as jest.Mock).mockResolvedValue({
        data: { activity: mockActivity },
      });

      const result = await fullStateResync(projectId);

      expect(result).toEqual({
        agents: mockAgents,
        tasks: mockTasks,
        activity: mockActivity,
        timestamp: now,
      });
    });
  });

  describe('parallel fetches (T079)', () => {
    it('should execute all API calls in parallel using Promise.all', async () => {
      let agentsResolved = false;
      let tasksResolved = false;
      let activityResolved = false;

      (agentsApi.list as jest.Mock).mockImplementation(async () => {
        await new Promise((resolve) => setTimeout(resolve, 100));
        agentsResolved = true;
        return { data: { agents: mockAgents } };
      });

      (tasksApi.list as jest.Mock).mockImplementation(async () => {
        await new Promise((resolve) => setTimeout(resolve, 100));
        tasksResolved = true;
        return { data: { tasks: mockTasks } };
      });

      (activityApi.list as jest.Mock).mockImplementation(async () => {
        await new Promise((resolve) => setTimeout(resolve, 100));
        activityResolved = true;
        return { data: { activity: mockActivity } };
      });

      const resyncPromise = fullStateResync(projectId);

      // Advance timers to trigger all promises
      jest.advanceTimersByTime(100);
      await resyncPromise;

      // All should be resolved because they ran in parallel
      expect(agentsResolved).toBe(true);
      expect(tasksResolved).toBe(true);
      expect(activityResolved).toBe(true);
    });

    it('should be faster than sequential execution', async () => {
      // Mock each API to take 100ms
      (agentsApi.list as jest.Mock).mockImplementation(
        () =>
          new Promise((resolve) =>
            setTimeout(
              () => resolve({ data: { agents: mockAgents } }),
              100
            )
          )
      );
      (tasksApi.list as jest.Mock).mockImplementation(
        () =>
          new Promise((resolve) =>
            setTimeout(() => resolve({ data: { tasks: mockTasks } }), 100)
          )
      );
      (activityApi.list as jest.Mock).mockImplementation(
        () =>
          new Promise((resolve) =>
            setTimeout(
              () => resolve({ data: { activity: mockActivity } }),
              100
            )
          )
      );

      const startTime = Date.now();
      const resyncPromise = fullStateResync(projectId);

      // Advance time by 100ms (not 300ms for sequential)
      jest.advanceTimersByTime(100);
      await resyncPromise;

      const duration = Date.now() - startTime;

      // Should complete in ~100ms (parallel) not ~300ms (sequential)
      expect(duration).toBeLessThan(200);
    });
  });

  describe('error handling (T080)', () => {
    it('should throw error if agents fetch fails', async () => {
      (agentsApi.list as jest.Mock).mockRejectedValue(
        new Error('Network error')
      );
      (tasksApi.list as jest.Mock).mockResolvedValue({
        data: { tasks: mockTasks },
      });
      (activityApi.list as jest.Mock).mockResolvedValue({
        data: { activity: mockActivity },
      });

      await expect(fullStateResync(projectId)).rejects.toThrow('Network error');
    });

    it('should throw error if tasks fetch fails', async () => {
      (agentsApi.list as jest.Mock).mockResolvedValue({
        data: { agents: mockAgents },
      });
      (tasksApi.list as jest.Mock).mockRejectedValue(
        new Error('Database error')
      );
      (activityApi.list as jest.Mock).mockResolvedValue({
        data: { activity: mockActivity },
      });

      await expect(fullStateResync(projectId)).rejects.toThrow('Database error');
    });

    it('should throw error if activity fetch fails', async () => {
      (agentsApi.list as jest.Mock).mockResolvedValue({
        data: { agents: mockAgents },
      });
      (tasksApi.list as jest.Mock).mockResolvedValue({
        data: { tasks: mockTasks },
      });
      (activityApi.list as jest.Mock).mockRejectedValue(
        new Error('Activity API error')
      );

      await expect(fullStateResync(projectId)).rejects.toThrow(
        'Activity API error'
      );
    });

    it('should handle empty responses gracefully', async () => {
      (agentsApi.list as jest.Mock).mockResolvedValue({
        data: { agents: [] },
      });
      (tasksApi.list as jest.Mock).mockResolvedValue({
        data: { tasks: [] },
      });
      (activityApi.list as jest.Mock).mockResolvedValue({
        data: { activity: [] },
      });

      const result = await fullStateResync(projectId);

      expect(result.agents).toEqual([]);
      expect(result.tasks).toEqual([]);
      expect(result.activity).toEqual([]);
      expect(result.timestamp).toBeGreaterThan(0);
    });

    it('should handle undefined/null responses', async () => {
      (agentsApi.list as jest.Mock).mockResolvedValue({
        data: { agents: undefined },
      });
      (tasksApi.list as jest.Mock).mockResolvedValue({
        data: { tasks: null },
      });
      (activityApi.list as jest.Mock).mockResolvedValue({
        data: { activity: [] },
      });

      const result = await fullStateResync(projectId);

      // Should handle undefined/null by providing empty arrays
      expect(result.agents).toEqual([]);
      expect(result.tasks).toEqual([]);
      expect(result.activity).toEqual([]);
    });

    it('should retry on network timeout', async () => {
      let attempts = 0;

      (agentsApi.list as jest.Mock).mockImplementation(async () => {
        attempts++;
        if (attempts === 1) {
          throw new Error('Timeout');
        }
        return { data: { agents: mockAgents } };
      });

      (tasksApi.list as jest.Mock).mockResolvedValue({
        data: { tasks: mockTasks },
      });
      (activityApi.list as jest.Mock).mockResolvedValue({
        data: { activity: mockActivity },
      });

      // First call should fail
      await expect(fullStateResync(projectId)).rejects.toThrow('Timeout');

      // Second call should succeed
      const result = await fullStateResync(projectId);
      expect(result.agents).toEqual(mockAgents);
      expect(attempts).toBe(2);
    });
  });

  describe('timestamp generation', () => {
    it('should generate timestamp at resync time', async () => {
      const beforeResync = Date.now();

      (agentsApi.list as jest.Mock).mockResolvedValue({
        data: { agents: mockAgents },
      });
      (tasksApi.list as jest.Mock).mockResolvedValue({
        data: { tasks: mockTasks },
      });
      (activityApi.list as jest.Mock).mockResolvedValue({
        data: { activity: mockActivity },
      });

      const result = await fullStateResync(projectId);

      const afterResync = Date.now();

      expect(result.timestamp).toBeGreaterThanOrEqual(beforeResync);
      expect(result.timestamp).toBeLessThanOrEqual(afterResync);
    });

    it('should have different timestamps for consecutive resyncs', async () => {
      (agentsApi.list as jest.Mock).mockResolvedValue({
        data: { agents: mockAgents },
      });
      (tasksApi.list as jest.Mock).mockResolvedValue({
        data: { tasks: mockTasks },
      });
      (activityApi.list as jest.Mock).mockResolvedValue({
        data: { activity: mockActivity },
      });

      const result1 = await fullStateResync(projectId);
      jest.advanceTimersByTime(10);
      const result2 = await fullStateResync(projectId);

      expect(result2.timestamp).toBeGreaterThan(result1.timestamp);
    });
  });
});
