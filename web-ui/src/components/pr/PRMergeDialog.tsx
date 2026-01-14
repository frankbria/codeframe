/**
 * PRMergeDialog Component
 * Confirmation dialog for merging pull requests
 *
 * Features:
 * - Merge method selection (squash, merge, rebase)
 * - Delete branch option
 * - Warning about irreversibility
 * - Loading state during merge
 * - Error handling with display
 */

'use client';

import { useState, useCallback } from 'react';
import { pullRequestsApi } from '@/lib/api';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { Checkbox } from '@/components/ui/checkbox';
import {
  AlertCircleIcon,
  Loading03Icon,
  GitBranchIcon,
  ArrowRight01Icon,
  Alert02Icon,
} from '@hugeicons/react';
import type { PullRequest, MergeMethod } from '@/types/pullRequest';

// ============================================================================
// Types
// ============================================================================

export interface PRMergeDialogProps {
  pr: PullRequest;
  projectId: number;
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

// ============================================================================
// Constants
// ============================================================================

const MERGE_METHODS: { value: MergeMethod; label: string; description: string }[] = [
  {
    value: 'squash',
    label: 'Squash and merge',
    description: 'Combine all commits into one before merging',
  },
  {
    value: 'merge',
    label: 'Create merge commit',
    description: 'Preserve all commits with a merge commit',
  },
  {
    value: 'rebase',
    label: 'Rebase and merge',
    description: 'Reapply commits on top of base branch',
  },
];

// ============================================================================
// Component
// ============================================================================

export default function PRMergeDialog({
  pr,
  projectId,
  isOpen,
  onClose,
  onSuccess,
}: PRMergeDialogProps) {
  // Form state
  const [mergeMethod, setMergeMethod] = useState<MergeMethod>('squash');
  const [deleteBranch, setDeleteBranch] = useState(true);

  // Submission state
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Handle merge
  const handleMerge = useCallback(async () => {
    setIsSubmitting(true);
    setError(null);

    try {
      await pullRequestsApi.merge(projectId, pr.pr_number, {
        method: mergeMethod,
        delete_branch: deleteBranch,
      });
      onSuccess();
      onClose();
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to merge pull request';
      setError(message);
    } finally {
      setIsSubmitting(false);
    }
  }, [projectId, pr.pr_number, mergeMethod, deleteBranch, onSuccess, onClose]);

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle>Merge Pull Request</DialogTitle>
          <DialogDescription>
            Merge <span className="font-medium">#{pr.pr_number}</span> into {pr.base_branch}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6 py-4">
          {/* PR Info */}
          <div className="bg-muted/50 rounded-lg p-4">
            <h4 className="font-medium text-foreground mb-2">{pr.title}</h4>
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <GitBranchIcon className="h-4 w-4" />
              <span className="font-mono text-xs">{pr.head_branch}</span>
              <ArrowRight01Icon className="h-3 w-3" />
              <span className="font-mono text-xs">{pr.base_branch}</span>
            </div>
          </div>

          {/* Error Message */}
          {error && (
            <div className="flex items-center gap-2 p-3 bg-destructive/10 text-destructive rounded-md">
              <AlertCircleIcon className="h-4 w-4 flex-shrink-0" />
              <span className="text-sm">{error}</span>
            </div>
          )}

          {/* Merge Method Selection */}
          <div className="space-y-3">
            <Label>Merge Method</Label>
            <RadioGroup
              value={mergeMethod}
              onValueChange={(value: string) => setMergeMethod(value as MergeMethod)}
              className="space-y-2"
            >
              {MERGE_METHODS.map((method) => (
                <div key={method.value} className="flex items-start space-x-3">
                  <RadioGroupItem
                    value={method.value}
                    id={`merge-${method.value}`}
                    className="mt-1"
                  />
                  <div className="flex-1">
                    <Label
                      htmlFor={`merge-${method.value}`}
                      className="font-medium cursor-pointer"
                    >
                      {method.label}
                    </Label>
                    <p className="text-sm text-muted-foreground">{method.description}</p>
                  </div>
                </div>
              ))}
            </RadioGroup>
          </div>

          {/* Delete Branch Option */}
          <div className="flex items-center space-x-2">
            <Checkbox
              id="delete-branch"
              checked={deleteBranch}
              onCheckedChange={(checked: boolean | 'indeterminate') => setDeleteBranch(checked === true)}
            />
            <Label htmlFor="delete-branch" className="cursor-pointer">
              Delete branch after merge
            </Label>
          </div>

          {/* Warning */}
          <div className="flex items-start gap-2 p-3 bg-yellow-100 dark:bg-yellow-900/20 text-yellow-800 dark:text-yellow-200 rounded-md">
            <Alert02Icon className="h-4 w-4 flex-shrink-0 mt-0.5" />
            <span className="text-sm">
              This action cannot be undone. The commits will be permanently merged into{' '}
              <span className="font-medium">{pr.base_branch}</span>.
            </span>
          </div>
        </div>

        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            onClick={onClose}
            disabled={isSubmitting}
          >
            Cancel
          </Button>
          <Button
            type="button"
            onClick={handleMerge}
            disabled={isSubmitting}
          >
            {isSubmitting ? (
              <>
                <Loading03Icon className="h-4 w-4 mr-2 animate-spin" />
                Merging...
              </>
            ) : (
              'Confirm Merge'
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
