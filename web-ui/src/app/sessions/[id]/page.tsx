'use client';

import { useParams } from 'next/navigation';
import Link from 'next/link';
import { ArrowLeft01Icon } from '@hugeicons/react';
import { Button } from '@/components/ui/button';

export default function SessionDetailPage() {
  const params = useParams<{ id: string }>();
  const sessionId = params.id;

  return (
    <main className="min-h-screen bg-background">
      <div className="mx-auto max-w-7xl px-4 py-8">
        <div className="mb-6 flex items-center gap-3">
          <Button asChild variant="ghost" size="sm">
            <Link href="/sessions">
              <ArrowLeft01Icon className="h-4 w-4" />
              Back to Sessions
            </Link>
          </Button>
        </div>
        <div className="rounded-lg border bg-muted/50 p-8 text-center">
          <p className="text-sm font-medium text-foreground">
            Session {sessionId?.slice(-8)}
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            Session detail view coming soon.
          </p>
        </div>
      </div>
    </main>
  );
}
