'use client';

import Link from 'next/link';
import { formatDistanceToNow } from 'date-fns';
import { Cancel01Icon } from '@hugeicons/react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import type { Session } from '@/types';

interface SessionCardProps {
  session: Session;
  onEnd: (id: string) => void;
}

export function SessionCard({ session, onEnd }: SessionCardProps) {
  const shortId = session.id.slice(-8);
  const workspaceName = session.workspace_path.split('/').pop() || session.workspace_path;
  const isActive = session.state === 'active';
  const relativeTime = formatDistanceToNow(new Date(session.created_at), { addSuffix: true });

  const handleEnd = () => {
    if (window.confirm('End this session? This will stop the active agent.')) {
      onEnd(session.id);
    }
  };

  return (
    <Card className="transition-colors hover:border-primary/50">
      <CardContent className="p-3">
        {/* Top row: state dot + short ID */}
        <div className="mb-2 flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <span
              data-testid="session-state-dot"
              className={`inline-block h-2.5 w-2.5 rounded-full ${
                isActive ? 'bg-green-500' : 'bg-gray-400'
              }`}
            />
            <span className="font-mono text-sm font-medium">{shortId}</span>
          </div>
          <span className="text-xs text-muted-foreground">{relativeTime}</span>
        </div>

        {/* Details */}
        <p className="truncate text-xs text-muted-foreground">{workspaceName}</p>
        <p className="mt-0.5 text-xs text-muted-foreground">{session.model}</p>
        <p className="mt-0.5 text-xs text-muted-foreground">${session.cost_usd}</p>

        {/* Action buttons */}
        <div className="mt-2 flex gap-1">
          <Link href={`/sessions/${session.id}`}>
            <Button size="sm" variant="ghost" className="h-7 gap-1 px-2 text-xs">
              {isActive ? 'Resume' : 'View'} &rarr;
            </Button>
          </Link>
          {isActive && (
            <Button
              size="sm"
              variant="ghost"
              className="h-7 gap-1 px-2 text-xs text-destructive"
              onClick={handleEnd}
            >
              <Cancel01Icon className="h-3.5 w-3.5" />
              End
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
