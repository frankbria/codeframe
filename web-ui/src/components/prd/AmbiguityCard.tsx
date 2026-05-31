'use client';

import { Badge } from '@/components/ui/badge';
import { Textarea } from '@/components/ui/textarea';
import type { StressTestAmbiguity } from '@/types';

interface AmbiguityCardProps {
  ambiguity: StressTestAmbiguity;
  answer: string;
  onChange: (id: string, answer: string) => void;
}

/**
 * Renders a single stress-test ambiguity as an answerable card (issue #562):
 * the label, a severity badge, the unanswered questions, an answer textarea,
 * and the agent's recommendation as helper text.
 */
export function AmbiguityCard({ ambiguity, answer, onChange }: AmbiguityCardProps) {
  const isBlocking = ambiguity.severity === 'blocking';

  return (
    <div className="rounded-md border bg-card p-4">
      <div className="mb-2 flex items-start justify-between gap-2">
        <h4 className="text-sm font-semibold leading-tight">{ambiguity.label}</h4>
        <Badge variant={isBlocking ? 'destructive' : 'secondary'}>
          {isBlocking ? 'Blocking' : 'Warning'}
        </Badge>
      </div>

      {ambiguity.source_node_title && (
        <p className="mb-2 text-xs text-muted-foreground">
          From: {ambiguity.source_node_title}
        </p>
      )}

      {ambiguity.questions.length > 0 && (
        <ul className="mb-3 list-disc space-y-1 pl-5 text-sm text-foreground">
          {ambiguity.questions.map((q, i) => (
            <li key={i}>{q}</li>
          ))}
        </ul>
      )}

      <Textarea
        aria-label={`Answer for ${ambiguity.label}`}
        placeholder="Your answer..."
        value={answer}
        onChange={(e) => onChange(ambiguity.id, e.target.value)}
        rows={3}
      />

      {ambiguity.recommendation && (
        <p className="mt-2 text-xs text-muted-foreground">
          <span className="font-medium">Recommendation:</span>{' '}
          {ambiguity.recommendation}
        </p>
      )}
    </div>
  );
}
