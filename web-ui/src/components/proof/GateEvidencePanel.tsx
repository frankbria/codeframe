'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import type { ProofEvidenceWithContent } from '@/types';

const MAX_LINES = 200;

function truncateLines(text: string, max: number): { lines: string[]; truncated: boolean } {
  const lines = text.split('\n');
  if (lines.length <= max) return { lines, truncated: false };
  return { lines: lines.slice(0, max), truncated: true };
}

interface GateEvidencePanelProps {
  evidence: ProofEvidenceWithContent[];
}

interface GateEvidenceRowProps {
  ev: ProofEvidenceWithContent;
}

function GateEvidenceRow({ ev }: GateEvidenceRowProps) {
  const [expanded, setExpanded] = useState(false);
  const [showFull, setShowFull] = useState(false);

  const hasText = ev.artifact_text != null && ev.artifact_text.trim().length > 0;
  const { lines, truncated } = hasText
    ? truncateLines(ev.artifact_text!, MAX_LINES)
    : { lines: [], truncated: false };
  const displayLines = showFull ? ev.artifact_text!.split('\n') : lines;

  return (
    <div className="border-b last:border-0">
      <button
        type="button"
        aria-expanded={expanded}
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center gap-3 px-4 py-2 text-left hover:bg-muted/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-inset"
      >
        <span className="font-mono text-xs text-muted-foreground w-16 shrink-0 capitalize">{ev.gate}</span>
        <span
          className={`rounded-full px-2 py-0.5 text-xs font-medium ${
            ev.satisfied
              ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
              : 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'
          }`}
        >
          {ev.satisfied ? 'pass' : 'fail'}
        </span>
        <span className="ml-auto text-xs text-muted-foreground">{expanded ? '▲' : '▼'}</span>
      </button>

      {expanded && (
        <div className="px-4 pb-3">
          {!hasText ? (
            <p className="text-xs text-muted-foreground italic">No output captured</p>
          ) : (
            <>
              <pre className="max-h-64 overflow-auto rounded-md bg-muted p-3 text-xs leading-relaxed whitespace-pre-wrap break-words">
                {displayLines.join('\n')}
              </pre>
              {truncated && !showFull && (
                <Button
                  variant="ghost"
                  size="sm"
                  className="mt-1 text-xs"
                  onClick={(e) => { e.stopPropagation(); setShowFull(true); }}
                >
                  Show full output
                </Button>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

export function GateEvidencePanel({ evidence }: GateEvidencePanelProps) {
  if (evidence.length === 0) return null;

  return (
    <div className="rounded-lg border bg-background" aria-label="Gate evidence">
      {evidence.map((ev, i) => (
        <GateEvidenceRow key={`${ev.run_id}:${ev.gate}:${i}`} ev={ev} />
      ))}
    </div>
  );
}
