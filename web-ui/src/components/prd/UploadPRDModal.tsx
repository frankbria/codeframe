'use client';

import { useState, useRef } from 'react';
import { Upload04Icon, Loading03Icon } from '@hugeicons/react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { Button } from '@/components/ui/button';
import { prdApi } from '@/lib/api';
import type { PrdResponse, ApiError } from '@/types';

interface UploadPRDModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  workspacePath: string;
  onSuccess: (prd: PrdResponse) => void;
}

export function UploadPRDModal({
  open,
  onOpenChange,
  workspacePath,
  onSuccess,
}: UploadPRDModalProps) {
  const [content, setContent] = useState('');
  const [title, setTitle] = useState('');
  const [fileName, setFileName] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const resetForm = () => {
    setContent('');
    setTitle('');
    setFileName(null);
    setError(null);
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setFileName(file.name);
    setError(null);

    const reader = new FileReader();
    reader.onload = (event) => {
      const text = event.target?.result;
      if (typeof text === 'string') {
        setContent(text);
        // Use filename without extension as default title
        if (!title) {
          setTitle(file.name.replace(/\.md$/i, ''));
        }
      }
    };
    reader.onerror = () => {
      setError('Failed to read file');
    };
    reader.readAsText(file);
  };

  const handleSubmit = async () => {
    const trimmed = content.trim();
    if (!trimmed) {
      setError('PRD content cannot be empty');
      return;
    }

    setIsSubmitting(true);
    setError(null);

    try {
      const prd = await prdApi.create(
        workspacePath,
        trimmed,
        title.trim() || undefined
      );
      onSuccess(prd);
      resetForm();
      onOpenChange(false);
    } catch (err) {
      const apiError = err as ApiError;
      setError(apiError.detail || 'Failed to create PRD');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(value) => {
        if (!value) resetForm();
        onOpenChange(value);
      }}
    >
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>Upload PRD</DialogTitle>
          <DialogDescription>
            Upload a markdown file or paste PRD content directly.
          </DialogDescription>
        </DialogHeader>

        {/* Optional title */}
        <div>
          <label
            htmlFor="prd-title"
            className="mb-1 block text-sm font-medium"
          >
            Title{' '}
            <span className="text-muted-foreground">(optional)</span>
          </label>
          <input
            id="prd-title"
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Extracted from content if not provided"
            className="w-full rounded-md border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-ring"
          />
        </div>

        <Tabs defaultValue="paste">
          <TabsList className="w-full">
            <TabsTrigger value="paste" className="flex-1">
              Paste Markdown
            </TabsTrigger>
            <TabsTrigger value="file" className="flex-1">
              Upload File
            </TabsTrigger>
          </TabsList>

          <TabsContent value="paste">
            <textarea
              value={content}
              onChange={(e) => {
                setContent(e.target.value);
                setError(null);
              }}
              placeholder="Paste your PRD markdown here..."
              rows={12}
              className="w-full rounded-md border bg-background px-3 py-2 font-mono text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-ring"
            />
          </TabsContent>

          <TabsContent value="file">
            <div className="flex flex-col items-center gap-4 rounded-lg border-2 border-dashed p-8">
              <Upload04Icon className="h-10 w-10 text-muted-foreground/50" />
              <div className="text-center">
                {fileName ? (
                  <p className="text-sm font-medium">{fileName}</p>
                ) : (
                  <p className="text-sm text-muted-foreground">
                    Select a .md file
                  </p>
                )}
              </div>
              <input
                ref={fileInputRef}
                type="file"
                accept=".md,.markdown,.txt"
                onChange={handleFileChange}
                className="hidden"
              />
              <Button
                variant="outline"
                size="sm"
                onClick={() => fileInputRef.current?.click()}
              >
                Choose File
              </Button>
              {content && (
                <p className="text-xs text-muted-foreground">
                  {content.length.toLocaleString()} characters loaded
                </p>
              )}
            </div>
          </TabsContent>
        </Tabs>

        {error && (
          <p className="text-sm text-destructive">{error}</p>
        )}

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={isSubmitting}
          >
            Cancel
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={isSubmitting || !content.trim()}
          >
            {isSubmitting ? (
              <>
                <Loading03Icon className="mr-1.5 h-4 w-4 animate-spin" />
                Creating...
              </>
            ) : (
              'Create PRD'
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
