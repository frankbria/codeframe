/**
 * PRDModal Component
 * Displays Product Requirements Document in a modal/drawer
 */

'use client';

import { useEffect, useRef, memo } from 'react';
import ReactMarkdown from 'react-markdown';
import type { PRDResponse } from '@/types/api';

interface PRDModalProps {
  isOpen: boolean;
  onClose: () => void;
  prdData: PRDResponse | null;
}

const PRDModal = memo(function PRDModal({ isOpen, onClose, prdData }: PRDModalProps) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);

  // Focus trap and escape key handler
  useEffect(() => {
    if (!isOpen) return;

    // Focus close button when modal opens
    closeButtonRef.current?.focus();

    // Handle escape key
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };

    document.addEventListener('keydown', handleEscape);

    // Prevent body scroll when modal is open
    document.body.style.overflow = 'hidden';

    return () => {
      document.removeEventListener('keydown', handleEscape);
      document.body.style.overflow = 'unset';
    };
  }, [isOpen, onClose]);

  if (!isOpen) {
    return null;
  }

  // Handle overlay click
  const handleOverlayClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (e.target === e.currentTarget) {
      onClose();
    }
  };

  // Format timestamp for display
  const formatTimestamp = (isoDate: string) => {
    try {
      const date = new Date(isoDate);
      return date.toLocaleString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return isoDate;
    }
  };

  // Render content based on status
  const renderContent = () => {
    if (!prdData) {
      return (
        <div className="text-center py-12 text-muted-foreground">
          No PRD data available
        </div>
      );
    }

    if (prdData.status === 'generating') {
      return (
        <div className="text-center py-12">
          <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-primary mb-4"></div>
          <p className="text-muted-foreground">Generating PRD...</p>
        </div>
      );
    }

    if (prdData.status === 'not_found') {
      return (
        <div className="text-center py-12 text-muted-foreground">
          <p className="text-lg font-medium mb-2">PRD Not Found</p>
          <p className="text-sm">No Product Requirements Document has been generated for this project yet.</p>
        </div>
      );
    }

    if (!prdData.prd_content || prdData.prd_content.trim() === '') {
      return (
        <div className="text-center py-12 text-muted-foreground">
          No content available
        </div>
      );
    }

    return (
      <div
        data-testid="prd-content"
        className="prose prose-sm max-w-none overflow-y-auto pr-4"
      >
        <ReactMarkdown>{prdData.prd_content}</ReactMarkdown>
      </div>
    );
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"
      onClick={handleOverlayClick}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="prd-modal-title"
        className="bg-card rounded-lg shadow-xl w-full max-w-4xl max-h-[90vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border">
          <div className="flex-1">
            <h2 id="prd-modal-title" className="text-xl font-semibold text-foreground">
              Product Requirements Document
            </h2>
            {prdData && (
              <div className="flex items-center gap-4 mt-1 text-sm text-muted-foreground">
                <span>Project: {prdData.project_id}</span>
                <span
                  className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
                    prdData.status === 'available'
                      ? 'bg-green-100 text-green-800'
                      : prdData.status === 'generating'
                      ? 'bg-yellow-100 text-yellow-800'
                      : 'bg-muted text-muted-foreground'
                  }`}
                >
                  {prdData.status.toUpperCase()}
                </span>
              </div>
            )}
          </div>
          <button
            ref={closeButtonRef}
            onClick={onClose}
            className="ml-4 p-2 text-muted-foreground hover:text-foreground hover:bg-muted rounded-md transition-colors"
            aria-label="Close"
          >
            <svg
              className="w-6 h-6"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M6 18L18 6M6 6l12 12"
              />
            </svg>
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto px-6 py-6">
          {renderContent()}
        </div>

        {/* Footer with timestamps */}
        {prdData && prdData.status === 'available' && (
          <div className="px-6 py-4 border-t border-border bg-muted">
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span>
                <span className="font-medium">Generated:</span>{' '}
                {formatTimestamp(prdData.generated_at)}
              </span>
              <span>
                <span className="font-medium">Updated:</span>{' '}
                {formatTimestamp(prdData.updated_at)}
              </span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
});

PRDModal.displayName = 'PRDModal';

export default PRDModal;
