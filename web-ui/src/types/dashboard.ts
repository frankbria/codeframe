/**
 * Dashboard type definitions for tab management
 * Feature: 013-context-panel-integration
 */

export type DashboardTab = 'overview' | 'context' | 'checkpoints';

export interface DashboardState {
  activeTab: DashboardTab;
  selectedAgentId: string | null;
}
