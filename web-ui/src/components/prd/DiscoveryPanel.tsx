'use client';

import { useState, useCallback, useEffect } from 'react';
import { Cancel01Icon, Loading03Icon } from '@hugeicons/react';
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

const now = () => new Date().toISOString();

/** Extract display text from the API's question object. */
function questionText(q: Record<string, unknown>): string {
  if (typeof q.text === 'string') return q.text;
  if (typeof q.question === 'string') return q.question;
  // Fallback: stringify the whole object
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

  // ─── Start session ───────────────────────────────────────────────
  const startSession = useCallback(async () => {
    setIsThinking(true);
    setError(null);
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
    } finally {
      setIsThinking(false);
    }
  }, [workspacePath]);

  // Auto-start when panel mounts if no session yet
  useEffect(() => {
    if (!sessionId) startSession();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ─── Submit answer ───────────────────────────────────────────────
  const handleSubmitAnswer = useCallback(
    async (answer: string) => {
      if (!sessionId) return;
      // Append user message immediately
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

        // Build AI reply from feedback + follow-up or next question
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

  // ─── Generate PRD ────────────────────────────────────────────────
  const handleGeneratePrd = useCallback(async () => {
    if (!sessionId) return;
    setIsGenerating(true);
    setError(null);

    try {
      await discoveryApi.generatePrd(sessionId, workspacePath);
      // Fetch the full PRD to hand back to the page
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
        <button
          onClick={onClose}
          className="rounded-md p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
          aria-label="Close discovery panel"
        >
          <Cancel01Icon className="h-4 w-4" />
        </button>
      </div>

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
