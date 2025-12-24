import { useState, useEffect } from 'react';
import { formatDistanceToNow } from 'date-fns';

interface SessionState {
  last_session: {
    summary: string;
    timestamp: string;
  };
  next_actions: string[];
  progress_pct: number;
  active_blockers: Array<{
    id: number;
    question: string;
    priority: string;
  }>;
}

interface SessionStatusProps {
  projectId: number;
}

export function SessionStatus({ projectId }: SessionStatusProps) {
  const [session, setSession] = useState<SessionState | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchSession = async () => {
      try {
        setIsLoading(true);
        const response = await fetch(`/api/projects/${projectId}/session`);

        if (!response.ok) {
          throw new Error('Failed to fetch session state');
        }

        const data = await response.json();
        setSession(data);
        setError(null);
      } catch (err) {
        console.error('Failed to fetch session:', err);
        setError(err instanceof Error ? err.message : 'Unknown error');
      } finally {
        setIsLoading(false);
      }
    };

    fetchSession();

    // Auto-refresh every 30 seconds
    const interval = setInterval(fetchSession, 30000);
    return () => clearInterval(interval);
  }, [projectId]);

  if (isLoading) {
    return (
      <div className="bg-primary/10 border border-primary rounded-lg p-4">
        <div className="flex items-center space-x-2">
          <span className="text-2xl">📋</span>
          <span className="text-primary font-medium">Loading session...</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
        <div className="flex items-center space-x-2">
          <span className="text-2xl">⚠️</span>
          <span className="text-yellow-700 font-medium">
            Could not load session state: {error}
          </span>
        </div>
      </div>
    );
  }

  if (!session) {
    return null;
  }

  // Check if this is a new session
  const isNewSession = session.last_session.summary === 'No previous session';

  return (
    <div className="bg-primary/10 border border-primary rounded-lg p-6">
      <div className="flex items-start space-x-3">
        <span className="text-3xl">📋</span>
        <div className="flex-1">
          <h3 className="text-lg font-semibold text-foreground mb-3">
            Session Context
          </h3>

          {isNewSession ? (
            <div className="text-foreground">
              <p className="font-medium">🚀 Starting new session...</p>
              <p className="text-sm text-muted-foreground mt-1">
                No previous session state found
              </p>
            </div>
          ) : (
            <>
              {/* Last Session */}
              <div className="mb-4">
                <h4 className="text-sm font-medium text-foreground mb-1">
                  Last session:
                </h4>
                <p className="text-foreground">{session.last_session.summary}</p>
                <p className="text-sm text-muted-foreground mt-1">
                  {formatDistanceToNow(new Date(session.last_session.timestamp), {
                    addSuffix: true,
                  })}
                </p>
              </div>

              {/* Next Actions */}
              {session.next_actions && session.next_actions.length > 0 && (
                <div className="mb-4">
                  <h4 className="text-sm font-medium text-foreground mb-1">
                    Next actions:
                  </h4>
                  <ul className="list-disc list-inside text-foreground space-y-1">
                    {session.next_actions.slice(0, 3).map((action, index) => (
                      <li key={index} className="text-sm">
                        {action}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Progress */}
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-medium text-foreground">
                  Progress:
                </span>
                <span className="text-primary font-semibold">
                  {Math.round(session.progress_pct)}%
                </span>
              </div>

              {/* Progress Bar */}
              <div className="w-full bg-muted rounded-full h-2 mb-4">
                <div
                  className="bg-primary h-2 rounded-full transition-all duration-300"
                  style={{ width: `${Math.min(session.progress_pct, 100)}%` }}
                />
              </div>

              {/* Blockers */}
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-foreground">
                  Blockers:
                </span>
                {session.active_blockers.length > 0 ? (
                  <span className="text-yellow-700 font-semibold">
                    {session.active_blockers.length} active
                  </span>
                ) : (
                  <span className="text-green-700 font-semibold">None</span>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
