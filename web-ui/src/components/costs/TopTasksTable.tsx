'use client';

import Link from 'next/link';
import type { TaskCostEntry } from '@/types';

interface TopTasksTableProps {
  tasks: TaskCostEntry[];
  isLoading?: boolean;
}

function formatNumber(n: number): string {
  return n.toLocaleString('en-US');
}

function formatCost(value: number): string {
  return value.toLocaleString('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 4,
    maximumFractionDigits: 6,
  });
}

export function TopTasksTable({ tasks, isLoading }: TopTasksTableProps) {
  if (isLoading) {
    return (
      <div data-testid="top-tasks-loading" className="h-40 animate-pulse rounded-xl bg-muted" />
    );
  }

  if (tasks.length === 0) {
    return (
      <div
        data-testid="top-tasks-empty"
        className="rounded-lg border border-dashed bg-muted/20 p-6 text-center text-sm text-muted-foreground"
      >
        No per-task cost data yet. Run a task to start tracking spend.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-lg border">
      <table
        data-testid="top-tasks-table"
        className="w-full text-sm"
      >
        <thead className="bg-muted/40 text-xs uppercase tracking-wide text-muted-foreground">
          <tr>
            <th scope="col" className="px-3 py-2 text-left font-medium">Task</th>
            <th scope="col" className="px-3 py-2 text-left font-medium">Agent</th>
            <th scope="col" className="px-3 py-2 text-right font-medium">Input</th>
            <th scope="col" className="px-3 py-2 text-right font-medium">Output</th>
            <th scope="col" className="px-3 py-2 text-right font-medium">Cost</th>
          </tr>
        </thead>
        <tbody>
          {tasks.map((task) => (
            <tr
              key={task.task_id}
              className="border-t hover:bg-muted/20"
            >
              <td className="max-w-[280px] truncate px-3 py-2">
                <Link
                  href={`/tasks?selected=${encodeURIComponent(task.task_id)}`}
                  className="text-foreground hover:underline"
                  title={task.task_title}
                >
                  {task.task_title}
                </Link>
              </td>
              <td className="px-3 py-2 font-mono text-xs text-muted-foreground">
                {task.agent_id}
              </td>
              <td className="px-3 py-2 text-right tabular-nums">
                {formatNumber(task.input_tokens)}
              </td>
              <td className="px-3 py-2 text-right tabular-nums">
                {formatNumber(task.output_tokens)}
              </td>
              <td className="px-3 py-2 text-right font-medium tabular-nums">
                {formatCost(task.total_cost_usd)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
