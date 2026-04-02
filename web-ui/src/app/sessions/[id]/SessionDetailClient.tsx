'use client';

import { useEffect, useRef, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import useSWR from 'swr';
import { ArrowLeft01Icon } from '@hugeicons/react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { AgentChatPanel } from '@/components/sessions/AgentChatPanel';
import { AgentTerminal } from '@/components/sessions/AgentTerminal';
import { SplitPane } from '@/components/sessions/SplitPane';
import { sessionsApi } from '@/lib/api';
import type { ChatMessage, Session } from '@/types';

// ── Helpers ──────────────────────────────────────────────────────────────

function shortId(id: string): string {
  return id.slice(-8);
}

function stateBadgeVariant(state: Session['state']): 'default' | 'secondary' | 'outline' {
  if (state === 'active') return 'default';
  if (state === 'ended') return 'secondary';
  return 'outline';
}

// ── Loading skeleton ──────────────────────────────────────────────────────

function SessionDetailSkeleton() {
  return (
    <div data-testid="session-detail-skeleton" className="flex h-screen flex-col">
      {/* Header skeleton */}
      <div className="flex items-center gap-4 border-b px-4 py-3">
        <div className="h-8 w-24 animate-pulse rounded bg-muted" />
        <div className="h-5 w-32 animate-pulse rounded bg-muted" />
        <div className="ml-auto h-8 w-28 animate-pulse rounded bg-muted" />
      </div>
      {/* Body skeleton */}
      <div className="flex flex-1 gap-0">
        <div className="h-full flex-1 animate-pulse bg-muted/50" />
        <div className="w-px bg-border" />
        <div className="h-full flex-1 animate-pulse bg-muted/50" />
      </div>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────

interface SessionDetailClientProps {
  sessionId: string;
}

export function SessionDetailClient({ sessionId }: SessionDetailClientProps) {
  const router = useRouter();

  const { data: session, isLoading, error } = useSWR<Session>(
    sessionId ? `/api/v2/sessions/${sessionId}` : null,
    () => sessionsApi.getOne(sessionId),
    { refreshInterval: (data) => (data?.state === 'active' ? 5000 : 0) }
  );

  const [endingSession, setEndingSession] = useState(false);
  const [endError, setEndError] = useState<string | null>(null);
  const [historyMessages, setHistoryMessages] = useState<ChatMessage[] | undefined>(undefined);
  const messagesFetchedRef = useRef(false);

  // Load message history for ended sessions via REST (once per mount)
  useEffect(() => {
    if (session?.state === 'ended' && !messagesFetchedRef.current) {
      messagesFetchedRef.current = true;
      sessionsApi
        .getMessages(session.id)
        .then(setHistoryMessages)
        .catch(() => setHistoryMessages([]));
    }
  }, [session]);

  const handleEndSession = useCallback(async () => {
    if (!session || session.state !== 'active') return;
    setEndingSession(true);
    setEndError(null);
    try {
      await sessionsApi.end(session.id);
      router.push('/sessions');
    } catch {
      setEndError('Failed to end session. Please try again.');
    } finally {
      setEndingSession(false);
    }
  }, [session, router]);

  // ── Loading ──────────────────────────────────────────────────────────

  if (isLoading) {
    return <SessionDetailSkeleton />;
  }

  // ── Error ────────────────────────────────────────────────────────────

  if (error || !session) {
    const isNotFound = error?.status === 404 || error?.detail === 'Session not found';
    return (
      <main className="min-h-screen bg-background">
        <div className="mx-auto max-w-7xl px-4 py-8">
          <div className="mb-6">
            <Button asChild variant="ghost" size="sm">
              <Link href="/sessions">
                <ArrowLeft01Icon className="h-4 w-4 mr-1" />
                Back to Sessions
              </Link>
            </Button>
          </div>
          <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-8 text-center">
            {isNotFound ? (
              <>
                <p className="text-sm font-medium text-foreground">Session not found</p>
                <p className="mt-2 text-xs text-muted-foreground">
                  This session may have been deleted or the ID is incorrect.
                </p>
                <Button asChild variant="outline" size="sm" className="mt-4">
                  <Link href="/sessions">Back to Sessions</Link>
                </Button>
              </>
            ) : (
              <>
                <p className="text-sm font-medium text-destructive">Failed to load session</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  {error?.detail ?? 'An unexpected error occurred.'}
                </p>
              </>
            )}
          </div>
        </div>
      </main>
    );
  }

  // ── Loaded ───────────────────────────────────────────────────────────

  const isActive = session.state === 'active';
  const sid = shortId(session.id);

  return (
    <main className="flex h-screen flex-col bg-background overflow-hidden">
      {/* Header */}
      <header className="flex shrink-0 items-center gap-3 border-b bg-background px-4 py-2">
        <Button asChild variant="ghost" size="sm" className="shrink-0">
          <Link href="/sessions">
            <ArrowLeft01Icon className="h-4 w-4 mr-1" />
            Sessions
          </Link>
        </Button>

        <span className="font-mono text-sm font-medium text-foreground">
          Session #{sid}
        </span>

        <Badge variant={stateBadgeVariant(session.state)} className="capitalize">
          {session.state}
        </Badge>

        <span className="font-mono text-xs text-muted-foreground">
          ${(session.cost_usd ?? 0).toFixed(4)}
        </span>

        <div className="ml-auto flex items-center gap-2">
          {endError && (
            <span className="text-xs text-destructive" role="alert">{endError}</span>
          )}
          <Button
            variant="outline"
            size="sm"
            disabled={!isActive || endingSession}
            onClick={handleEndSession}
          >
            {endingSession ? 'Ending…' : 'End Session'}
          </Button>
        </div>
      </header>

      {/* Ended session banner */}
      {!isActive && (
        <div className="shrink-0 border-b bg-muted/50 px-4 py-2 text-center text-xs text-muted-foreground">
          This session has ended.{' '}
          <Link href="/sessions" className="underline hover:text-foreground">
            View history
          </Link>
        </div>
      )}

      {/* Body — SplitPane for active, chat-only for ended */}
      <div className="flex-1 overflow-hidden">
        {isActive ? (
          <SplitPane
            left={<AgentChatPanel sessionId={session.id} className="h-full" />}
            right={<AgentTerminal sessionId={session.id} className="h-full" />}
            defaultSplit={45}
            storageKey={`session-split-${session.id}`}
            className="h-full"
          />
        ) : (
          <AgentChatPanel
            sessionId={session.id}
            readOnly
            initialMessages={historyMessages}
            className="h-full"
          />
        )}
      </div>
    </main>
  );
}
