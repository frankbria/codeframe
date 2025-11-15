/**
 * ContextItemList - Table displaying context items with filtering and pagination (T066)
 *
 * Displays context items in a table with:
 * - Columns: Type, Content (truncated), Score, Tier, Age
 * - Filterable by tier (dropdown)
 * - Pagination (20 per page)
 *
 * Part of 007-context-management Phase 7 (US5 - Context Visualization)
 */

import React, { useState, useEffect } from 'react';
import type { ContextItem, ContextTier } from '../../types/context';
import { fetchContextItems } from '../../api/context';

interface ContextItemListProps {
  /** Agent ID to display items for */
  agentId: string;
  /** Project ID the agent is working on */
  projectId: number;
  /** Items per page (default 20) */
  pageSize?: number;
}

/**
 * Calculate how long ago a timestamp was
 */
function getAge(timestamp: string): string {
  const now = new Date();
  const created = new Date(timestamp);
  const diffMs = now.getTime() - created.getTime();

  const diffMinutes = Math.floor(diffMs / (1000 * 60));
  const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (diffDays > 0) {
    return `${diffDays}d ago`;
  } else if (diffHours > 0) {
    return `${diffHours}h ago`;
  } else if (diffMinutes > 0) {
    return `${diffMinutes}m ago`;
  } else {
    return 'Just now';
  }
}

/**
 * Truncate content to max length
 */
function truncate(text: string, maxLength: number = 100): string {
  if (text.length <= maxLength) {
    return text;
  }
  return text.substring(0, maxLength) + '...';
}

/**
 * Table component for displaying context items
 */
export function ContextItemList({
  agentId,
  projectId,
  pageSize = 20,
}: ContextItemListProps): JSX.Element {
  const [items, setItems] = useState<ContextItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [tierFilter, setTierFilter] = useState<string>(''); // '' = all, 'hot', 'warm', 'cold'
  const [currentPage, setCurrentPage] = useState<number>(1);

  // Fetch items when filter changes
  useEffect(() => {
    let mounted = true;

    const loadItems = async () => {
      setLoading(true);
      try {
        const data = await fetchContextItems(
          agentId,
          projectId,
          tierFilter || undefined,
          1000 // Fetch all items (up to 1000)
        );
        if (mounted) {
          setItems(data);
          setError(null);
          setLoading(false);
          setCurrentPage(1); // Reset to first page when filter changes
        }
      } catch (err) {
        if (mounted) {
          setError(err instanceof Error ? err.message : 'Failed to load context items');
          setLoading(false);
        }
      }
    };

    loadItems();

    return () => {
      mounted = false;
    };
  }, [agentId, projectId, tierFilter]);

  // Pagination
  const startIndex = (currentPage - 1) * pageSize;
  const endIndex = startIndex + pageSize;
  const paginatedItems = items.slice(startIndex, endIndex);
  const totalPages = Math.ceil(items.length / pageSize);

  if (loading) {
    return (
      <div className="context-item-list">
        <h4>Context Items</h4>
        <p>Loading...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="context-item-list error">
        <h4>Context Items</h4>
        <p className="error-message">{error}</p>
      </div>
    );
  }

  return (
    <div className="context-item-list">
      <div className="list-header">
        <h4>Context Items</h4>

        {/* Tier Filter */}
        <div className="filter-controls">
          <label htmlFor="tier-filter">Filter by tier:</label>
          <select
            id="tier-filter"
            value={tierFilter}
            onChange={(e) => setTierFilter(e.target.value)}
          >
            <option value="">All Tiers</option>
            <option value="hot">HOT</option>
            <option value="warm">WARM</option>
            <option value="cold">COLD</option>
          </select>
        </div>
      </div>

      {items.length === 0 ? (
        <p className="no-items">No context items found</p>
      ) : (
        <>
          {/* Items Table */}
          <table className="items-table">
            <thead>
              <tr>
                <th>Type</th>
                <th>Content</th>
                <th>Score</th>
                <th>Tier</th>
                <th>Age</th>
              </tr>
            </thead>
            <tbody>
              {paginatedItems.map((item) => (
                <tr key={item.id} className={`tier-${item.current_tier.toLowerCase()}`}>
                  <td className="item-type">{item.item_type}</td>
                  <td className="item-content" title={item.content}>
                    {truncate(item.content)}
                  </td>
                  <td className="item-score">
                    {item.importance_score.toFixed(2)}
                  </td>
                  <td className="item-tier">
                    <span className={`tier-badge ${item.current_tier.toLowerCase()}`}>
                      {item.current_tier}
                    </span>
                  </td>
                  <td className="item-age">{getAge(item.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>

          {/* Pagination Controls */}
          {totalPages > 1 && (
            <div className="pagination">
              <button
                onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                disabled={currentPage === 1}
              >
                Previous
              </button>

              <span className="page-info">
                Page {currentPage} of {totalPages} ({items.length} total items)
              </span>

              <button
                onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                disabled={currentPage === totalPages}
              >
                Next
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

export default ContextItemList;
