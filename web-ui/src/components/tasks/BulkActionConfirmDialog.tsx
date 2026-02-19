'use client';

import { Loading03Icon } from '@hugeicons/react';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';

export type BulkActionType = 'execute' | 'stop' | 'reset';

interface BulkActionConfirmDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  actionType: BulkActionType;
  taskCount: number;
  onConfirm: () => void;
  isLoading: boolean;
}

const ACTION_CONFIG: Record<BulkActionType, {
  title: string;
  description: (count: number) => string;
  destructive: boolean;
}> = {
  execute: {
    title: 'Execute Tasks',
    description: (count) => `This will execute ${count} task(s) using the selected strategy.`,
    destructive: false,
  },
  stop: {
    title: 'Stop Tasks',
    description: (count) => `This will stop ${count} running task(s). They will need to be re-executed.`,
    destructive: true,
  },
  reset: {
    title: 'Reset Tasks',
    description: (count) => `This will reset ${count} failed task(s) to READY status for re-execution.`,
    destructive: false,
  },
};

export function BulkActionConfirmDialog({
  open,
  onOpenChange,
  actionType,
  taskCount,
  onConfirm,
  isLoading,
}: BulkActionConfirmDialogProps) {
  const config = ACTION_CONFIG[actionType];

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{config.title}</AlertDialogTitle>
          <AlertDialogDescription>
            {config.description(taskCount)}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction
            onClick={(e) => {
              e.preventDefault();
              onConfirm();
            }}
            disabled={isLoading}
            className={config.destructive ? 'bg-destructive text-destructive-foreground hover:bg-destructive/90' : ''}
          >
            {isLoading && <Loading03Icon className="mr-2 h-4 w-4 animate-spin" />}
            Confirm
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
