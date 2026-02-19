'use client';

import { ArrowLeft01Icon, ArrowRight01Icon } from '@hugeicons/react';
import { Button } from '@/components/ui/button';

interface DiffNavigationProps {
  currentFileIndex: number;
  totalFiles: number;
  currentFileName: string;
  onPrevious: () => void;
  onNext: () => void;
}

/**
 * Compact navigation bar for stepping through diff files.
 *
 * Displays [Prev] File X of Y: filename [Next] with disabled
 * states at the boundaries.
 */
export function DiffNavigation({
  currentFileIndex,
  totalFiles,
  currentFileName,
  onPrevious,
  onNext,
}: DiffNavigationProps) {
  if (totalFiles === 0) return null;

  const isFirst = currentFileIndex <= 0;
  const isLast = currentFileIndex >= totalFiles - 1;

  return (
    <nav
      className="flex items-center gap-2 border-b bg-card px-4 py-2"
      aria-label="File navigation"
    >
      <Button
        variant="outline"
        size="sm"
        onClick={onPrevious}
        disabled={isFirst}
        aria-label="Previous file"
      >
        <ArrowLeft01Icon className="mr-1 h-3.5 w-3.5" />
        Prev
      </Button>

      <span className="flex-1 truncate text-center text-xs text-muted-foreground">
        <span className="font-medium text-foreground">
          File {currentFileIndex + 1} of {totalFiles}
        </span>
        <span className="mx-1.5">:</span>
        <span className="font-mono">{currentFileName}</span>
      </span>

      <Button
        variant="outline"
        size="sm"
        onClick={onNext}
        disabled={isLast}
        aria-label="Next file"
      >
        Next
        <ArrowRight01Icon className="ml-1 h-3.5 w-3.5" />
      </Button>
    </nav>
  );
}
