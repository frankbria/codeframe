'use client';

import { Progress } from '@/components/ui/progress';
import { agentStateLabels } from '@/lib/eventStyles';
import type { UIAgentState } from '@/types';

interface ProgressIndicatorProps {
  currentStep: number;
  totalSteps: number;
  currentMessage: string;
  agentState: UIAgentState;
}

export function ProgressIndicator({
  currentStep,
  totalSteps,
  currentMessage,
  agentState,
}: ProgressIndicatorProps) {
  const percentage = totalSteps > 0 ? Math.round((currentStep / totalSteps) * 100) : 0;

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between text-xs">
        <span className="text-muted-foreground">
          {totalSteps > 0 ? (
            <>
              Step {currentStep} of {totalSteps}
              {currentMessage && (
                <span className="ml-1.5 text-foreground">{currentMessage}</span>
              )}
            </>
          ) : (
            <span>{agentStateLabels[agentState]}...</span>
          )}
        </span>
        {totalSteps > 0 && (
          <span className="tabular-nums text-muted-foreground">{percentage}%</span>
        )}
      </div>
      <Progress value={percentage} className="h-1.5" />
    </div>
  );
}
