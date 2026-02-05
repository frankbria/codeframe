'use client';

import { useState, useCallback } from 'react';
import ReactMarkdown from 'react-markdown';
import { Loading03Icon } from '@hugeicons/react';
import { Button } from '@/components/ui/button';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';

interface MarkdownEditorProps {
  content: string;
  /** Called when the user explicitly saves. Returns the updated content. */
  onSave: (content: string, changeSummary: string) => Promise<void>;
  isSaving?: boolean;
}

export function MarkdownEditor({
  content: initialContent,
  onSave,
  isSaving = false,
}: MarkdownEditorProps) {
  const [draft, setDraft] = useState(initialContent);
  const [changeSummary, setChangeSummary] = useState('');
  const [activeTab, setActiveTab] = useState('edit');

  const hasChanges = draft !== initialContent;

  const handleSave = useCallback(async () => {
    if (!hasChanges) return;
    const summary = changeSummary.trim() || 'Updated PRD content';
    await onSave(draft, summary);
    setChangeSummary('');
  }, [draft, changeSummary, hasChanges, onSave]);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <TabsList>
            <TabsTrigger value="edit">Edit</TabsTrigger>
            <TabsTrigger value="preview">Preview</TabsTrigger>
          </TabsList>
        </Tabs>

        {hasChanges && (
          <div className="flex items-center gap-2">
            <input
              type="text"
              value={changeSummary}
              onChange={(e) => setChangeSummary(e.target.value)}
              placeholder="Change summary (optional)"
              className="h-8 w-56 rounded-md border bg-background px-2 text-xs placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-ring"
            />
            <Button size="sm" onClick={handleSave} disabled={isSaving}>
              {isSaving ? (
                <>
                  <Loading03Icon className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                  Saving...
                </>
              ) : (
                'Save'
              )}
            </Button>
          </div>
        )}
      </div>

      {activeTab === 'edit' && (
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          className="min-h-[400px] w-full rounded-md border bg-background px-4 py-3 font-mono text-sm leading-relaxed placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-ring"
          placeholder="Write your PRD in markdown..."
        />
      )}

      {activeTab === 'preview' && (
        <div className="min-h-[400px] rounded-md border px-4 py-3">
          {draft.trim() ? (
            <div className="prose prose-sm max-w-none text-foreground prose-headings:text-foreground prose-strong:text-foreground prose-code:rounded prose-code:bg-muted prose-code:px-1 prose-code:py-0.5 prose-code:text-sm prose-pre:bg-muted prose-pre:text-foreground">
              <ReactMarkdown>{draft}</ReactMarkdown>
            </div>
          ) : (
            <p className="text-sm italic text-muted-foreground">
              Nothing to preview yet.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
