'use client';

import Link from 'next/link';
import {
  FileEditIcon,
  Task01Icon,
  GitBranchIcon,
} from '@hugeicons/react';
import { Button } from '@/components/ui/button';

export function QuickActions() {
  return (
    <section className="my-8">
      <h2 className="mb-4 text-lg font-semibold">Quick Actions</h2>
      <div className="flex flex-wrap gap-3">
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
      </div>
    </section>
  );
}
