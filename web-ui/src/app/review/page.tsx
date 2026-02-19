'use client';

import { useState, useEffect, useCallback, useMemo } from 'react';
import Link from 'next/link';
import useSWR from 'swr';
import { getSelectedWorkspacePath } from '@/lib/workspace-storage';
import { reviewApi, gatesApi, gitApi, prApi } from '@/lib/api';
import { parseDiff, getFilePath } from '@/lib/diffParser';
import type {
  DiffStatsResponse,
  GateResult,
  ApiError,
} from '@/types';

import { FileTreePanel } from '@/components/review/FileTreePanel';
import { DiffViewer } from '@/components/review/DiffViewer';
import { DiffNavigation } from '@/components/review/DiffNavigation';
import { ReviewHeader } from '@/components/review/ReviewHeader';
import { CommitPanel } from '@/components/review/CommitPanel';
import { ExportPatchModal } from '@/components/review/ExportPatchModal';
import { PRCreatedModal } from '@/components/review/PRCreatedModal';

export default function ReviewPage() {
  const [workspacePath, setWorkspacePath] = useState<string | null>(null);
  const [workspaceReady, setWorkspaceReady] = useState(false);

  // Core state
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [selectedFileIndex, setSelectedFileIndex] = useState(0);
  const [gateResult, setGateResult] = useState<GateResult | null>(null);
  const [commitMessage, setCommitMessage] = useState('');

  // Loading states
  const [isRunningGates, setIsRunningGates] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [isCommitting, setIsCommitting] = useState(false);
  const [isCreatingPR, setIsCreatingPR] = useState(false);

  // Modal states
  const [showPatchModal, setShowPatchModal] = useState(false);
  const [patchContent, setPatchContent] = useState('');
  const [patchFilename, setPatchFilename] = useState('');
  const [showPRModal, setShowPRModal] = useState(false);
  const [prUrl, setPrUrl] = useState('');
  const [prNumber, setPrNumber] = useState(0);

  // Feedback
  const [feedback, setFeedback] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  useEffect(() => {
    setWorkspacePath(getSelectedWorkspacePath());
    setWorkspaceReady(true);
  }, []);

  // Fetch diff data
  const {
    data: diffData,
    error: diffError,
    mutate: mutateDiff,
  } = useSWR<DiffStatsResponse>(
    workspacePath ? `/api/v2/review/diff?path=${workspacePath}` : null,
    () => reviewApi.getDiff(workspacePath!)
  );

  // Parse diff into structured files
  const diffFiles = useMemo(
    () => (diffData?.diff ? parseDiff(diffData.diff) : []),
    [diffData?.diff]
  );

  // Auto-generate commit message on first load
  useEffect(() => {
    if (!workspacePath || !diffData || commitMessage) return;
    reviewApi
      .generateCommitMessage(workspacePath)
      .then((res) => setCommitMessage(res.message))
      .catch(() => {});
  }, [workspacePath, diffData, commitMessage]);

  // Clear feedback after 5 seconds
  useEffect(() => {
    if (!feedback) return;
    const timer = setTimeout(() => setFeedback(null), 5000);
    return () => clearTimeout(timer);
  }, [feedback]);

  const handleRunGates = useCallback(async () => {
    if (!workspacePath) return;
    setIsRunningGates(true);
    try {
      const result = await gatesApi.run(workspacePath);
      setGateResult(result);
    } catch (err) {
      setFeedback({ type: 'error', message: (err as ApiError).detail || 'Failed to run gates' });
    } finally {
      setIsRunningGates(false);
    }
  }, [workspacePath]);

  const handleExportPatch = useCallback(async () => {
    if (!workspacePath) return;
    try {
      const result = await reviewApi.getPatch(workspacePath);
      setPatchContent(result.patch);
      setPatchFilename(result.filename);
      setShowPatchModal(true);
    } catch (err) {
      setFeedback({ type: 'error', message: (err as ApiError).detail || 'Failed to export patch' });
    }
  }, [workspacePath]);

  const handleGenerateMessage = useCallback(async () => {
    if (!workspacePath) return;
    setIsGenerating(true);
    try {
      const result = await reviewApi.generateCommitMessage(workspacePath);
      setCommitMessage(result.message);
    } catch (err) {
      setFeedback({ type: 'error', message: (err as ApiError).detail || 'Failed to generate message' });
    } finally {
      setIsGenerating(false);
    }
  }, [workspacePath]);

  const handleCommit = useCallback(async () => {
    if (!workspacePath || !commitMessage.trim()) return;
    const files = diffData?.changed_files.map((f) => f.path) ?? [];
    if (files.length === 0) {
      setFeedback({ type: 'error', message: 'No files to commit' });
      return;
    }
    setIsCommitting(true);
    try {
      const result = await gitApi.commit(workspacePath, files, commitMessage);
      setFeedback({
        type: 'success',
        message: `Committed ${result.files_changed} files: ${result.commit_hash.slice(0, 7)}`,
      });
      setCommitMessage('');
      mutateDiff(); // Refresh diff
    } catch (err) {
      setFeedback({ type: 'error', message: (err as ApiError).detail || 'Failed to commit' });
    } finally {
      setIsCommitting(false);
    }
  }, [workspacePath, commitMessage, diffData, mutateDiff]);

  const handleCreatePR = useCallback(
    async (title: string, body: string) => {
      if (!workspacePath) return;
      setIsCreatingPR(true);
      try {
        const result = await prApi.create(workspacePath, {
          branch: '', // Let backend use current branch
          title,
          body,
        });
        setPrUrl(result.url);
        setPrNumber(result.number);
        setShowPRModal(true);
      } catch (err) {
        setFeedback({ type: 'error', message: (err as ApiError).detail || 'Failed to create PR' });
      } finally {
        setIsCreatingPR(false);
      }
    },
    [workspacePath]
  );

  const handleFileSelect = useCallback(
    (filePath: string) => {
      setSelectedFile(filePath);
      const idx = diffFiles.findIndex(
        (f) => getFilePath(f).includes(filePath) || filePath.includes(getFilePath(f))
      );
      if (idx >= 0) setSelectedFileIndex(idx);
    },
    [diffFiles]
  );

  const handlePrevFile = useCallback(() => {
    if (selectedFileIndex <= 0) return;
    const newIdx = selectedFileIndex - 1;
    setSelectedFileIndex(newIdx);
    setSelectedFile(getFilePath(diffFiles[newIdx]));
  }, [selectedFileIndex, diffFiles]);

  const handleNextFile = useCallback(() => {
    if (selectedFileIndex >= diffFiles.length - 1) return;
    const newIdx = selectedFileIndex + 1;
    setSelectedFileIndex(newIdx);
    setSelectedFile(getFilePath(diffFiles[newIdx]));
  }, [selectedFileIndex, diffFiles]);

  // Hydration guard
  if (!workspaceReady) return null;

  // No workspace
  if (!workspacePath) {
    return (
      <main className="min-h-screen bg-background">
        <div className="mx-auto max-w-7xl px-4 py-8">
          <div className="rounded-lg border bg-muted/50 p-6 text-center">
            <p className="text-muted-foreground">
              No workspace selected. Return to{' '}
              <Link href="/" className="text-primary hover:underline">
                Workspace
              </Link>{' '}
              and select a project.
            </p>
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className="flex h-[calc(100vh-0px)] flex-col bg-background">
      {/* Feedback banner */}
      {feedback && (
        <div
          className={`px-4 py-2 text-sm ${
            feedback.type === 'success'
              ? 'bg-green-100 text-green-800'
              : 'bg-red-100 text-red-800'
          }`}
        >
          {feedback.message}
        </div>
      )}

      {/* Header */}
      <div className="shrink-0 p-4 pb-0">
        <ReviewHeader
          filesChanged={diffData?.files_changed ?? 0}
          insertions={diffData?.insertions ?? 0}
          deletions={diffData?.deletions ?? 0}
          gateResult={gateResult}
          isRunningGates={isRunningGates}
          onRunGates={handleRunGates}
          onExportPatch={handleExportPatch}
        />
      </div>

      {/* Navigation */}
      {diffFiles.length > 0 && (
        <div className="shrink-0 px-4 pt-2">
          <DiffNavigation
            currentFileIndex={selectedFileIndex}
            totalFiles={diffFiles.length}
            currentFileName={
              diffFiles.length > 0
                ? getFilePath(diffFiles[selectedFileIndex])
                : ''
            }
            onPrevious={handlePrevFile}
            onNext={handleNextFile}
          />
        </div>
      )}

      {/* Main content area */}
      <div className="flex min-h-0 flex-1 gap-4 p-4">
        {/* File tree (left sidebar) */}
        <FileTreePanel
          files={diffData?.changed_files ?? []}
          selectedFile={selectedFile}
          onFileSelect={handleFileSelect}
        />

        {/* Diff viewer (center) */}
        <DiffViewer
          diffFiles={diffFiles}
          selectedFile={selectedFile}
        />

        {/* Commit panel (right sidebar) */}
        <CommitPanel
          commitMessage={commitMessage}
          onCommitMessageChange={setCommitMessage}
          onGenerateMessage={handleGenerateMessage}
          onCommit={handleCommit}
          isGenerating={isGenerating}
          isCommitting={isCommitting}
          isCreatingPR={isCreatingPR}
          changedFiles={diffData?.changed_files.map((f) => f.path) ?? []}
          onCreatePR={handleCreatePR}
        />
      </div>

      {/* Error state */}
      {diffError && (
        <div className="mx-4 mb-4 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
          Failed to load diff: {(diffError as ApiError).detail || 'Unknown error'}
        </div>
      )}

      {/* Modals */}
      <ExportPatchModal
        open={showPatchModal}
        onClose={() => setShowPatchModal(false)}
        patchContent={patchContent}
        filename={patchFilename}
      />

      <PRCreatedModal
        open={showPRModal}
        onClose={() => setShowPRModal(false)}
        prUrl={prUrl}
        prNumber={prNumber}
      />
    </main>
  );
}
