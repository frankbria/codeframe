'use client';

import Link from 'next/link';
import {
  FileEditIcon,
  FileAddIcon,
  Task01Icon,
  GitBranchIcon,
  PlayCircleIcon,
  CheckListIcon,
} from '@hugeicons/react';
import { Button } from '@/components/ui/button';
import type { QuickActionsProps } from '@/types';

type PipelineState = 'no_tasks' | 'tasks_ready' | 'executing' | 'done' | 'mixed';

function getPipelineState(counts: QuickActionsProps['taskCounts']): PipelineState {
  if (!counts) return 'no_tasks';
  const total = counts.BACKLOG + counts.READY + counts.IN_PROGRESS + counts.DONE + counts.BLOCKED + counts.FAILED + counts.MERGED;
  if (total === 0) return 'no_tasks';
  if (counts.IN_PROGRESS > 0) return 'executing';
  if (counts.READY > 0) return 'tasks_ready';
  if (counts.DONE > 0 && counts.READY === 0) return 'done';
  return 'mixed';
}

export function QuickActions({ taskCounts }: QuickActionsProps) {
  const state = getPipelineState(taskCounts);

  return (
    <section className="my-8">
      <h2 className="mb-4 text-lg font-semibold">Quick Actions</h2>
      <div className="flex flex-wrap gap-3">
        {state === 'no_tasks' && (
          <>
            <Button asChild>
              <Link href="/prd">
                <FileEditIcon className="mr-2 h-4 w-4" />
                Create PRD
              </Link>
            </Button>
            <Button variant="outline" asChild>
              <Link href="/prd">
                <FileAddIcon className="mr-2 h-4 w-4" />
                Import PRD
              </Link>
            </Button>
          </>
        )}

        {state === 'tasks_ready' && (
          <>
            <Button asChild>
              <Link href="/tasks">
                <PlayCircleIcon className="mr-2 h-4 w-4" />
                Execute Tasks
              </Link>
            </Button>
            <Button variant="outline" asChild>
              <Link href="/tasks">
                <Task01Icon className="mr-2 h-4 w-4" />
                Manage Tasks
              </Link>
            </Button>
          </>
        )}

        {state === 'executing' && (
          <>
            <Button asChild>
              <Link href="/tasks">
                <PlayCircleIcon className="mr-2 h-4 w-4" />
                View Running Tasks
              </Link>
            </Button>
            <Button variant="outline" asChild>
              <Link href="/tasks">
                <Task01Icon className="mr-2 h-4 w-4" />
                Manage Tasks
              </Link>
            </Button>
          </>
        )}

        {state === 'done' && (
          <>
            <Button asChild>
              <Link href="/proof">
                <CheckListIcon className="mr-2 h-4 w-4" />
                View Proof Gates
              </Link>
            </Button>
            <Button variant="outline" asChild>
              <Link href="/review">
                <GitBranchIcon className="mr-2 h-4 w-4" />
                Review Changes
              </Link>
            </Button>
          </>
        )}

        {state === 'mixed' && (
          <>
            <Button variant="outline" asChild>
              <Link href="/prd">
                <FileEditIcon className="mr-2 h-4 w-4" />
                View PRD
              </Link>
            </Button>
            <Button variant="outline" asChild>
              <Link href="/tasks">
                <Task01Icon className="mr-2 h-4 w-4" />
                Manage Tasks
              </Link>
            </Button>
            <Button variant="outline" asChild>
              <Link href="/review">
                <GitBranchIcon className="mr-2 h-4 w-4" />
                Review Changes
              </Link>
            </Button>
          </>
        )}
      </div>
    </section>
  );
}
