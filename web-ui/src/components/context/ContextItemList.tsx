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
import type { ContextItem } from '../../types/context';
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
      <div className="p-6 bg-card rounded-lg border border-border">
        <h4 className="text-lg font-semibold text-foreground mb-2">Context Items</h4>
        <p className="text-muted-foreground">Loading...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6 bg-card rounded-lg border border-border">
        <h4 className="text-lg font-semibold text-foreground mb-2">Context Items</h4>
        <p className="text-red-600">{error}</p>
      </div>
    );
  }

  return (
    <div className="p-6 bg-card rounded-lg border border-border space-y-4">
      <div className="flex justify-between items-center">
        <h4 className="text-lg font-semibold text-foreground">Context Items</h4>

        {/* Tier Filter */}
        <div className="flex items-center gap-2">
          <label htmlFor="tier-filter" className="text-sm text-muted-foreground">Filter by tier:</label>
          <select
            id="tier-filter"
            value={tierFilter}
            onChange={(e) => setTierFilter(e.target.value)}
            className="px-3 py-1.5 bg-background border border-border rounded-md text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
          >
            <option value="">All Tiers</option>
            <option value="hot">HOT</option>
            <option value="warm">WARM</option>
            <option value="cold">COLD</option>
          </select>
        </div>
      </div>

      {items.length === 0 ? (
        <p className="text-muted-foreground text-center py-8">No context items found</p>
      ) : (
        <>
          {/* Items Table */}
          <div className="overflow-x-auto">
            <table className="w-full border-collapse">
              <thead>
                <tr className="border-b border-border">
                  <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase">Type</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase">Content</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase">Score</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase">Tier</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase">Age</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {paginatedItems.map((item) => (
                  <tr key={item.id} className="hover:bg-muted/50 transition-colors">
                    <td className="px-4 py-3 text-sm text-foreground">{item.item_type}</td>
                    <td className="px-4 py-3 text-sm text-muted-foreground max-w-md truncate" title={item.content}>
                      {truncate(item.content)}
                    </td>
                    <td className="px-4 py-3 text-sm text-foreground">
                      {item.importance_score.toFixed(2)}
                    </td>
                    <td className="px-4 py-3">
                      <span className="inline-flex px-2 py-1 text-xs font-medium bg-muted text-foreground rounded-md border border-border">
                        {item.current_tier}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-sm text-muted-foreground">{getAge(item.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination Controls */}
          {totalPages > 1 && (
            <div className="flex justify-between items-center pt-4 border-t border-border">
              <button
                onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                disabled={currentPage === 1}
                className="px-4 py-2 text-sm font-medium bg-background border border-border rounded-md text-foreground hover:bg-muted disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                Previous
              </button>

              <span className="text-sm text-muted-foreground">
                Page {currentPage} of {totalPages} ({items.length} total items)
              </span>

              <button
                onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                disabled={currentPage === totalPages}
                className="px-4 py-2 text-sm font-medium bg-background border border-border rounded-md text-foreground hover:bg-muted disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
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
