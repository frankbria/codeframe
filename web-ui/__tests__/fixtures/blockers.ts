import type { Blocker } from '@/types/blocker';

/**
 * Test fixtures for blocker data
 * Used across multiple test files for consistent test data
 */

export const mockSyncBlocker: Blocker = {
  id: 1,
  agent_id: 'backend-worker-001',
  task_id: 123,
  blocker_type: 'SYNC',
  question: 'Should I use SQLite or PostgreSQL for this feature?',
  answer: null,
  status: 'PENDING',
  created_at: new Date('2025-11-08T10:00:00Z').toISOString(),
  resolved_at: null,
  agent_name: 'Backend Worker #1',
  task_title: 'Implement database layer',
  time_waiting_ms: 300000, // 5 minutes
};

export const mockAsyncBlocker: Blocker = {
  id: 2,
  agent_id: 'frontend-worker-002',
  task_id: 456,
  blocker_type: 'ASYNC',
  question: 'What color scheme should we use for the dashboard?',
  answer: null,
  status: 'PENDING',
  created_at: new Date('2025-11-08T08:00:00Z').toISOString(), // 2 hours before mockSyncBlocker
  resolved_at: null,
  agent_name: 'Frontend Worker #2',
  task_title: 'Build UI components',
  time_waiting_ms: 7200000, // 2 hours
};

export const mockResolvedBlocker: Blocker = {
  id: 3,
  agent_id: 'backend-worker-001',
  task_id: 123,
  blocker_type: 'SYNC',
  question: 'Which testing framework should we use for this feature?',
  answer: 'Use Jest to match existing codebase',
  status: 'RESOLVED',
  created_at: new Date('2025-11-08T09:00:00Z').toISOString(),
  resolved_at: new Date('2025-11-08T09:30:00Z').toISOString(),
  agent_name: 'Backend Worker #1',
  task_title: 'Implement database layer',
  time_waiting_ms: 1800000, // 30 minutes
};

export const mockExpiredBlocker: Blocker = {
  id: 4,
  agent_id: 'test-worker-003',
  task_id: 789,
  blocker_type: 'ASYNC',
  question: 'What testing framework should we use?',
  answer: null,
  status: 'EXPIRED',
  created_at: new Date('2025-11-07T10:00:00Z').toISOString(),
  resolved_at: null,
  agent_name: 'Test Worker #3',
  task_title: 'Set up testing infrastructure',
  time_waiting_ms: 86400000, // 24 hours
};

export const mockLongQuestionBlocker: Blocker = {
  id: 5,
  agent_id: 'backend-worker-001',
  task_id: 123,
  blocker_type: 'SYNC',
  question: 'This is a very long question that should be truncated because it exceeds the eighty character limit that we have set for the preview display in the blocker panel component',
  answer: null,
  status: 'PENDING',
  created_at: new Date('2025-11-08T10:00:00Z').toISOString(),
  resolved_at: null,
  agent_name: 'Backend Worker #1',
  task_title: 'Implement database layer',
  time_waiting_ms: 300000, // 5 minutes
};

export const mockShortQuestionBlocker: Blocker = {
  id: 6,
  agent_id: 'frontend-worker-002',
  task_id: 456,
  blocker_type: 'ASYNC',
  question: 'Which library should I use?',
  answer: null,
  status: 'PENDING',
  created_at: new Date('2025-11-08T10:00:00Z').toISOString(),
  resolved_at: null,
  agent_name: 'Frontend Worker #2',
  task_title: 'Build UI components',
  time_waiting_ms: 60000, // 1 minute
};

export const mockBlockerWithoutTask: Blocker = {
  id: 7,
  agent_id: 'orchestrator-001',
  task_id: null,
  blocker_type: 'SYNC',
  question: 'Should I proceed with the next phase?',
  answer: null,
  status: 'PENDING',
  created_at: new Date('2025-11-08T10:00:00Z').toISOString(),
  resolved_at: null,
  agent_name: 'Orchestrator Agent',
  task_title: undefined,
  time_waiting_ms: 180000, // 3 minutes
};

// Collections for sorting tests
export const mockBlockersUnsorted: Blocker[] = [
  mockAsyncBlocker,      // ASYNC, older
  mockSyncBlocker,       // SYNC, newer
  mockResolvedBlocker,   // RESOLVED (should be filtered out)
  mockExpiredBlocker,    // EXPIRED (should be filtered out)
];

export const mockBlockersSortedCorrectly: Blocker[] = [
  mockSyncBlocker,      // SYNC, newer
  mockAsyncBlocker,     // ASYNC, older
];

export const mockMultipleSyncBlockers: Blocker[] = [
  {
    ...mockSyncBlocker,
    id: 10,
    created_at: new Date('2025-11-08T09:00:00Z').toISOString(), // Older
  },
  {
    ...mockSyncBlocker,
    id: 11,
    created_at: new Date('2025-11-08T10:00:00Z').toISOString(), // Newer
  },
];

export const mockMultipleAsyncBlockers: Blocker[] = [
  {
    ...mockAsyncBlocker,
    id: 20,
    created_at: new Date('2025-11-08T07:00:00Z').toISOString(), // Older
  },
  {
    ...mockAsyncBlocker,
    id: 21,
    created_at: new Date('2025-11-08T08:00:00Z').toISOString(), // Newer
  },
];

export const mockEmptyBlockersList: Blocker[] = [];
