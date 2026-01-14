/**
 * BlockerBadge Component (049-human-in-loop, T016)
 * Displays a color-coded badge showing blocker type (SYNC/ASYNC)
 */

'use client';

import type { BlockerType } from '../types/blocker';

interface BlockerBadgeProps {
  type: BlockerType;
  className?: string;
}

interface BadgeConfig {
  label: string;
  bgColor: string;
  textColor: string;
  icon: string;
}

const BADGE_CONFIGS: Record<BlockerType, BadgeConfig> = {
  SYNC: {
    label: 'CRITICAL',
    bgColor: 'bg-destructive/10',
    textColor: 'text-destructive',
    icon: '🚨',
  },
  ASYNC: {
    label: 'INFO',
    bgColor: 'bg-accent/10',
    textColor: 'text-accent-foreground',
    icon: '💡',
  },
};

export function BlockerBadge({ type, className = '' }: BlockerBadgeProps) {
  const config = BADGE_CONFIGS[type];

  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium ${config.bgColor} ${config.textColor} ${className}`}
      title={`${type} blocker - ${type === 'SYNC' ? 'Agent paused, immediate action required' : 'Agent continuing, info only'}`}
    >
      <span className="text-sm">{config.icon}</span>
      <span>{config.label}</span>
    </span>
  );
}
