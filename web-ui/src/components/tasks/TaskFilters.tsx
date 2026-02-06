'use client';

import { useRef, useEffect, useState } from 'react';
import { Search01Icon } from '@hugeicons/react';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import type { TaskStatus } from '@/types';

const FILTERABLE_STATUSES: { value: TaskStatus; label: string; variant: string }[] = [
  { value: 'BACKLOG', label: 'Backlog', variant: 'backlog' },
  { value: 'READY', label: 'Ready', variant: 'ready' },
  { value: 'IN_PROGRESS', label: 'In Progress', variant: 'in-progress' },
  { value: 'BLOCKED', label: 'Blocked', variant: 'blocked' },
  { value: 'FAILED', label: 'Failed', variant: 'failed' },
  { value: 'DONE', label: 'Done', variant: 'done' },
];

interface TaskFiltersProps {
  searchQuery: string;
  onSearchChange: (query: string) => void;
  statusFilter: TaskStatus | null;
  onStatusFilter: (status: TaskStatus | null) => void;
}

export function TaskFilters({
  searchQuery,
  onSearchChange,
  statusFilter,
  onStatusFilter,
}: TaskFiltersProps) {
  const [localQuery, setLocalQuery] = useState(searchQuery);
  const timerRef = useRef<ReturnType<typeof setTimeout>>(undefined);

  // Debounce search input by 300ms
  useEffect(() => {
    timerRef.current = setTimeout(() => {
      onSearchChange(localQuery);
    }, 300);
    return () => clearTimeout(timerRef.current);
  }, [localQuery, onSearchChange]);

  // Sync if parent resets the query
  useEffect(() => {
    setLocalQuery(searchQuery);
  }, [searchQuery]);

  return (
    <div className="flex flex-wrap items-center gap-3">
      {/* Search input */}
      <div className="relative w-56">
        <Search01Icon className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={localQuery}
          onChange={(e) => setLocalQuery(e.target.value)}
          placeholder="Search tasks..."
          className="pl-8"
        />
      </div>

      {/* Status filter pills */}
      <div className="flex flex-wrap items-center gap-1.5">
        {FILTERABLE_STATUSES.map(({ value, label, variant }) => {
          const isActive = statusFilter === value;
          return (
            <button
              key={value}
              onClick={() => onStatusFilter(isActive ? null : value)}
              className="focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-ring rounded-md"
            >
              <Badge
                variant={variant as never}
                className={cn(
                  'cursor-pointer transition-opacity',
                  !isActive && statusFilter !== null && 'opacity-40'
                )}
              >
                {label}
              </Badge>
            </button>
          );
        })}

        {statusFilter && (
          <button
            onClick={() => onStatusFilter(null)}
            className="text-xs text-muted-foreground hover:text-foreground"
          >
            Clear
          </button>
        )}
      </div>
    </div>
  );
}
