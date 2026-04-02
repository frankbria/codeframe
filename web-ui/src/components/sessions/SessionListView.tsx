'use client';

import { useState, useMemo, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import useSWR from 'swr';
import { Search01Icon, Loading03Icon } from '@hugeicons/react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { SessionCard } from './SessionCard';
import { NewSessionModal } from './NewSessionModal';
import { sessionsApi } from '@/lib/api';
import type { SessionListResponse, ApiError } from '@/types';

interface SessionListViewProps {
  workspacePath: string;
}

export function SessionListView({ workspacePath }: SessionListViewProps) {
  const router = useRouter();
  const [search, setSearch] = useState('');
  const [modalOpen, setModalOpen] = useState(false);

  const [endError, setEndError] = useState<string | null>(null);

  const { data, isLoading, error, mutate } = useSWR<SessionListResponse, ApiError>(
    `/api/v2/sessions?path=${encodeURIComponent(workspacePath)}`,
    () => sessionsApi.getAll(workspacePath),
    { refreshInterval: 10000 }
  );

  const sortedSessions = useMemo(() => {
    if (!data?.sessions) return [];
    return [...data.sessions].sort((a, b) => {
      if (a.state === 'active' && b.state !== 'active') return -1;
      if (a.state !== 'active' && b.state === 'active') return 1;
      return 0;
    });
  }, [data?.sessions]);

  const filteredSessions = useMemo(() => {
    if (!search) return sortedSessions;
    const q = search.toLowerCase();
    return sortedSessions.filter(
      (s) =>
        s.id.toLowerCase().includes(q) ||
        s.workspace_path.toLowerCase().includes(q)
    );
  }, [sortedSessions, search]);

  const handleEnd = useCallback(async (id: string) => {
    try {
      await sessionsApi.end(id);
    } catch {
      setEndError('Failed to end session. Please try again.');
    } finally {
      mutate();
    }
  }, [mutate]);

  const handleCreate = useCallback(async (createData: { workspace_path: string; model: string }) => {
    const session = await sessionsApi.create(createData);
    setModalOpen(false);
    mutate();
    router.push(`/sessions/${session.id}`);
  }, [mutate, router]);

  // Loading state
  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold tracking-tight">Sessions</h1>
        </div>
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div
              key={i}
              data-testid="session-skeleton"
              className="h-32 animate-pulse rounded-lg border bg-muted/50"
            />
          ))}
        </div>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold tracking-tight">Sessions</h1>
        </div>
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-6 text-center">
          <p className="mb-3 text-sm text-destructive">
            {error.detail || 'Failed to load sessions'}
          </p>
          <Button variant="outline" size="sm" onClick={() => mutate()}>
            Retry
          </Button>
        </div>
      </div>
    );
  }

  // Empty state
  if (!data?.sessions.length) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold tracking-tight">Sessions</h1>
          <Button size="sm" onClick={() => setModalOpen(true)}>
            + New Session
          </Button>
        </div>
        <div className="rounded-lg border bg-muted/50 p-8 text-center">
          <Loading03Icon className="mx-auto mb-3 h-10 w-10 text-muted-foreground" />
          <p className="text-sm font-medium text-foreground">No sessions yet</p>
          <p className="mt-1 text-xs text-muted-foreground">
            Start a new session to begin working with an AI agent.
          </p>
        </div>
        <NewSessionModal
          open={modalOpen}
          onOpenChange={setModalOpen}
          defaultWorkspacePath={workspacePath}
          onSubmit={handleCreate}
        />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold tracking-tight">Sessions</h1>
        <Button size="sm" onClick={() => setModalOpen(true)}>
          + New Session
        </Button>
      </div>

      {/* Search */}
      <div className="relative">
        <Search01Icon className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          placeholder="Search sessions..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="pl-9"
        />
      </div>

      {/* End error */}
      {endError && (
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 px-4 py-2 text-sm text-destructive">
          {endError}
          <button className="ml-2 underline" onClick={() => setEndError(null)}>Dismiss</button>
        </div>
      )}

      {/* Session list */}
      <div className="space-y-3">
        {filteredSessions.map((session) => (
          <SessionCard key={session.id} session={session} onEnd={handleEnd} />
        ))}
      </div>

      <NewSessionModal
        open={modalOpen}
        onOpenChange={setModalOpen}
        defaultWorkspacePath={workspacePath}
        onSubmit={handleCreate}
      />
    </div>
  );
}
