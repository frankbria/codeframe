'use client';

import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';

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
  const [isEditing, setIsEditing] = useState(false);
  const [editValue, setEditValue] = useState('');

  // Reset state each time the dialog opens or detected stack changes
  useEffect(() => {
    if (!open) return;
    setIsEditing(!detectedStack);
    setEditValue(detectedStack ?? '');
  }, [open, detectedStack]);

  const isManualMode = !detectedStack || isEditing;

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onCancel(); }}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>
            {isManualMode && !detectedStack
              ? 'Tech Stack Detection'
              : isEditing
              ? 'Edit Tech Stack'
              : 'Tech Stack Detected'}
          </DialogTitle>
          <DialogDescription>
            {!detectedStack
              ? 'Could not auto-detect. Enter your stack manually.'
              : isEditing
              ? 'Update the detected tech stack to match your project.'
              : 'Is this the correct tech stack for your project?'}
          </DialogDescription>
        </DialogHeader>

        {isManualMode ? (
          <Textarea
            placeholder="e.g. Python with uv, pytest, ruff"
            value={editValue}
            onChange={(e) => setEditValue(e.target.value)}
          />
        ) : (
          <div className="rounded-md border bg-muted/50 px-4 py-3">
            <p className="font-medium">{detectedStack}</p>
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={onCancel}>
            Cancel
          </Button>
          {!isManualMode && (
            <Button variant="outline" onClick={() => setIsEditing(true)}>
              Edit
            </Button>
          )}
          {isManualMode ? (
            <Button onClick={() => onConfirm(editValue)} disabled={!editValue.trim()}>
              Save
            </Button>
          ) : (
            <Button onClick={() => onConfirm(detectedStack!)}>
              Confirm
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
