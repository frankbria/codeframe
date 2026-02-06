'use client';

import { useState, useCallback, useEffect } from 'react';
import { Cancel01Icon, Loading03Icon, ArrowReloadHorizontalIcon } from '@hugeicons/react';
import { Button } from '@/components/ui/button';
import { DiscoveryTranscript } from './DiscoveryTranscript';
import { DiscoveryInput } from './DiscoveryInput';
import { discoveryApi, prdApi } from '@/lib/api';
import type {
  DiscoveryMessage,
  DiscoveryState,
  PrdResponse,
  ApiError,
} from '@/types';

interface DiscoveryPanelProps {
  workspacePath: string;
  onClose: () => void;
  onPrdGenerated: (prd: PrdResponse) => void;
}

/** Info about a pre-existing session returned by the status check. */
interface PendingSession {
  sessionId: string;
  answeredCount: number;
  currentQuestion: Record<string, unknown> | null;
}

const now = () => new Date().toISOString();

/** Extract display text from the API's question object. */
function questionText(q: Record<string, unknown>): string {
  if (typeof q.text === 'string') return q.text;
  if (typeof q.question === 'string') return q.question;
  return JSON.stringify(q);
}

export function DiscoveryPanel({
  workspacePath,
  onClose,
  onPrdGenerated,
}: DiscoveryPanelProps) {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [state, setState] = useState<DiscoveryState>('idle');
  const [messages, setMessages] = useState<DiscoveryMessage[]>([]);
  const [isThinking, setIsThinking] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pendingSession, setPendingSession] = useState<PendingSession | null>(null);

  // ─── Initialise: check for existing session before starting ────
  const initSession = useCallback(async () => {
    setIsThinking(true);
    setError(null);
    try {
      const status = await discoveryApi.getStatus(workspacePath);

      if (status.session_id && status.state === 'discovering') {
        // Active session found — surface the resume prompt
        const answeredCount =
          typeof status.progress?.answered_count === 'number'
            ? status.progress.answered_count
            : 0;
        setPendingSession({
          sessionId: status.session_id,
          answeredCount,
          currentQuestion: status.current_question,
        });
      } else if (status.session_id && status.state === 'completed') {
        // Completed but PRD never generated — go straight to generate
        setSessionId(status.session_id);
        setState('completed');
      } else {
        // No active session — start fresh
        await startNewSession();
      }
    } catch {
      // Status endpoint failed — fall back to starting a new session
      await startNewSession();
    } finally {
      setIsThinking(false);
    }
  }, [workspacePath]);

  // ─── Start a brand-new session ─────────────────────────────────
  const startNewSession = useCallback(async () => {
    setError(null);
    setPendingSession(null);
    try {
      const resp = await discoveryApi.start(workspacePath);
      setSessionId(resp.session_id);
      setState('discovering');
      setMessages([
        {
          role: 'assistant',
          content: questionText(resp.question),
          timestamp: now(),
        },
      ]);
    } catch (err) {
      const apiErr = err as ApiError;
      setError(apiErr.detail || 'Failed to start discovery session');
    }
  }, [workspacePath]);

  // ─── Resume an existing session ────────────────────────────────
  const resumeSession = useCallback(() => {
    if (!pendingSession) return;
    setSessionId(pendingSession.sessionId);
    setState('discovering');
    setPendingSession(null);

    const introMessages: DiscoveryMessage[] = [
      {
        role: 'assistant',
        content: `Resuming your previous session (${pendingSession.answeredCount} question${pendingSession.answeredCount === 1 ? '' : 's'} answered so far).`,
        timestamp: now(),
      },
    ];

    if (pendingSession.currentQuestion) {
      introMessages.push({
        role: 'assistant',
        content: questionText(pendingSession.currentQuestion),
        timestamp: now(),
      });
    }

    setMessages(introMessages);
  }, [pendingSession]);

  // ─── Start over: reset then start fresh ────────────────────────
  const startOver = useCallback(async () => {
    setIsThinking(true);
    setError(null);
    setPendingSession(null);
    try {
      await discoveryApi.reset(workspacePath);
      await startNewSession();
    } catch (err) {
      const apiErr = err as ApiError;
      setError(apiErr.detail || 'Failed to reset session');
    } finally {
      setIsThinking(false);
    }
  }, [workspacePath, startNewSession]);

  // Auto-init when panel mounts
  useEffect(() => {
    if (!sessionId && !pendingSession) initSession();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ─── Submit answer ─────────────────────────────────────────────
  const handleSubmitAnswer = useCallback(
    async (answer: string) => {
      if (!sessionId) return;
      setMessages((prev) => [
        ...prev,
        { role: 'user', content: answer, timestamp: now() },
      ]);
      setIsThinking(true);
      setError(null);

      try {
        const resp = await discoveryApi.submitAnswer(
          sessionId,
          answer,
          workspacePath
        );

        let aiReply = resp.feedback;
        if (!resp.accepted && resp.follow_up) {
          aiReply += '\n\n' + resp.follow_up;
        } else if (resp.next_question) {
          aiReply += '\n\n' + questionText(resp.next_question);
        }

        setMessages((prev) => [
          ...prev,
          { role: 'assistant', content: aiReply, timestamp: now() },
        ]);

        if (resp.is_complete) {
          setState('completed');
        }
      } catch (err) {
        const apiErr = err as ApiError;
        setError(apiErr.detail || 'Failed to submit answer');
      } finally {
        setIsThinking(false);
      }
    },
    [sessionId, workspacePath]
  );

  // ─── Generate PRD ──────────────────────────────────────────────
  const handleGeneratePrd = useCallback(async () => {
    if (!sessionId) return;
    setIsGenerating(true);
    setError(null);

    try {
      await discoveryApi.generatePrd(sessionId, workspacePath);
      const fullPrd = await prdApi.getLatest(workspacePath);
      onPrdGenerated(fullPrd);
    } catch (err) {
      const apiErr = err as ApiError;
      setError(apiErr.detail || 'Failed to generate PRD');
    } finally {
      setIsGenerating(false);
    }
  }, [sessionId, workspacePath, onPrdGenerated]);

  return (
    <div className="flex h-full flex-col rounded-lg border bg-card">
      {/* Panel header */}
      <div className="flex items-center justify-between border-b px-4 py-3">
        <h3 className="text-sm font-semibold">Discovery Session</h3>
        <div className="flex items-center gap-1">
          {/* Start Over — visible once a session is active */}
          {(state === 'discovering' || state === 'completed') && (
            <button
              onClick={startOver}
              className="rounded-md p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
              aria-label="Start over"
              title="Start over"
            >
              <ArrowReloadHorizontalIcon className="h-4 w-4" />
            </button>
          )}
          <button
            onClick={onClose}
            className="rounded-md p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
            aria-label="Close discovery panel"
          >
            <Cancel01Icon className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Resume prompt when a previous session is detected */}
      {pendingSession && (
        <div className="border-b px-4 py-4">
          <p className="mb-3 text-sm text-muted-foreground">
            You have an active discovery session
            {pendingSession.answeredCount > 0
              ? ` with ${pendingSession.answeredCount} question${pendingSession.answeredCount === 1 ? '' : 's'} answered`
              : ''}
            .
          </p>
          <div className="flex gap-2">
            <Button size="sm" onClick={resumeSession}>
              Resume
            </Button>
            <Button size="sm" variant="outline" onClick={startOver}>
              Start Fresh
            </Button>
          </div>
        </div>
      )}

      {/* Transcript */}
      <DiscoveryTranscript messages={messages} isThinking={isThinking} />

      {/* Error banner */}
      {error && (
        <div className="mx-4 mb-2 rounded-md bg-destructive/10 px-3 py-2 text-xs text-destructive">
          {error}
        </div>
      )}

      {/* Generate PRD button when discovery is complete */}
      {state === 'completed' && (
        <div className="border-t px-4 py-3">
          <Button
            className="w-full"
            onClick={handleGeneratePrd}
            disabled={isGenerating}
          >
            {isGenerating ? (
              <>
                <Loading03Icon className="mr-1.5 h-4 w-4 animate-spin" />
                Generating PRD...
              </>
            ) : (
              'Generate PRD'
            )}
          </Button>
        </div>
      )}

      {/* Input (only when actively discovering) */}
      {state === 'discovering' && (
        <DiscoveryInput
          onSubmit={handleSubmitAnswer}
          disabled={isThinking}
        />
      )}
    </div>
  );
}
