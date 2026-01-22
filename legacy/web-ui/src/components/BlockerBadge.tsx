/**
 * BlockerBadge Component (049-human-in-loop, T016)
 * Displays a color-coded badge showing blocker type (SYNC/ASYNC)
 */

'use client';

import type { BlockerType } from '../types/blocker';
import { Alert02Icon, Idea01Icon } from '@hugeicons/react';

interface BlockerBadgeProps {
  type: BlockerType;
  className?: string;
}

interface BadgeConfig {
  label: string;
  bgColor: string;
  textColor: string;
  Icon: React.ComponentType<{ className?: string }>;
}

const BADGE_CONFIGS: Record<BlockerType, BadgeConfig> = {
  SYNC: {
    label: 'CRITICAL',
    bgColor: 'bg-destructive/10',
    textColor: 'text-destructive',
    Icon: Alert02Icon,
  },
  ASYNC: {
    label: 'INFO',
    bgColor: 'bg-accent/10',
    textColor: 'text-accent-foreground',
    Icon: Idea01Icon,
  },
};

export function BlockerBadge({ type, className = '' }: BlockerBadgeProps) {
  const config = BADGE_CONFIGS[type];

  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium ${config.bgColor} ${config.textColor} ${className}`}
      title={`${type} blocker - ${type === 'SYNC' ? 'Agent paused, immediate action required' : 'Agent continuing, info only'}`}
    >
      <config.Icon className="h-3.5 w-3.5" aria-hidden="true" />
      <span>{config.label}</span>
    </span>
  );
}
