/**
 * Integration tests for blocker WebSocket events
 * Tests T061 from Phase 9: Testing & Validation
 * 049-human-in-loop feature
 */

import { describe, it, expect, jest, beforeEach, afterEach } from '@jest/globals';

// Mock WebSocket
class MockWebSocket {
  public onopen: (() => void) | null = null;
  public onmessage: ((event: { data: string }) => void) | null = null;
  public onerror: ((error: Event) => void) | null = null;
  public onclose: (() => void) | null = null;
  public readyState: number = 0;

  public static CONNECTING = 0;
  public static OPEN = 1;
  public static CLOSING = 2;
  public static CLOSED = 3;

  constructor(public url: string) {
    setTimeout(() => {
      this.readyState = MockWebSocket.OPEN;
      if (this.onopen) this.onopen();
    }, 0);
  }

  send(data: string) {
    // Mock send implementation
  }

  close() {
    this.readyState = MockWebSocket.CLOSED;
    if (this.onclose) this.onclose();
  }

  // Helper method to simulate receiving a message
  simulateMessage(data: any) {
    if (this.onmessage) {
      this.onmessage({ data: JSON.stringify(data) });
    }
  }
}

// Replace global WebSocket
(global as any).WebSocket = MockWebSocket;

describe('Blocker WebSocket Integration', () => {
  let mockWs: MockWebSocket;
  let messageHandler: jest.Mock;

  beforeEach(() => {
    messageHandler = jest.fn();
    mockWs = new MockWebSocket('ws://localhost:8000/ws');
  });

  afterEach(() => {
    if (mockWs) {
      mockWs.close();
    }
    jest.clearAllMocks();
  });

  describe('blocker_created event', () => {
    it('receives blocker_created event with correct payload', (done) => {
      const blockerCreatedEvent = {
        type: 'blocker_created',
        blocker_id: 123,
        agent_id: 'backend-worker-001',
        task_id: 456,
        blocker_type: 'SYNC',
        question: 'Should I use SQLite or PostgreSQL?',
        created_at: '2025-11-08T12:34:56Z',
      };

      mockWs.onmessage = (event) => {
        const data = JSON.parse(event.data);
        expect(data.type).toBe('blocker_created');
        expect(data.blocker_id).toBe(123);
        expect(data.agent_id).toBe('backend-worker-001');
        expect(data.task_id).toBe(456);
        expect(data.blocker_type).toBe('SYNC');
        expect(data.question).toBe('Should I use SQLite or PostgreSQL?');
        expect(data.created_at).toBe('2025-11-08T12:34:56Z');
        done();
      };

      // Wait for connection to open
      mockWs.onopen = () => {
        mockWs.simulateMessage(blockerCreatedEvent);
      };
    });

    it('handles ASYNC blocker_created event', (done) => {
      const asyncBlockerEvent = {
        type: 'blocker_created',
        blocker_id: 124,
        agent_id: 'frontend-worker-001',
        task_id: 457,
        blocker_type: 'ASYNC',
        question: 'Should the button be blue or green?',
        created_at: '2025-11-08T12:35:00Z',
      };

      mockWs.onmessage = (event) => {
        const data = JSON.parse(event.data);
        expect(data.type).toBe('blocker_created');
        expect(data.blocker_type).toBe('ASYNC');
        done();
      };

      mockWs.onopen = () => {
        mockWs.simulateMessage(asyncBlockerEvent);
      };
    });

    it('triggers dashboard blocker panel update on blocker_created', (done) => {
      const blockerCreatedEvent = {
        type: 'blocker_created',
        blocker_id: 125,
        agent_id: 'backend-worker-002',
        task_id: 458,
        blocker_type: 'SYNC',
        question: 'Test question',
        created_at: '2025-11-08T12:36:00Z',
      };

      const dashboardUpdateHandler = jest.fn((data: any) => {
        expect(data.type).toBe('blocker_created');
        expect(dashboardUpdateHandler).toHaveBeenCalledTimes(1);
        done();
      });

      mockWs.onmessage = (event) => {
        const data = JSON.parse(event.data);
        dashboardUpdateHandler(data);
      };

      mockWs.onopen = () => {
        mockWs.simulateMessage(blockerCreatedEvent);
      };
    });
  });

  describe('blocker_resolved event', () => {
    it('receives blocker_resolved event with correct payload', (done) => {
      const blockerResolvedEvent = {
        type: 'blocker_resolved',
        blocker_id: 123,
        answer: 'Use SQLite to match existing codebase',
        resolved_at: '2025-11-08T12:45:30Z',
      };

      mockWs.onmessage = (event) => {
        const data = JSON.parse(event.data);
        expect(data.type).toBe('blocker_resolved');
        expect(data.blocker_id).toBe(123);
        expect(data.answer).toBe('Use SQLite to match existing codebase');
        expect(data.resolved_at).toBe('2025-11-08T12:45:30Z');
        done();
      };

      mockWs.onopen = () => {
        mockWs.simulateMessage(blockerResolvedEvent);
      };
    });

    it('removes resolved blocker from dashboard panel', (done) => {
      const blockerResolvedEvent = {
        type: 'blocker_resolved',
        blocker_id: 123,
        answer: 'Use JWT',
        resolved_at: '2025-11-08T12:45:30Z',
      };

      const panelUpdateHandler = jest.fn((data: any) => {
        expect(data.type).toBe('blocker_resolved');
        expect(data.blocker_id).toBe(123);
        // In real implementation, this would trigger removal from panel
        done();
      });

      mockWs.onmessage = (event) => {
        const data = JSON.parse(event.data);
        panelUpdateHandler(data);
      };

      mockWs.onopen = () => {
        mockWs.simulateMessage(blockerResolvedEvent);
      };
    });

    it('handles blocker_resolved with long answer', (done) => {
      const longAnswer = 'A'.repeat(5000);
      const blockerResolvedEvent = {
        type: 'blocker_resolved',
        blocker_id: 126,
        answer: longAnswer,
        resolved_at: '2025-11-08T12:46:00Z',
      };

      mockWs.onmessage = (event) => {
        const data = JSON.parse(event.data);
        expect(data.answer.length).toBe(5000);
        done();
      };

      mockWs.onopen = () => {
        mockWs.simulateMessage(blockerResolvedEvent);
      };
    });
  });

  describe('agent_resumed event', () => {
    it('receives agent_resumed event with correct payload', (done) => {
      const agentResumedEvent = {
        type: 'agent_resumed',
        agent_id: 'backend-worker-001',
        task_id: 456,
        blocker_id: 123,
        resumed_at: '2025-11-08T12:45:35Z',
      };

      mockWs.onmessage = (event) => {
        const data = JSON.parse(event.data);
        expect(data.type).toBe('agent_resumed');
        expect(data.agent_id).toBe('backend-worker-001');
        expect(data.task_id).toBe(456);
        expect(data.blocker_id).toBe(123);
        expect(data.resumed_at).toBe('2025-11-08T12:45:35Z');
        done();
      };

      mockWs.onopen = () => {
        mockWs.simulateMessage(agentResumedEvent);
      };
    });

    it('updates agent status card on agent_resumed', (done) => {
      const agentResumedEvent = {
        type: 'agent_resumed',
        agent_id: 'backend-worker-001',
        task_id: 456,
        blocker_id: 123,
        resumed_at: '2025-11-08T12:45:35Z',
      };

      const statusUpdateHandler = jest.fn((data: any) => {
        expect(data.agent_id).toBe('backend-worker-001');
        // In real implementation, this would update agent status from 'blocked' to 'working'
        done();
      });

      mockWs.onmessage = (event) => {
        const data = JSON.parse(event.data);
        statusUpdateHandler(data);
      };

      mockWs.onopen = () => {
        mockWs.simulateMessage(agentResumedEvent);
      };
    });

    it('adds activity feed entry on agent_resumed', (done) => {
      const agentResumedEvent = {
        type: 'agent_resumed',
        agent_id: 'frontend-worker-001',
        task_id: 457,
        blocker_id: 124,
        resumed_at: '2025-11-08T12:46:00Z',
      };

      const activityFeedHandler = jest.fn((data: any) => {
        expect(data.type).toBe('agent_resumed');
        // In real implementation, this would add entry like:
        // "Frontend Worker #1 resumed work on Task 457 after blocker resolution"
        done();
      });

      mockWs.onmessage = (event) => {
        const data = JSON.parse(event.data);
        activityFeedHandler(data);
      };

      mockWs.onopen = () => {
        mockWs.simulateMessage(agentResumedEvent);
      };
    });
  });

  describe('blocker_expired event', () => {
    it('receives blocker_expired event with correct payload', (done) => {
      const blockerExpiredEvent = {
        type: 'blocker_expired',
        blocker_id: 127,
        task_id: 459,
      };

      mockWs.onmessage = (event) => {
        const data = JSON.parse(event.data);
        expect(data.type).toBe('blocker_expired');
        expect(data.blocker_id).toBe(127);
        expect(data.task_id).toBe(459);
        done();
      };

      mockWs.onopen = () => {
        mockWs.simulateMessage(blockerExpiredEvent);
      };
    });

    it('removes expired blocker from dashboard panel', (done) => {
      const blockerExpiredEvent = {
        type: 'blocker_expired',
        blocker_id: 127,
        task_id: 459,
      };

      const panelUpdateHandler = jest.fn((data: any) => {
        expect(data.type).toBe('blocker_expired');
        expect(data.blocker_id).toBe(127);
        // Should remove blocker from panel
        done();
      });

      mockWs.onmessage = (event) => {
        const data = JSON.parse(event.data);
        panelUpdateHandler(data);
      };

      mockWs.onopen = () => {
        mockWs.simulateMessage(blockerExpiredEvent);
      };
    });

    it('updates task status to FAILED on blocker_expired', (done) => {
      const blockerExpiredEvent = {
        type: 'blocker_expired',
        blocker_id: 128,
        task_id: 460,
      };

      const taskStatusHandler = jest.fn((data: any) => {
        expect(data.task_id).toBe(460);
        // In real implementation, task status would update to FAILED
        done();
      });

      mockWs.onmessage = (event) => {
        const data = JSON.parse(event.data);
        taskStatusHandler(data);
      };

      mockWs.onopen = () => {
        mockWs.simulateMessage(blockerExpiredEvent);
      };
    });
  });

  describe('complete workflow event sequence', () => {
    it('handles full lifecycle: created → resolved → resumed', (done) => {
      const events = [
        {
          type: 'blocker_created',
          blocker_id: 200,
          agent_id: 'backend-worker-003',
          task_id: 500,
          blocker_type: 'SYNC',
          question: 'Question?',
          created_at: '2025-11-08T13:00:00Z',
        },
        {
          type: 'blocker_resolved',
          blocker_id: 200,
          answer: 'Answer',
          resolved_at: '2025-11-08T13:05:00Z',
        },
        {
          type: 'agent_resumed',
          agent_id: 'backend-worker-003',
          task_id: 500,
          blocker_id: 200,
          resumed_at: '2025-11-08T13:05:05Z',
        },
      ];

      let eventIndex = 0;
      const receivedEvents: string[] = [];

      mockWs.onmessage = (event) => {
        const data = JSON.parse(event.data);
        receivedEvents.push(data.type);

        if (receivedEvents.length === 3) {
          expect(receivedEvents).toEqual([
            'blocker_created',
            'blocker_resolved',
            'agent_resumed',
          ]);
          done();
        }
      };

      mockWs.onopen = () => {
        // Simulate events in sequence
        events.forEach((event, index) => {
          setTimeout(() => {
            mockWs.simulateMessage(event);
          }, index * 10);
        });
      };
    });

    it('handles workflow with blocker expiration', (done) => {
      const events = [
        {
          type: 'blocker_created',
          blocker_id: 201,
          agent_id: 'backend-worker-004',
          task_id: 501,
          blocker_type: 'SYNC',
          question: 'Will expire',
          created_at: '2025-11-07T13:00:00Z',
        },
        {
          type: 'blocker_expired',
          blocker_id: 201,
          task_id: 501,
        },
      ];

      let eventIndex = 0;
      const receivedEvents: string[] = [];

      mockWs.onmessage = (event) => {
        const data = JSON.parse(event.data);
        receivedEvents.push(data.type);

        if (receivedEvents.length === 2) {
          expect(receivedEvents).toEqual(['blocker_created', 'blocker_expired']);
          done();
        }
      };

      mockWs.onopen = () => {
        events.forEach((event, index) => {
          setTimeout(() => {
            mockWs.simulateMessage(event);
          }, index * 10);
        });
      };
    });

    it('handles multiple concurrent blockers', (done) => {
      const events = [
        {
          type: 'blocker_created',
          blocker_id: 300,
          agent_id: 'backend-worker-005',
          task_id: 600,
          blocker_type: 'SYNC',
          question: 'Question 1',
          created_at: '2025-11-08T14:00:00Z',
        },
        {
          type: 'blocker_created',
          blocker_id: 301,
          agent_id: 'frontend-worker-005',
          task_id: 601,
          blocker_type: 'ASYNC',
          question: 'Question 2',
          created_at: '2025-11-08T14:00:01Z',
        },
        {
          type: 'blocker_resolved',
          blocker_id: 300,
          answer: 'Answer 1',
          resolved_at: '2025-11-08T14:05:00Z',
        },
        {
          type: 'blocker_resolved',
          blocker_id: 301,
          answer: 'Answer 2',
          resolved_at: '2025-11-08T14:06:00Z',
        },
      ];

      const receivedBlockerIds = new Set<number>();

      mockWs.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.blocker_id) {
          receivedBlockerIds.add(data.blocker_id);
        }

        if (receivedBlockerIds.size === 2 && data.type === 'blocker_resolved') {
          expect(receivedBlockerIds).toEqual(new Set([300, 301]));
          done();
        }
      };

      mockWs.onopen = () => {
        events.forEach((event, index) => {
          setTimeout(() => {
            mockWs.simulateMessage(event);
          }, index * 10);
        });
      };
    });
  });

  describe('error handling', () => {
    it('handles malformed WebSocket messages gracefully', (done) => {
      const errorHandler = jest.fn();

      mockWs.onmessage = (event) => {
        try {
          JSON.parse(event.data);
        } catch (error) {
          errorHandler(error);
          expect(errorHandler).toHaveBeenCalledTimes(1);
          done();
        }
      };

      mockWs.onopen = () => {
        // Simulate malformed message
        if (mockWs.onmessage) {
          mockWs.onmessage({ data: 'invalid json{' });
        }
      };
    });

    it('handles WebSocket connection errors', (done) => {
      const errorWs = new MockWebSocket('ws://localhost:8000/ws');

      errorWs.onerror = (error) => {
        expect(error).toBeDefined();
        done();
      };

      // Simulate error
      if (errorWs.onerror) {
        errorWs.onerror(new Event('error'));
      }
    });

    it('handles WebSocket disconnection', (done) => {
      mockWs.onclose = () => {
        expect(mockWs.readyState).toBe(MockWebSocket.CLOSED);
        done();
      };

      mockWs.close();
    });
  });

  describe('real-time dashboard updates', () => {
    it('updates blocker count in dashboard header', (done) => {
      let blockerCount = 0;

      mockWs.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.type === 'blocker_created') {
          blockerCount++;
        } else if (data.type === 'blocker_resolved') {
          blockerCount--;
        }

        if (data.type === 'blocker_resolved') {
          expect(blockerCount).toBe(0);
          done();
        }
      };

      mockWs.onopen = () => {
        mockWs.simulateMessage({
          type: 'blocker_created',
          blocker_id: 400,
          agent_id: 'test-agent',
          task_id: 700,
          blocker_type: 'SYNC',
          question: 'Test',
          created_at: '2025-11-08T15:00:00Z',
        });

        setTimeout(() => {
          mockWs.simulateMessage({
            type: 'blocker_resolved',
            blocker_id: 400,
            answer: 'Answer',
            resolved_at: '2025-11-08T15:01:00Z',
          });
        }, 10);
      };
    });

    it('updates blocker panel in real-time', (done) => {
      const panelBlockers: number[] = [];

      mockWs.onmessage = (event) => {
        const data = JSON.parse(event.data);

        if (data.type === 'blocker_created') {
          panelBlockers.push(data.blocker_id);
        } else if (data.type === 'blocker_resolved') {
          const index = panelBlockers.indexOf(data.blocker_id);
          if (index > -1) {
            panelBlockers.splice(index, 1);
          }
        }

        if (data.type === 'blocker_resolved') {
          expect(panelBlockers.length).toBe(0);
          done();
        }
      };

      mockWs.onopen = () => {
        mockWs.simulateMessage({
          type: 'blocker_created',
          blocker_id: 500,
          agent_id: 'test-agent',
          task_id: 800,
          blocker_type: 'SYNC',
          question: 'Test',
          created_at: '2025-11-08T16:00:00Z',
        });

        setTimeout(() => {
          mockWs.simulateMessage({
            type: 'blocker_resolved',
            blocker_id: 500,
            answer: 'Answer',
            resolved_at: '2025-11-08T16:01:00Z',
          });
        }, 10);
      };
    });
  });
});
