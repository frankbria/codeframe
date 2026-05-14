'use client';

import Link from 'next/link';
import { PlayCircleIcon, CheckmarkCircle01Icon, LinkCircleIcon, Cancel01Icon, ArrowTurnBackwardIcon, Loading03Icon, BookOpen01Icon, MoneyBag02Icon } from '@hugeicons/react';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Tooltip, TooltipTrigger, TooltipContent, TooltipProvider } from '@/components/ui/tooltip';
import { STATUS_INFO } from '@/lib/taskStatusInfo';
import type { Task, TaskStatus, ProofRequirement, TaskCostEntry } from '@/types';

/** Format cost for the inline badge.
 *
 * AI per-task costs commonly sit below $0.01, so 2dp would display "$0.00"
 * and hide real spend. Mirrors TopTasksTable's 4dp precision under $1 and
 * falls back to 2dp once costs cross a dollar.
 */
function formatBadgeCost(value: number): string {
  if (value < 0.01) {
    return value.toLocaleString('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 4,
      maximumFractionDigits: 4,
    });
  }
  if (value < 1) {
    return `$${value.toFixed(2)}`;
  }
  return value.toLocaleString('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function formatTokens(n: number): string {
  return n.toLocaleString('en-US');
}

/** Map backend TaskStatus to badge variant name. */
const STATUS_BADGE_VARIANT: Record<TaskStatus, string> = {
  BACKLOG: 'backlog',
  READY: 'ready',
  IN_PROGRESS: 'in-progress',
  DONE: 'done',
  BLOCKED: 'blocked',
  FAILED: 'failed',
  MERGED: 'merged',
};

/** Human-readable status labels. */
const STATUS_LABEL: Record<TaskStatus, string> = {
  BACKLOG: 'Backlog',
  READY: 'Ready',
  IN_PROGRESS: 'In Progress',
  DONE: 'Done',
  BLOCKED: 'Blocked',
  FAILED: 'Failed',
  MERGED: 'Merged',
};

interface TaskCardProps {
  task: Task;
  selectionMode: boolean;
  selected: boolean;
  onToggleSelect: (taskId: string) => void;
  onClick: (taskId: string) => void;
  onExecute: (taskId: string) => void;
  onMarkReady: (taskId: string) => void;
  /** Optional — when omitted, IN_PROGRESS cards silently hide the Stop button. TaskBoardView always provides this. */
  onStop?: (taskId: string) => void;
  /** Optional — when omitted, FAILED cards silently hide the Reset button. TaskBoardView always provides this. */
  onReset?: (taskId: string) => void;
  isLoading?: boolean;
  /** Map of requirement ID → ProofRequirement for badge lookup (shared SWR cache from parent). */
  requirementsMap?: Map<string, ProofRequirement>;
  /** Map of task ID → cost entry. When present and entry has nonzero cost, a cost badge renders. */
  costMap?: Map<string, TaskCostEntry>;
}

export function TaskCard({
  task,
  selectionMode,
  selected,
  onToggleSelect,
  onClick,
  onExecute,
  onMarkReady,
  onStop,
  onReset,
  isLoading = false,
  requirementsMap,
  costMap,
}: TaskCardProps) {
  const reqIds = task.requirement_ids ?? [];
  const firstReq = reqIds.length > 0 ? requirementsMap?.get(reqIds[0]) : undefined;
  const overflowCount = reqIds.length > 1 ? reqIds.length - 1 : 0;
  const costEntry = costMap?.get(task.id);
  const showCostBadge = costEntry !== undefined && costEntry.total_cost_usd > 0;
  return (
    <Card
      className="cursor-pointer transition-colors hover:border-primary/50 focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-ring"
      onClick={() => onClick(task.id)}
      onKeyDown={(e) => {
        if (e.target !== e.currentTarget) return;
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onClick(task.id);
        }
      }}
      role="button"
      tabIndex={0}
      aria-label={`View details for ${task.title}`}
    >
      <CardContent className="p-3">
        {/* Single TooltipProvider for the entire card to avoid per-tooltip provider overhead */}
        <TooltipProvider>
        {/* Top row: checkbox (if selection mode) + status badge */}
        <div className="mb-2 flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            {selectionMode && (
              <Checkbox
                checked={selected}
                onCheckedChange={() => onToggleSelect(task.id)}
                onClick={(e) => e.stopPropagation()}
                aria-label={`Select ${task.title}`}
              />
            )}
            <Tooltip>
              <TooltipTrigger asChild>
                <Badge variant={STATUS_BADGE_VARIANT[task.status] as never}>
                  {STATUS_LABEL[task.status]}
                </Badge>
              </TooltipTrigger>
              <TooltipContent className="max-w-[220px] space-y-1">
                <p className="text-xs font-medium">{STATUS_INFO[task.status].meaning}</p>
                <p className="text-xs text-muted-foreground">{STATUS_INFO[task.status].nextSteps}</p>
              </TooltipContent>
            </Tooltip>
          </div>
          {task.depends_on.length > 0 && (
            <Tooltip>
              <TooltipTrigger asChild>
                <span className="flex cursor-default items-center gap-1 text-xs text-muted-foreground">
                  <LinkCircleIcon className="h-3.5 w-3.5" />
                  {task.depends_on.length}
                </span>
              </TooltipTrigger>
              <TooltipContent>
                Depends on {task.depends_on.length} task{task.depends_on.length !== 1 ? 's' : ''}. This task will become READY when all dependencies complete.
              </TooltipContent>
            </Tooltip>
          )}
        </div>

        {/* Title */}
        <h4 className="truncate text-sm font-medium">{task.title}</h4>

        {/* Description snippet */}
        {task.description && (
          <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">
            {task.description}
          </p>
        )}

        {/* Requirement badges */}
        {reqIds.length > 0 && (
          <div
            className="mt-2 flex flex-wrap items-center gap-1"
            onClick={(e) => e.stopPropagation()}
            onKeyDown={(e) => e.stopPropagation()}
          >
            <BookOpen01Icon className="h-3 w-3 shrink-0 text-muted-foreground" />
            <Link href={`/proof/${encodeURIComponent(reqIds[0])}`}>
              <Badge variant="outline" className="h-5 cursor-pointer gap-1 px-1.5 text-[10px] hover:bg-accent">
                <span className="font-mono">{reqIds[0].slice(0, 10)}</span>
                {firstReq?.glitch_type && (
                  <span className="text-muted-foreground">· {firstReq.glitch_type}</span>
                )}
              </Badge>
            </Link>
            {overflowCount > 0 && (
              <span className="text-[10px] text-muted-foreground">+{overflowCount}</span>
            )}
          </div>
        )}

        {/* Cost badge (issue #558) */}
        {showCostBadge && costEntry && (
          <div
            className="mt-2 flex items-center gap-1"
            onClick={(e) => e.stopPropagation()}
            onKeyDown={(e) => e.stopPropagation()}
          >
            <Tooltip>
              <TooltipTrigger asChild>
                <Badge
                  data-testid="cost-badge"
                  variant="outline"
                  className="h-5 gap-1 px-1.5 text-[10px]"
                >
                  <MoneyBag02Icon className="h-3 w-3" />
                  <span className="tabular-nums">{formatBadgeCost(costEntry.total_cost_usd)}</span>
                </Badge>
              </TooltipTrigger>
              <TooltipContent className="max-w-[220px] space-y-0.5 text-xs">
                <p>Input tokens: {formatTokens(costEntry.input_tokens)}</p>
                <p>Output tokens: {formatTokens(costEntry.output_tokens)}</p>
                <p className="font-medium">
                  Total: {formatBadgeCost(costEntry.total_cost_usd)}
                </p>
              </TooltipContent>
            </Tooltip>
          </div>
        )}

        {/* Action buttons */}
        {(task.status === 'READY' || task.status === 'BACKLOG' || task.status === 'IN_PROGRESS' || task.status === 'FAILED') && (
          <div className="mt-2 flex gap-1">
            {isLoading ? (
              <span role="status" aria-label="Loading">
                <Loading03Icon className="h-3.5 w-3.5 animate-spin text-muted-foreground" />
              </span>
            ) : (
              <>
                {task.status === 'READY' && (
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-7 gap-1 px-2 text-xs"
                    onClick={(e) => {
                      e.stopPropagation();
                      onExecute(task.id);
                    }}
                  >
                    <PlayCircleIcon className="h-3.5 w-3.5" />
                    Execute
                  </Button>
                )}
                {task.status === 'BACKLOG' && (
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-7 gap-1 px-2 text-xs"
                    onClick={(e) => {
                      e.stopPropagation();
                      onMarkReady(task.id);
                    }}
                  >
                    <CheckmarkCircle01Icon className="h-3.5 w-3.5" />
                    Mark Ready
                  </Button>
                )}
                {task.status === 'IN_PROGRESS' && onStop && (
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-7 gap-1 px-2 text-xs text-destructive"
                    onClick={(e) => {
                      e.stopPropagation();
                      onStop(task.id);
                    }}
                  >
                    <Cancel01Icon className="h-3.5 w-3.5" />
                    Stop
                  </Button>
                )}
                {task.status === 'FAILED' && onReset && (
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-7 gap-1 px-2 text-xs"
                    onClick={(e) => {
                      e.stopPropagation();
                      onReset(task.id);
                    }}
                  >
                    <ArrowTurnBackwardIcon className="h-3.5 w-3.5" />
                    Reset
                  </Button>
                )}
              </>
            )}
          </div>
        )}
        </TooltipProvider>
      </CardContent>
    </Card>
  );
}
