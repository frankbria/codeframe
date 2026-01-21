/**
 * Shared Test Utilities for DiscoveryProgress Component Tests
 * 
 * This file contains common mocks, setup functions, test fixtures,
 * and helper functions used across all DiscoveryProgress test files.
 */

import { authFetch } from '@/lib/api-client';
import type { DiscoveryProgressResponse } from '@/types/api';

// Re-export testing library functions for convenience
export { render, screen, waitFor, fireEvent, act } from '@testing-library/react';
export { default as DiscoveryProgress } from '@/components/DiscoveryProgress';
export { projectsApi, tasksApi } from '@/lib/api';
export type { DiscoveryProgressResponse };

// =============================================================================
// Mock Functions
// =============================================================================

export const mockStartProject = jest.fn();
export const mockRestartDiscovery = jest.fn();
export const mockRetryPrdGeneration = jest.fn();
export const mockGenerateTasks = jest.fn();
export const mockGetPRD = jest.fn();
export const mockTasksList = jest.fn();

// =============================================================================
// WebSocket Mock
// =============================================================================

export type MessageHandler = (message: Record<string, unknown>) => void;
export const mockMessageHandlers: MessageHandler[] = [];

export const mockWsClient = {
  onMessage: jest.fn((handler: MessageHandler) => {
    mockMessageHandlers.push(handler);
    return () => {
      const index = mockMessageHandlers.indexOf(handler);
      if (index > -1) mockMessageHandlers.splice(index, 1);
    };
  }),
  connect: jest.fn(),
  disconnect: jest.fn(),
  subscribe: jest.fn(),
};

// Helper to simulate WebSocket messages
export const simulateWsMessage = (message: Record<string, unknown>) => {
  mockMessageHandlers.forEach(handler => handler(message));
};

// =============================================================================
// Mock Modules Setup
// =============================================================================

// Mock Hugeicons - comprehensive mock for all icons used in DiscoveryProgress and shadcn/ui components
jest.mock('@hugeicons/react', () => {
  const createMockIcon = (name: string, testId: string) => {
    const Icon = ({ className }: { className?: string }) => (
      <svg className={className} data-testid={testId} aria-hidden="true" />
    );
    Icon.displayName = name;
    return Icon;
  };

  return {
    // DiscoveryProgress icons
    Cancel01Icon: createMockIcon('Cancel01Icon', 'cancel-icon'),
    CheckmarkCircle01Icon: createMockIcon('CheckmarkCircle01Icon', 'checkmark-icon'),
    Alert02Icon: createMockIcon('Alert02Icon', 'alert-icon'),
    AlertDiamondIcon: createMockIcon('AlertDiamondIcon', 'alert-diamond-icon'),
    Idea01Icon: createMockIcon('Idea01Icon', 'idea-icon'),
    // shadcn/ui Dialog component icons
    Tick01Icon: createMockIcon('Tick01Icon', 'tick-icon'),
    ArrowDown01Icon: createMockIcon('ArrowDown01Icon', 'arrow-down-icon'),
    ArrowUp01Icon: createMockIcon('ArrowUp01Icon', 'arrow-up-icon'),
    CheckmarkSquare01Icon: createMockIcon('CheckmarkSquare01Icon', 'checkmark-square-icon'),
    CircleIcon: createMockIcon('CircleIcon', 'circle-icon'),
  };
});

// Mock the API
jest.mock('@/lib/api', () => ({
  projectsApi: {
    getDiscoveryProgress: jest.fn(),
    startProject: (...args: unknown[]) => mockStartProject(...args),
    restartDiscovery: (...args: unknown[]) => mockRestartDiscovery(...args),
    retryPrdGeneration: (...args: unknown[]) => mockRetryPrdGeneration(...args),
    generateTasks: (...args: unknown[]) => mockGenerateTasks(...args),
    getPRD: (...args: unknown[]) => mockGetPRD(...args),
  },
  tasksApi: {
    list: (...args: unknown[]) => mockTasksList(...args),
  },
}));

// Mock WebSocket client
jest.mock('@/lib/websocket', () => ({
  getWebSocketClient: () => mockWsClient,
}));

// Mock the authenticated fetch
jest.mock('@/lib/api-client', () => ({
  authFetch: jest.fn(),
}));

export const mockAuthFetch = authFetch as jest.MockedFunction<typeof authFetch>;

// Mock child components
jest.mock('@/components/ProgressBar', () => {
  return function MockProgressBar({ percentage, label }: { percentage: number; label?: string }) {
    return (
      <div data-testid="mock-progress-bar">
        {label && <span>{label}</span>}
        <span>{percentage}%</span>
      </div>
    );
  };
});

jest.mock('@/components/PhaseIndicator', () => {
  return function MockPhaseIndicator({ phase }: { phase: string }) {
    return <span data-testid="mock-phase-indicator">{phase}</span>;
  };
});

// =============================================================================
// Common Setup Functions
// =============================================================================

/**
 * Reset all mocks before each test
 */
export const setupMocks = () => {
  jest.clearAllMocks();
  jest.useFakeTimers();
  mockAuthFetch.mockReset();
  mockStartProject.mockReset();
  mockRestartDiscovery.mockReset();
  mockRetryPrdGeneration.mockReset();
  mockGenerateTasks.mockReset();
  mockGetPRD.mockReset();
  mockTasksList.mockReset();
  mockMessageHandlers.length = 0;
};

/**
 * Cleanup after each test
 */
export const cleanupMocks = () => {
  jest.runOnlyPendingTimers();
  jest.useRealTimers();
};

// =============================================================================
// Test Data Fixtures
// =============================================================================

export const createDiscoveryResponse = (
  overrides?: Partial<DiscoveryProgressResponse>
): DiscoveryProgressResponse => ({
  project_id: 1,
  phase: 'discovery',
  discovery: {
    state: 'discovering',
    progress_percentage: 50,
    answered_count: 5,
    total_required: 10,
  },
  ...overrides,
});

export const createIdleDiscovery = (): DiscoveryProgressResponse => ({
  project_id: 1,
  phase: 'discovery',
  discovery: {
    state: 'idle',
    progress_percentage: 0,
    answered_count: 0,
    total_required: 10,
  },
});

export const createDiscoveringWithQuestion = (questionText?: string): DiscoveryProgressResponse => ({
  project_id: 1,
  phase: 'discovery',
  discovery: {
    state: 'discovering',
    progress_percentage: 10,
    answered_count: 2,
    total_required: 20,
    current_question: {
      id: 'q1',
      category: 'problem',
      question: questionText || 'What problem does your project solve?',
    },
  },
});

export const createCompletedDiscovery = (): DiscoveryProgressResponse => ({
  project_id: 1,
  phase: 'planning',
  discovery: {
    state: 'completed',
    progress_percentage: 100,
    answered_count: 20,
    total_required: 20,
  },
});

export const createDiscoveringNoQuestion = (): DiscoveryProgressResponse => ({
  project_id: 1,
  phase: 'discovery',
  discovery: {
    state: 'discovering',
    progress_percentage: 0,
    answered_count: 0,
    total_required: 10,
  },
});
