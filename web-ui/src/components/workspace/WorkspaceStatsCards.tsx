'use client';

import Link from 'next/link';
import {
  CodeIcon,
  Task01Icon,
  PlayIcon,
} from '@hugeicons/react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import type { TaskStatusCounts } from '@/types';

interface WorkspaceStatsCardsProps {
  techStack: string | null;
  taskCounts: TaskStatusCounts;
  activeRunCount: number;
}

export function WorkspaceStatsCards({
  techStack,
  taskCounts,
  activeRunCount,
}: WorkspaceStatsCardsProps) {
  const totalTasks = Object.values(taskCounts).reduce((sum, count) => sum + count, 0);

  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
      {/* Tech Stack Card */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Tech Stack</CardTitle>
          <CodeIcon className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          {techStack ? (
            <p className="text-lg font-semibold">{techStack}</p>
          ) : (
            <p className="text-sm text-muted-foreground">Not detected</p>
          )}
        </CardContent>
      </Card>

      {/* Task Stats Card */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Tasks</CardTitle>
          <Task01Icon className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-2">
            {taskCounts.READY > 0 && (
              <Badge
                data-testid="badge-ready"
                className="bg-blue-100 text-blue-900"
              >
                {taskCounts.READY} ready
              </Badge>
            )}
            {taskCounts.IN_PROGRESS > 0 && (
              <Badge
                data-testid="badge-in-progress"
                className="bg-amber-100 text-amber-900"
              >
                {taskCounts.IN_PROGRESS} in progress
              </Badge>
            )}
            {taskCounts.DONE > 0 && (
              <Badge
                data-testid="badge-done"
                className="bg-green-100 text-green-900"
              >
                {taskCounts.DONE} done
              </Badge>
            )}
            {taskCounts.BLOCKED > 0 && (
              <Badge
                data-testid="badge-blocked"
                className="bg-red-100 text-red-900"
              >
                {taskCounts.BLOCKED} blocked
              </Badge>
            )}
            {taskCounts.FAILED > 0 && (
              <Badge
                data-testid="badge-failed"
                className="bg-red-200 text-red-900"
              >
                {taskCounts.FAILED} failed
              </Badge>
            )}
          </div>
          <p className="mt-2 text-sm text-muted-foreground">{totalTasks} total</p>
        </CardContent>
      </Card>

      {/* Active Runs Card */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Active Runs</CardTitle>
          <PlayIcon className="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <p
            data-testid="active-run-count"
            className={cn(
              'text-2xl font-bold',
              activeRunCount === 0 && 'text-muted-foreground'
            )}
          >
            {activeRunCount}
          </p>
          {activeRunCount > 0 && (
            <Link
              href="/execution"
              className="mt-2 inline-block text-sm text-primary hover:underline"
            >
              View Execution →
            </Link>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
