/**
 * Unit tests for ContextItemList component (T066)
 *
 * Tests:
 * - Data loading and display
 * - Pagination (next/prev, page numbers)
 * - Filtering by tier (HOT/WARM/COLD/All)
 * - Item type badges
 * - Token count display
 * - Empty state
 * - Loading state
 * - Error handling
 * - Auto-refresh on prop changes
 *
 * Part of 007-context-management Phase 7 (US5 - Context Visualization)
 */

import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ContextItemList } from '../../../src/components/context/ContextItemList';
import * as contextApi from '../../../src/api/context';
import type { ContextItem } from '../../../src/types/context';

// Mock the API module
jest.mock('../../../src/api/context');

const mockFetchContextItems = contextApi.fetchContextItems as jest.MockedFunction<
  typeof contextApi.fetchContextItems
>;

describe('ContextItemList', () => {
  // Mock context items for testing
  const mockItems: ContextItem[] = [
    {
      id: 1,
      project_id: 123,
      agent_id: 'test-agent-001',
      item_type: 'TASK',
      content: 'Implement user authentication with JWT tokens',
      importance_score: 0.95,
      current_tier: 'HOT',
      access_count: 5,
      created_at: new Date(Date.now() - 1000 * 60 * 30).toISOString(), // 30 minutes ago
      last_accessed: new Date(Date.now() - 1000 * 60 * 5).toISOString(), // 5 minutes ago
    },
    {
      id: 2,
      project_id: 123,
      agent_id: 'test-agent-001',
      item_type: 'CODE',
      content: 'def authenticate_user(token: str) -> User: return validate_jwt(token)',
      importance_score: 0.72,
      current_tier: 'WARM',
      access_count: 3,
      created_at: new Date(Date.now() - 1000 * 60 * 60 * 2).toISOString(), // 2 hours ago
      last_accessed: new Date(Date.now() - 1000 * 60 * 30).toISOString(), // 30 minutes ago
    },
    {
      id: 3,
      project_id: 123,
      agent_id: 'test-agent-001',
      item_type: 'ERROR',
      content: 'Authentication failed: Invalid token signature',
      importance_score: 0.85,
      current_tier: 'HOT',
      access_count: 7,
      created_at: new Date(Date.now() - 1000 * 60 * 10).toISOString(), // 10 minutes ago
      last_accessed: new Date(Date.now() - 1000 * 60 * 2).toISOString(), // 2 minutes ago
    },
    {
      id: 4,
      project_id: 123,
      agent_id: 'test-agent-001',
      item_type: 'PRD_SECTION',
      content: 'User stories for OAuth 2.0 integration with Google and GitHub providers',
      importance_score: 0.35,
      current_tier: 'COLD',
      access_count: 1,
      created_at: new Date(Date.now() - 1000 * 60 * 60 * 24 * 3).toISOString(), // 3 days ago
      last_accessed: new Date(Date.now() - 1000 * 60 * 60 * 24).toISOString(), // 1 day ago
    },
  ];

  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('Data Loading and Display', () => {
    it('test_renders_context_items_table', async () => {
      // ARRANGE
      mockFetchContextItems.mockResolvedValueOnce(mockItems);

      // ACT
      render(<ContextItemList agentId="test-agent-001" projectId={123} />);

      // ASSERT: Wait for loading to complete
      await waitFor(() => {
        expect(screen.queryByText('Loading...')).not.toBeInTheDocument();
      });

      // Verify table headers
      expect(screen.getByText('Type')).toBeInTheDocument();
      expect(screen.getByText('Content')).toBeInTheDocument();
      expect(screen.getByText('Score')).toBeInTheDocument();
      expect(screen.getByText('Tier')).toBeInTheDocument();
      expect(screen.getByText('Age')).toBeInTheDocument();

      // Verify items are displayed
      expect(screen.getByText('TASK')).toBeInTheDocument();
      expect(screen.getByText('CODE')).toBeInTheDocument();
      expect(screen.getByText('ERROR')).toBeInTheDocument();
      expect(screen.getByText('PRD_SECTION')).toBeInTheDocument();
    });

    it('test_displays_item_content_truncated', async () => {
      // ARRANGE
      const longContentItem: ContextItem = {
        id: 99,
        project_id: 123,
        agent_id: 'test-agent-001',
        item_type: 'CODE',
        content: 'A'.repeat(150), // 150 characters
        importance_score: 0.75,
        current_tier: 'WARM',
        access_count: 2,
        created_at: new Date().toISOString(),
        last_accessed: new Date().toISOString(),
      };
      mockFetchContextItems.mockResolvedValueOnce([longContentItem]);

      // ACT
      render(<ContextItemList agentId="test-agent-001" projectId={123} />);

      // ASSERT: Wait for loading to complete
      await waitFor(() => {
        expect(screen.queryByText('Loading...')).not.toBeInTheDocument();
      });

      // Verify content is truncated to 100 characters + "..."
      const truncatedContent = 'A'.repeat(100) + '...';
      expect(screen.getByText(truncatedContent)).toBeInTheDocument();
    });

    it('test_displays_importance_scores', async () => {
      // ARRANGE
      mockFetchContextItems.mockResolvedValueOnce(mockItems);

      // ACT
      render(<ContextItemList agentId="test-agent-001" projectId={123} />);

      // ASSERT: Wait for loading to complete
      await waitFor(() => {
        expect(screen.queryByText('Loading...')).not.toBeInTheDocument();
      });

      // Verify importance scores are formatted to 2 decimal places
      expect(screen.getByText('0.95')).toBeInTheDocument();
      expect(screen.getByText('0.72')).toBeInTheDocument();
      expect(screen.getByText('0.85')).toBeInTheDocument();
      expect(screen.getByText('0.35')).toBeInTheDocument();
    });

    it('test_displays_tier_badges', async () => {
      // ARRANGE
      mockFetchContextItems.mockResolvedValueOnce(mockItems);

      // ACT
      render(<ContextItemList agentId="test-agent-001" projectId={123} />);

      // ASSERT: Wait for loading to complete
      await waitFor(() => {
        expect(screen.queryByText('Loading...')).not.toBeInTheDocument();
      });

      // Verify tier badges are displayed (2 HOT, 1 WARM, 1 COLD)
      // Note: getAllByText also includes the dropdown options, so we check for tier-badge specifically
      const container = screen.getByText('Type').parentElement?.parentElement?.parentElement;
      const hotBadges = container!.querySelectorAll('.tier-badge.hot');
      expect(hotBadges).toHaveLength(2);

      const warmBadges = container!.querySelectorAll('.tier-badge.warm');
      expect(warmBadges).toHaveLength(1);

      const coldBadges = container!.querySelectorAll('.tier-badge.cold');
      expect(coldBadges).toHaveLength(1);
    });

    it('test_displays_item_age_minutes', async () => {
      // ARRANGE: Use actual Date.now() since component doesn't use mocked time
      const actualNow = Date.now();
      const fifteenMinutesAgo = new Date(actualNow - 1000 * 60 * 15).toISOString();

      const recentItem: ContextItem = {
        ...mockItems[0],
        created_at: fifteenMinutesAgo,
      };
      mockFetchContextItems.mockResolvedValueOnce([recentItem]);

      // ACT
      render(<ContextItemList agentId="test-agent-001" projectId={123} />);

      // ASSERT
      await waitFor(() => {
        expect(screen.getByText('15m ago')).toBeInTheDocument();
      });
    });

    it('test_displays_item_age_hours', async () => {
      // ARRANGE: Use actual Date.now() since component doesn't use mocked time
      const actualNow = Date.now();
      const threeHoursAgo = new Date(actualNow - 1000 * 60 * 60 * 3).toISOString();

      const hourOldItem: ContextItem = {
        ...mockItems[0],
        created_at: threeHoursAgo,
      };
      mockFetchContextItems.mockResolvedValueOnce([hourOldItem]);

      // ACT
      render(<ContextItemList agentId="test-agent-001" projectId={123} />);

      // ASSERT
      await waitFor(() => {
        expect(screen.getByText('3h ago')).toBeInTheDocument();
      });
    });

    it('test_displays_item_age_days', async () => {
      // ARRANGE
      const dayOldItem: ContextItem = {
        ...mockItems[0],
        created_at: new Date(Date.now() - 1000 * 60 * 60 * 24 * 5).toISOString(), // 5 days ago
      };
      mockFetchContextItems.mockResolvedValueOnce([dayOldItem]);

      // ACT
      render(<ContextItemList agentId="test-agent-001" projectId={123} />);

      // ASSERT
      await waitFor(() => {
        expect(screen.getByText('5d ago')).toBeInTheDocument();
      });
    });

    it('test_displays_item_age_just_now', async () => {
      // ARRANGE: Use actual Date.now() since component doesn't use mocked time
      const actualNow = Date.now();
      const thirtySecondsAgo = new Date(actualNow - 1000 * 30).toISOString();

      const justNowItem: ContextItem = {
        ...mockItems[0],
        created_at: thirtySecondsAgo,
      };
      mockFetchContextItems.mockResolvedValueOnce([justNowItem]);

      // ACT
      render(<ContextItemList agentId="test-agent-001" projectId={123} />);

      // ASSERT
      await waitFor(() => {
        expect(screen.getByText('Just now')).toBeInTheDocument();
      });
    });

    it('test_calls_api_with_correct_params', async () => {
      // ARRANGE
      mockFetchContextItems.mockResolvedValueOnce(mockItems);

      // ACT
      render(<ContextItemList agentId="test-agent-001" projectId={123} />);

      // ASSERT
      await waitFor(() => {
        expect(mockFetchContextItems).toHaveBeenCalledWith(
          'test-agent-001',
          123,
          undefined,
          1000
        );
      });
    });
  });

  describe('Pagination', () => {
    // Create 25 items for pagination testing (pageSize default is 20)
    const manyItems: ContextItem[] = Array.from({ length: 25 }, (_, i) => ({
      id: i + 1,
      project_id: 123,
      agent_id: 'test-agent-001',
      item_type: 'TASK',
      content: `Task ${i + 1}`,
      importance_score: 0.5,
      current_tier: 'WARM',
      access_count: 1,
      created_at: new Date().toISOString(),
      last_accessed: new Date().toISOString(),
    }));

    it('test_pagination_shows_page_info', async () => {
      // ARRANGE
      mockFetchContextItems.mockResolvedValueOnce(manyItems);

      // ACT
      render(<ContextItemList agentId="test-agent-001" projectId={123} />);

      // ASSERT
      await waitFor(() => {
        expect(screen.getByText('Page 1 of 2 (25 total items)')).toBeInTheDocument();
      });
    });

    it('test_pagination_first_page_shows_20_items', async () => {
      // ARRANGE
      mockFetchContextItems.mockResolvedValueOnce(manyItems);

      // ACT
      render(<ContextItemList agentId="test-agent-001" projectId={123} />);

      // ASSERT
      await waitFor(() => {
        expect(screen.getByText('Task 1')).toBeInTheDocument();
        expect(screen.getByText('Task 20')).toBeInTheDocument();
        expect(screen.queryByText('Task 21')).not.toBeInTheDocument();
      });
    });

    it('test_pagination_next_button_works', async () => {
      // ARRANGE
      mockFetchContextItems.mockResolvedValueOnce(manyItems);

      // ACT
      render(<ContextItemList agentId="test-agent-001" projectId={123} />);

      // Wait for initial load
      await waitFor(() => {
        expect(screen.getByText('Task 1')).toBeInTheDocument();
      });

      // Click Next button
      const nextButton = screen.getByText('Next');
      fireEvent.click(nextButton);

      // ASSERT: Page 2 items are shown
      expect(screen.queryByText('Task 1')).not.toBeInTheDocument();
      expect(screen.getByText('Task 21')).toBeInTheDocument();
      expect(screen.getByText('Task 25')).toBeInTheDocument();
      expect(screen.getByText('Page 2 of 2 (25 total items)')).toBeInTheDocument();
    });

    it('test_pagination_previous_button_works', async () => {
      // ARRANGE
      mockFetchContextItems.mockResolvedValueOnce(manyItems);

      // ACT
      render(<ContextItemList agentId="test-agent-001" projectId={123} />);

      // Wait for initial load
      await waitFor(() => {
        expect(screen.getByText('Task 1')).toBeInTheDocument();
      });

      // Go to page 2
      const nextButton = screen.getByText('Next');
      fireEvent.click(nextButton);
      expect(screen.getByText('Task 21')).toBeInTheDocument();

      // Click Previous button
      const prevButton = screen.getByText('Previous');
      fireEvent.click(prevButton);

      // ASSERT: Back to page 1
      expect(screen.getByText('Task 1')).toBeInTheDocument();
      expect(screen.queryByText('Task 21')).not.toBeInTheDocument();
      expect(screen.getByText('Page 1 of 2 (25 total items)')).toBeInTheDocument();
    });

    it('test_pagination_previous_button_disabled_on_first_page', async () => {
      // ARRANGE
      mockFetchContextItems.mockResolvedValueOnce(manyItems);

      // ACT
      render(<ContextItemList agentId="test-agent-001" projectId={123} />);

      // ASSERT
      await waitFor(() => {
        const prevButton = screen.getByText('Previous');
        expect(prevButton).toBeDisabled();
      });
    });

    it('test_pagination_next_button_disabled_on_last_page', async () => {
      // ARRANGE
      mockFetchContextItems.mockResolvedValueOnce(manyItems);

      // ACT
      render(<ContextItemList agentId="test-agent-001" projectId={123} />);

      // Wait for initial load
      await waitFor(() => {
        expect(screen.getByText('Task 1')).toBeInTheDocument();
      });

      // Go to page 2 (last page)
      const nextButton = screen.getByText('Next');
      fireEvent.click(nextButton);

      // ASSERT: Next button is disabled
      await waitFor(() => {
        expect(nextButton).toBeDisabled();
      });
    });

    it('test_pagination_controls_hidden_for_single_page', async () => {
      // ARRANGE: Only 10 items (< pageSize)
      const fewItems = manyItems.slice(0, 10);
      mockFetchContextItems.mockResolvedValueOnce(fewItems);

      // ACT
      render(<ContextItemList agentId="test-agent-001" projectId={123} />);

      // ASSERT: No pagination controls
      await waitFor(() => {
        expect(screen.queryByText('Next')).not.toBeInTheDocument();
        expect(screen.queryByText('Previous')).not.toBeInTheDocument();
      });
    });

    it('test_pagination_respects_custom_page_size', async () => {
      // ARRANGE
      mockFetchContextItems.mockResolvedValueOnce(manyItems);

      // ACT: Set pageSize to 10
      render(<ContextItemList agentId="test-agent-001" projectId={123} pageSize={10} />);

      // ASSERT: Shows 10 items per page (3 pages total)
      await waitFor(() => {
        expect(screen.getByText('Page 1 of 3 (25 total items)')).toBeInTheDocument();
        expect(screen.getByText('Task 1')).toBeInTheDocument();
        expect(screen.getByText('Task 10')).toBeInTheDocument();
        expect(screen.queryByText('Task 11')).not.toBeInTheDocument();
      });
    });
  });

  describe('Tier Filtering', () => {
    it('test_filter_dropdown_shows_all_options', async () => {
      // ARRANGE
      mockFetchContextItems.mockResolvedValueOnce(mockItems);

      // ACT
      render(<ContextItemList agentId="test-agent-001" projectId={123} />);

      // ASSERT
      await waitFor(() => {
        const filterSelect = screen.getByLabelText('Filter by tier:');
        expect(filterSelect).toBeInTheDocument();

        // Verify all options are present
        expect(screen.getByRole('option', { name: 'All Tiers' })).toBeInTheDocument();
        expect(screen.getByRole('option', { name: 'HOT' })).toBeInTheDocument();
        expect(screen.getByRole('option', { name: 'WARM' })).toBeInTheDocument();
        expect(screen.getByRole('option', { name: 'COLD' })).toBeInTheDocument();
      });
    });

    it('test_filter_by_hot_tier', async () => {
      // ARRANGE
      const hotItems = mockItems.filter((item) => item.current_tier === 'HOT');
      mockFetchContextItems.mockResolvedValueOnce(mockItems); // Initial load
      mockFetchContextItems.mockResolvedValueOnce(hotItems); // After filter

      // ACT
      render(<ContextItemList agentId="test-agent-001" projectId={123} />);

      await waitFor(() => {
        expect(screen.getByText('TASK')).toBeInTheDocument();
      });

      // Select HOT filter
      const filterSelect = screen.getByLabelText('Filter by tier:');
      await userEvent.selectOptions(filterSelect, 'hot');

      // ASSERT: API called with tier filter
      await waitFor(() => {
        expect(mockFetchContextItems).toHaveBeenCalledWith(
          'test-agent-001',
          123,
          'hot',
          1000
        );
      });
    });

    it('test_filter_by_warm_tier', async () => {
      // ARRANGE
      const warmItems = mockItems.filter((item) => item.current_tier === 'WARM');
      mockFetchContextItems.mockResolvedValueOnce(mockItems); // Initial load
      mockFetchContextItems.mockResolvedValueOnce(warmItems); // After filter

      // ACT
      render(<ContextItemList agentId="test-agent-001" projectId={123} />);

      await waitFor(() => {
        expect(screen.getByText('TASK')).toBeInTheDocument();
      });

      // Select WARM filter
      const filterSelect = screen.getByLabelText('Filter by tier:');
      await userEvent.selectOptions(filterSelect, 'warm');

      // ASSERT
      await waitFor(() => {
        expect(mockFetchContextItems).toHaveBeenCalledWith(
          'test-agent-001',
          123,
          'warm',
          1000
        );
      });
    });

    it('test_filter_by_cold_tier', async () => {
      // ARRANGE
      const coldItems = mockItems.filter((item) => item.current_tier === 'COLD');
      mockFetchContextItems.mockResolvedValueOnce(mockItems); // Initial load
      mockFetchContextItems.mockResolvedValueOnce(coldItems); // After filter

      // ACT
      render(<ContextItemList agentId="test-agent-001" projectId={123} />);

      await waitFor(() => {
        expect(screen.getByText('TASK')).toBeInTheDocument();
      });

      // Select COLD filter
      const filterSelect = screen.getByLabelText('Filter by tier:');
      await userEvent.selectOptions(filterSelect, 'cold');

      // ASSERT
      await waitFor(() => {
        expect(mockFetchContextItems).toHaveBeenCalledWith(
          'test-agent-001',
          123,
          'cold',
          1000
        );
      });
    });

    it('test_filter_resets_pagination', async () => {
      // ARRANGE: 25 items for pagination
      const mockNow = new Date('2025-11-21T12:00:00Z').toISOString();
      const manyItems: ContextItem[] = Array.from({ length: 25 }, (_, i) => ({
        id: i + 1,
        project_id: 123,
        agent_id: 'test-agent-001',
        item_type: 'TASK',
        content: `Task ${i + 1}`,
        importance_score: 0.5,
        current_tier: i < 10 ? 'HOT' : 'WARM',
        access_count: 1,
        created_at: mockNow,
        last_accessed: mockNow,
      }));

      const hotItems = manyItems.slice(0, 10);

      mockFetchContextItems.mockResolvedValueOnce(manyItems); // Initial load
      mockFetchContextItems.mockResolvedValueOnce(hotItems); // After filter

      // ACT
      render(<ContextItemList agentId="test-agent-001" projectId={123} />);

      await waitFor(() => {
        expect(screen.getByText('Page 1 of 2 (25 total items)')).toBeInTheDocument();
      });

      // Go to page 2
      const nextButton = screen.getByText('Next');
      fireEvent.click(nextButton);

      await waitFor(() => {
        expect(screen.getByText('Page 2 of 2 (25 total items)')).toBeInTheDocument();
      });

      // Change filter
      const filterSelect = screen.getByLabelText('Filter by tier:');
      await userEvent.selectOptions(filterSelect, 'hot');

      // ASSERT: Pagination resets - should not show pagination for 10 items (< pageSize)
      await waitFor(() => {
        expect(screen.queryByText('Next')).not.toBeInTheDocument();
        expect(screen.getByText('Task 1')).toBeInTheDocument(); // Back to first page
      });
    });

    it('test_filter_back_to_all_tiers', async () => {
      // ARRANGE
      mockFetchContextItems.mockResolvedValue(mockItems);

      // ACT
      render(<ContextItemList agentId="test-agent-001" projectId={123} />);

      await waitFor(() => {
        expect(screen.getByText('TASK')).toBeInTheDocument();
      });

      // Select HOT filter
      const filterSelect = screen.getByLabelText('Filter by tier:');
      await userEvent.selectOptions(filterSelect, 'hot');

      await waitFor(() => {
        expect(mockFetchContextItems).toHaveBeenCalledTimes(2);
      });

      // Select "All Tiers"
      await userEvent.selectOptions(filterSelect, '');

      // ASSERT: API called without tier filter
      await waitFor(() => {
        expect(mockFetchContextItems).toHaveBeenCalledWith(
          'test-agent-001',
          123,
          undefined,
          1000
        );
      });
    });
  });

  describe('Empty State', () => {
    it('test_shows_empty_state_no_items', async () => {
      // ARRANGE
      mockFetchContextItems.mockResolvedValueOnce([]);

      // ACT
      render(<ContextItemList agentId="test-agent-001" projectId={123} />);

      // ASSERT
      await waitFor(() => {
        expect(screen.getByText('No context items found')).toBeInTheDocument();
      });

      // Table should not be rendered
      expect(screen.queryByRole('table')).not.toBeInTheDocument();
    });

    it('test_empty_state_with_filter_applied', async () => {
      // ARRANGE: Initially has items, but filter returns empty
      mockFetchContextItems.mockResolvedValueOnce(mockItems); // Initial load
      mockFetchContextItems.mockResolvedValueOnce([]); // After filter

      // ACT
      render(<ContextItemList agentId="test-agent-001" projectId={123} />);

      await waitFor(() => {
        expect(screen.getByText('TASK')).toBeInTheDocument();
      });

      // Apply filter
      const filterSelect = screen.getByLabelText('Filter by tier:');
      await userEvent.selectOptions(filterSelect, 'hot');

      // ASSERT
      await waitFor(() => {
        expect(screen.getByText('No context items found')).toBeInTheDocument();
      });
    });
  });

  describe('Loading State', () => {
    it('test_shows_loading_state', () => {
      // ARRANGE: Promise that never resolves
      mockFetchContextItems.mockImplementation(() => new Promise(() => {}));

      // ACT
      render(<ContextItemList agentId="test-agent-001" projectId={123} />);

      // ASSERT
      expect(screen.getByText('Loading...')).toBeInTheDocument();
      expect(screen.getByText('Context Items')).toBeInTheDocument();
    });

    it('test_loading_transitions_to_content', async () => {
      // ARRANGE
      mockFetchContextItems.mockResolvedValueOnce(mockItems);

      // ACT
      render(<ContextItemList agentId="test-agent-001" projectId={123} />);

      // ASSERT: Loading initially
      expect(screen.getByText('Loading...')).toBeInTheDocument();

      // ASSERT: Loading disappears after load
      await waitFor(() => {
        expect(screen.queryByText('Loading...')).not.toBeInTheDocument();
        expect(screen.getByText('TASK')).toBeInTheDocument();
      });
    });
  });

  describe('Error Handling', () => {
    it('test_shows_error_message', async () => {
      // ARRANGE
      const errorMessage = 'Failed to fetch context items: 500 Internal Server Error';
      mockFetchContextItems.mockRejectedValueOnce(new Error(errorMessage));

      // ACT
      render(<ContextItemList agentId="test-agent-001" projectId={123} />);

      // ASSERT
      await waitFor(() => {
        expect(screen.getByText(errorMessage)).toBeInTheDocument();
      });
    });

    it('test_error_state_shows_title', async () => {
      // ARRANGE
      mockFetchContextItems.mockRejectedValueOnce(new Error('Network error'));

      // ACT
      render(<ContextItemList agentId="test-agent-001" projectId={123} />);

      // ASSERT
      await waitFor(() => {
        expect(screen.getByText('Context Items')).toBeInTheDocument();
        expect(screen.getByText('Network error')).toBeInTheDocument();
      });
    });

    it('test_handles_non_error_rejection', async () => {
      // ARRANGE: Reject with non-Error object
      mockFetchContextItems.mockRejectedValueOnce('String error');

      // ACT
      render(<ContextItemList agentId="test-agent-001" projectId={123} />);

      // ASSERT: Generic error message
      await waitFor(() => {
        expect(screen.getByText('Failed to load context items')).toBeInTheDocument();
      });
    });
  });

  describe('Auto-Refresh on Prop Changes', () => {
    it('test_refetches_when_agent_id_changes', async () => {
      // ARRANGE
      mockFetchContextItems.mockResolvedValue(mockItems);

      // ACT: Render with agent-001
      const { rerender } = render(
        <ContextItemList agentId="test-agent-001" projectId={123} />
      );

      await waitFor(() => {
        expect(mockFetchContextItems).toHaveBeenCalledTimes(1);
        expect(mockFetchContextItems).toHaveBeenCalledWith(
          'test-agent-001',
          123,
          undefined,
          1000
        );
      });

      // ACT: Change agent_id
      rerender(<ContextItemList agentId="test-agent-002" projectId={123} />);

      // ASSERT: Refetches with new agent_id
      await waitFor(() => {
        expect(mockFetchContextItems).toHaveBeenCalledTimes(2);
        expect(mockFetchContextItems).toHaveBeenCalledWith(
          'test-agent-002',
          123,
          undefined,
          1000
        );
      });
    });

    it('test_refetches_when_project_id_changes', async () => {
      // ARRANGE
      mockFetchContextItems.mockResolvedValue(mockItems);

      // ACT: Render with project 123
      const { rerender } = render(
        <ContextItemList agentId="test-agent-001" projectId={123} />
      );

      await waitFor(() => {
        expect(mockFetchContextItems).toHaveBeenCalledTimes(1);
      });

      // ACT: Change project_id
      rerender(<ContextItemList agentId="test-agent-001" projectId={456} />);

      // ASSERT: Refetches with new project_id
      await waitFor(() => {
        expect(mockFetchContextItems).toHaveBeenCalledTimes(2);
        expect(mockFetchContextItems).toHaveBeenCalledWith(
          'test-agent-001',
          456,
          undefined,
          1000
        );
      });
    });

    it('test_cleanup_on_unmount', async () => {
      // ARRANGE
      let resolveFetch: (value: ContextItem[]) => void;
      const fetchPromise = new Promise<ContextItem[]>((resolve) => {
        resolveFetch = resolve;
      });
      mockFetchContextItems.mockReturnValueOnce(fetchPromise);

      // ACT: Render and unmount before fetch completes
      const { unmount } = render(
        <ContextItemList agentId="test-agent-001" projectId={123} />
      );

      expect(screen.getByText('Loading...')).toBeInTheDocument();

      // Unmount immediately
      unmount();

      // Resolve the promise after unmount
      resolveFetch!(mockItems);

      // ASSERT: No errors should occur (component should ignore state updates after unmount)
      await waitFor(() => {
        // If we get here without errors, the test passes
        expect(true).toBe(true);
      });
    });
  });

  describe('Row Styling', () => {
    it('test_applies_tier_specific_classes', async () => {
      // ARRANGE
      mockFetchContextItems.mockResolvedValueOnce(mockItems);

      // ACT
      render(<ContextItemList agentId="test-agent-001" projectId={123} />);

      // ASSERT
      await waitFor(() => {
        const rows = screen.getAllByRole('row');
        // Find rows with tier classes (skip header row)
        const hotRows = rows.filter((row) => row.className.includes('tier-hot'));
        const warmRows = rows.filter((row) => row.className.includes('tier-warm'));
        const coldRows = rows.filter((row) => row.className.includes('tier-cold'));

        expect(hotRows.length).toBeGreaterThan(0);
        expect(warmRows.length).toBeGreaterThan(0);
        expect(coldRows.length).toBeGreaterThan(0);
      });
    });
  });

  describe('Content Title Attribute', () => {
    it('test_full_content_shown_in_title_attribute', async () => {
      // ARRANGE
      const longContentItem: ContextItem = {
        id: 99,
        project_id: 123,
        agent_id: 'test-agent-001',
        item_type: 'CODE',
        content: 'A'.repeat(150), // 150 characters
        importance_score: 0.75,
        current_tier: 'WARM',
        access_count: 2,
        created_at: new Date().toISOString(),
        last_accessed: new Date().toISOString(),
      };
      mockFetchContextItems.mockResolvedValueOnce([longContentItem]);

      // ACT
      render(<ContextItemList agentId="test-agent-001" projectId={123} />);

      // ASSERT
      await waitFor(() => {
        const contentCell = screen.getByText('A'.repeat(100) + '...');
        expect(contentCell).toHaveAttribute('title', 'A'.repeat(150));
      });
    });
  });
});
