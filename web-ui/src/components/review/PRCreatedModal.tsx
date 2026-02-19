'use client';

import { useCallback } from 'react';
import { CheckmarkCircle01Icon } from '@hugeicons/react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';

interface PRCreatedModalProps {
  open: boolean;
  onClose: () => void;
  prUrl: string;
  prNumber: number;
}

export function PRCreatedModal({
  open,
  onClose,
  prUrl,
  prNumber,
}: PRCreatedModalProps) {
  const handleViewPR = useCallback(() => {
    window.open(prUrl, '_blank', 'noopener,noreferrer');
  }, [prUrl]);

  return (
    <Dialog open={open} onOpenChange={(isOpen) => { if (!isOpen) onClose(); }}>
      <DialogContent className="max-w-md">
        <DialogHeader className="items-center">
          <CheckmarkCircle01Icon className="mx-auto h-12 w-12 text-green-500" />
          <DialogTitle>Pull Request Created</DialogTitle>
          <DialogDescription className="sr-only">
            Pull request #{prNumber} has been created successfully
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-2 text-center">
          <p className="text-sm">
            <span className="font-bold">PR #{prNumber}</span>
          </p>
          <a
            href={prUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-sm text-primary transition-all hover:underline"
          >
            {prUrl}
          </a>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Close
          </Button>
          <Button variant="default" onClick={handleViewPR}>
            View PR
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
