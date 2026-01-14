/**
 * Dashboard type definitions for tab management
 * Feature: 013-context-panel-integration
 */

export type DashboardTab = 'overview' | 'tasks' | 'pull-requests' | 'quality-gates' | 'checkpoints' | 'metrics' | 'context';

export interface DashboardState {
  activeTab: DashboardTab;
  selectedAgentId: string | null;
}
