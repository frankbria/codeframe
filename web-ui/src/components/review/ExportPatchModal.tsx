'use client';

import { useState, useCallback } from 'react';
import { Copy01Icon, Download04Icon, CheckmarkCircle01Icon } from '@hugeicons/react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';

interface ExportPatchModalProps {
  open: boolean;
  onClose: () => void;
  patchContent: string;
  filename: string;
}

export function ExportPatchModal({
  open,
  onClose,
  patchContent,
  filename,
}: ExportPatchModalProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(patchContent);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback for non-HTTPS contexts
      const textarea = document.createElement('textarea');
      textarea.value = patchContent;
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  }, [patchContent]);

  const handleDownload = useCallback(() => {
    const blob = new Blob([patchContent], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }, [patchContent, filename]);

  return (
    <Dialog open={open} onOpenChange={(isOpen) => { if (!isOpen) onClose(); }}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Export Patch</DialogTitle>
          <DialogDescription>{filename}</DialogDescription>
        </DialogHeader>

        <textarea
          readOnly
          className="h-64 w-full resize-none rounded-md border bg-muted p-3 font-mono text-xs transition-all focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-ring"
          value={patchContent}
        />

        <DialogFooter>
          <Button variant="outline" onClick={handleCopy}>
            {copied ? (
              <CheckmarkCircle01Icon className="mr-1.5 h-3.5 w-3.5 text-green-500" />
            ) : (
              <Copy01Icon className="mr-1.5 h-3.5 w-3.5" />
            )}
            {copied ? 'Copied!' : 'Copy to Clipboard'}
          </Button>
          <Button variant="default" onClick={handleDownload}>
            <Download04Icon className="mr-1.5 h-3.5 w-3.5" />
            Download
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
