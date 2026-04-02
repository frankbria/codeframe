'use client';

import { useState, useEffect } from 'react';
import { Loading03Icon } from '@hugeicons/react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';

const MODEL_OPTIONS = [
  'claude-sonnet-4-6',
  'claude-opus-4-6',
  'claude-haiku-4-5',
] as const;

interface NewSessionModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  defaultWorkspacePath: string;
  onSubmit: (data: { workspace_path: string; model: string }) => Promise<void>;
}

export function NewSessionModal({
  open,
  onOpenChange,
  defaultWorkspacePath,
  onSubmit,
}: NewSessionModalProps) {
  const [workspacePath, setWorkspacePath] = useState(defaultWorkspacePath);
  const [model, setModel] = useState<string>(MODEL_OPTIONS[0]);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Reset form when modal opens (so stale workspace path from previous open is cleared)
  useEffect(() => {
    if (open) {
      setWorkspacePath(defaultWorkspacePath);
      setModel(MODEL_OPTIONS[0]);
    }
  }, [open, defaultWorkspacePath]);

  const handleSubmit = async () => {
    setIsSubmitting(true);
    try {
      await onSubmit({ workspace_path: workspacePath, model });
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>New Session</DialogTitle>
          <DialogDescription>
            Start a new agent session for your workspace.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          <div>
            <label htmlFor="workspace-path" className="mb-1 block text-sm font-medium">
              Workspace Path
            </label>
            <Input
              id="workspace-path"
              value={workspacePath}
              onChange={(e) => setWorkspacePath(e.target.value)}
            />
          </div>

          <div>
            <label htmlFor="model-select" className="mb-1 block text-sm font-medium">
              Model
            </label>
            <Select value={model} onValueChange={setModel}>
              <SelectTrigger id="model-select">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {MODEL_OPTIONS.map((m) => (
                  <SelectItem key={m} value={m}>
                    {m}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        <DialogFooter>
          <Button
            onClick={handleSubmit}
            disabled={isSubmitting}
          >
            {isSubmitting && <Loading03Icon className="mr-2 h-4 w-4 animate-spin" />}
            Start Session
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
