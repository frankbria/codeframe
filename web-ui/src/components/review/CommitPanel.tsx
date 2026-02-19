'use client';

import { useState } from 'react';
import {
  Loading03Icon,
  GitBranchIcon,
  Idea01Icon,
} from '@hugeicons/react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Input } from '@/components/ui/input';
import { Checkbox } from '@/components/ui/checkbox';
import { Badge } from '@/components/ui/badge';

export interface CommitPanelProps {
  commitMessage: string;
  onCommitMessageChange: (message: string) => void;
  onGenerateMessage: () => void;
  onCommit: () => void;
  isGenerating: boolean;
  isCommitting: boolean;
  isCreatingPR: boolean;
  changedFiles: string[];
  onCreatePR: (title: string, body: string) => void;
}

export function CommitPanel({
  commitMessage,
  onCommitMessageChange,
  onGenerateMessage,
  onCommit,
  isGenerating,
  isCommitting,
  isCreatingPR,
  changedFiles,
  onCreatePR,
}: CommitPanelProps) {
  const [showPRForm, setShowPRForm] = useState(false);
  const [prTitle, setPrTitle] = useState('');
  const [prBody, setPrBody] = useState('');

  return (
    <Card className="flex w-80 flex-col gap-4 p-4">
      {/* Header */}
      <h3 className="text-lg font-semibold">Commit Changes</h3>

      {/* Commit message */}
      <div className="flex flex-col gap-1.5">
        <label htmlFor="commit-message" className="text-sm font-medium">
          Commit Message
        </label>
        <Textarea
          id="commit-message"
          rows={4}
          className="font-mono text-sm"
          placeholder="Describe your changes..."
          value={commitMessage}
          onChange={(e) => onCommitMessageChange(e.target.value)}
        />
        <Button
          variant="ghost"
          size="sm"
          onClick={onGenerateMessage}
          disabled={isGenerating}
          className="self-start transition-all"
        >
          {isGenerating ? (
            <Loading03Icon className="mr-1.5 h-3.5 w-3.5 animate-spin" />
          ) : (
            <Idea01Icon className="mr-1.5 h-3.5 w-3.5" />
          )}
          Generate Message
        </Button>
      </div>

      {/* Changed files */}
      <div className="flex flex-col gap-1.5">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium">Files to commit</span>
          <Badge variant="secondary" className="text-xs">
            {changedFiles.length}
          </Badge>
        </div>
        <div className="max-h-32 overflow-y-auto rounded-md border bg-muted/50 p-2">
          {changedFiles.length > 0 ? (
            changedFiles.map((file) => (
              <div
                key={file}
                className="truncate font-mono text-xs text-muted-foreground"
                title={file}
              >
                {file}
              </div>
            ))
          ) : (
            <span className="text-xs text-muted-foreground">
              No changed files
            </span>
          )}
        </div>
      </div>

      {/* Commit button */}
      <Button
        variant="default"
        onClick={onCommit}
        disabled={isCommitting || !commitMessage.trim()}
        className="w-full transition-all"
      >
        {isCommitting && (
          <Loading03Icon className="mr-1.5 h-4 w-4 animate-spin" />
        )}
        {isCommitting ? 'Committing...' : 'Commit'}
      </Button>

      {/* PR section */}
      <div className="border-t pt-4">
        <div className="flex items-center gap-2">
          <Checkbox
            id="create-pr"
            checked={showPRForm}
            onCheckedChange={(checked) => setShowPRForm(checked === true)}
          />
          <label
            htmlFor="create-pr"
            className="cursor-pointer text-sm font-medium"
          >
            Create Pull Request
          </label>
        </div>

        {showPRForm && (
          <div className="mt-3 flex flex-col gap-3">
            <div className="flex flex-col gap-1.5">
              <label htmlFor="pr-title" className="text-sm font-medium">
                PR Title
              </label>
              <Input
                id="pr-title"
                placeholder="Pull request title"
                value={prTitle}
                onChange={(e) => setPrTitle(e.target.value)}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <label htmlFor="pr-body" className="text-sm font-medium">
                Description
              </label>
              <Textarea
                id="pr-body"
                rows={3}
                placeholder="Describe the changes..."
                value={prBody}
                onChange={(e) => setPrBody(e.target.value)}
              />
            </div>
            <Button
              variant="outline"
              onClick={() => onCreatePR(prTitle, prBody)}
              disabled={isCreatingPR || !prTitle.trim()}
              className="w-full transition-all"
            >
              {isCreatingPR ? (
                <Loading03Icon className="mr-1.5 h-4 w-4 animate-spin" />
              ) : (
                <GitBranchIcon className="mr-1.5 h-4 w-4" />
              )}
              {isCreatingPR ? 'Creating PR...' : 'Create PR'}
            </Button>
          </div>
        )}
      </div>
    </Card>
  );
}
