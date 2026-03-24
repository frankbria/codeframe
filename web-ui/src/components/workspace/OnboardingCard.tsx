'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { Cancel01Icon } from '@hugeicons/react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { getOnboardingDismissed, setOnboardingDismissed } from '@/lib/workspace-storage';

const PIPELINE_STEPS = [
  {
    phase: 'Think',
    description: 'Define requirements in the PRD',
  },
  {
    phase: 'Build',
    description: 'Generate and execute tasks with the AI agent',
  },
  {
    phase: 'Prove',
    description: 'Verify quality through proof gates',
  },
  {
    phase: 'Ship',
    description: 'Create a PR and merge your work',
  },
];

interface OnboardingCardProps {
  workspacePath: string;
}

export function OnboardingCard({ workspacePath }: OnboardingCardProps) {
  const [isDismissed, setIsDismissed] = useState(() =>
    getOnboardingDismissed(workspacePath)
  );

  // Re-check when workspacePath changes (e.g. user switches workspace)
  useEffect(() => {
    setIsDismissed(getOnboardingDismissed(workspacePath));
  }, [workspacePath]);

  if (isDismissed) return null;

  const handleDismiss = () => {
    setOnboardingDismissed(workspacePath);
    setIsDismissed(true);
  };

  return (
    <Card className="mb-6 border-primary/20 bg-primary/5">
      <CardHeader className="flex flex-row items-start justify-between pb-2">
        <CardTitle className="text-base font-semibold">
          Welcome to CodeFRAME — here's how to get started
        </CardTitle>
        <button
          onClick={handleDismiss}
          aria-label="Dismiss onboarding"
          className="ml-4 rounded p-1 text-muted-foreground transition-colors hover:bg-primary/10 hover:text-foreground"
        >
          <Cancel01Icon className="h-4 w-4" />
        </button>
      </CardHeader>
      <CardContent>
        <ol className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4">
          {PIPELINE_STEPS.map((step, index) => (
            <li key={step.phase} className="flex flex-col gap-1">
              <div className="flex items-center gap-2">
                <span className="flex h-6 w-6 items-center justify-center rounded-full bg-primary/15 text-xs font-semibold text-primary">
                  {index + 1}
                </span>
                <span className="font-semibold">{step.phase}</span>
              </div>
              <p className="pl-8 text-xs text-muted-foreground">{step.description}</p>
            </li>
          ))}
        </ol>
        <Button asChild size="sm">
          <Link href="/prd">Get Started →</Link>
        </Button>
      </CardContent>
    </Card>
  );
}
