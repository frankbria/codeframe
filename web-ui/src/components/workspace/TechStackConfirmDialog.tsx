'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';

interface TechStackConfirmDialogProps {
  open: boolean;
  detectedStack: string | null;
  onConfirm: (stack: string) => void;
  onCancel: () => void;
}

export function TechStackConfirmDialog({
  open,
  detectedStack,
  onConfirm,
  onCancel,
}: TechStackConfirmDialogProps) {
  const [isEditing, setIsEditing] = useState(!detectedStack);
  const [editValue, setEditValue] = useState(detectedStack ?? '');

  if (!open) return null;

  const handleConfirm = () => {
    onConfirm(detectedStack!);
  };

  const handleSave = () => {
    onConfirm(editValue);
  };

  // Failure mode or edit mode: show textarea
  if (!detectedStack || isEditing) {
    return (
      <div
        role="dialog"
        aria-modal="true"
        className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      >
        <div className="w-full max-w-md rounded-lg border bg-background p-6 shadow-lg">
          <h2 className="text-lg font-semibold">
            {detectedStack ? 'Edit Tech Stack' : 'Tech Stack Detection'}
          </h2>

          {!detectedStack && (
            <p className="mt-2 text-sm text-destructive">
              Could not auto-detect. Enter your stack manually.
            </p>
          )}

          <Textarea
            className="mt-4"
            placeholder="e.g. Python with uv, pytest, ruff"
            value={editValue}
            onChange={(e) => setEditValue(e.target.value)}
          />

          <div className="mt-4 flex justify-end gap-2">
            <Button variant="outline" onClick={onCancel}>
              Cancel
            </Button>
            <Button onClick={handleSave} disabled={!editValue.trim()}>
              Save
            </Button>
          </div>
        </div>
      </div>
    );
  }

  // Confirm mode
  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
    >
      <div className="w-full max-w-md rounded-lg border bg-background p-6 shadow-lg">
        <h2 className="text-lg font-semibold">Tech Stack Detected</h2>
        <p className="mt-2 text-sm text-muted-foreground">
          Is this the correct tech stack for your project?
        </p>

        <div className="mt-4 rounded-md border bg-muted/50 px-4 py-3">
          <p className="font-medium">{detectedStack}</p>
        </div>

        <div className="mt-4 flex justify-end gap-2">
          <Button variant="outline" onClick={onCancel}>
            Cancel
          </Button>
          <Button variant="outline" onClick={() => setIsEditing(true)}>
            Edit
          </Button>
          <Button onClick={handleConfirm}>
            Confirm
          </Button>
        </div>
      </div>
    </div>
  );
}
