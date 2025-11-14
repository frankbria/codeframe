/**
 * BlockerModal Component (049-human-in-loop, T022)
 * Phase 4 / User Story 2: Blocker Resolution via Dashboard
 * Modal dialog for resolving blockers with user answers
 */

'use client';

import { useState, useEffect, useCallback } from 'react';
import type { Blocker } from '../types/blocker';
import { BlockerBadge } from './BlockerBadge';
import { resolveBlocker } from '../lib/api';

interface BlockerModalProps {
  isOpen: boolean;
  blocker: Blocker | null;
  onClose: () => void;
  onResolved: () => void;
}

interface Toast {
  id: number;
  message: string;
  type: 'success' | 'error';
}

export function BlockerModal({ isOpen, blocker, onClose, onResolved }: BlockerModalProps) {
  const [answer, setAnswer] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [validationError, setValidationError] = useState<string | null>(null);

  // Reset form when modal opens/closes
  useEffect(() => {
    if (!isOpen) {
      setAnswer('');
      setValidationError(null);
      setIsSubmitting(false);
      setToasts([]);
    }
  }, [isOpen]);

  // Close modal on Escape key
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen && !isSubmitting) {
        onClose();
      }
    };

    if (isOpen) {
      document.addEventListener('keydown', handleEscape);
      return () => document.removeEventListener('keydown', handleEscape);
    }
  }, [isOpen, isSubmitting, onClose]);

  // Handle Ctrl+Enter to submit
  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      if (isValid) {
        handleSubmit();
      }
    }
  };

  // Add toast notification
  const addToast = useCallback((message: string, type: 'success' | 'error') => {
    const id = Date.now();
    setToasts((prev) => [...prev, { id, message, type }]);

    // Auto-remove after 3 seconds
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 3000);
  }, []);

  // Format waiting time
  const formatWaitingTime = (ms: number | undefined): string => {
    if (!ms) return '';

    const minutes = Math.floor(ms / 60000);
    const hours = Math.floor(minutes / 60);

    if (hours > 0) {
      return `${hours} hour${hours > 1 ? 's' : ''} ago`;
    }
    if (minutes > 0) {
      return `${minutes} minute${minutes > 1 ? 's' : ''} ago`;
    }
    return 'Just now';
  };

  // Validation
  const isValid = answer.trim().length > 0 && answer.length <= 5000;
  const charCount = answer.length;
  const showMaxLengthError = charCount > 5000;

  // Handle form submission
  const handleSubmit = async () => {
    if (!blocker || !isValid) return;

    setIsSubmitting(true);
    setValidationError(null);

    try {
      await resolveBlocker(blocker.id, answer);

      addToast('Blocker resolved successfully', 'success');

      // Call callbacks
      onResolved();
      setTimeout(() => onClose(), 500); // Small delay to show toast
    } catch (error: any) {
      // Handle specific error codes
      if (error?.response?.status === 409) {
        addToast('This blocker has already been resolved by another user', 'error');
      } else {
        addToast('Failed to resolve blocker. Please try again.', 'error');
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  // Handle backdrop click
  const handleBackdropClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (e.target === e.currentTarget && !isSubmitting) {
      onClose();
    }
  };

  if (!isOpen || !blocker) {
    return null;
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50 p-4"
      data-backdrop="true"
      onClick={handleBackdropClick}
    >
      <div
        role="dialog"
        aria-labelledby="blocker-modal-title"
        aria-modal="true"
        className="bg-white rounded-lg shadow-xl max-w-2xl w-full max-h-[90vh] overflow-hidden flex flex-col"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
          <h2 id="blocker-modal-title" className="text-xl font-semibold text-gray-900">
            Resolve Blocker
          </h2>
          <button
            onClick={onClose}
            disabled={isSubmitting}
            aria-label="Close modal"
            className="text-gray-400 hover:text-gray-600 disabled:opacity-50"
          >
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
          {/* Blocker Info */}
          <div className="space-y-3">
            {/* Badge and Waiting Time */}
            <div className="flex items-center gap-3">
              <BlockerBadge type={blocker.blocker_type} />
              <span className="text-sm text-gray-500">
                {formatWaitingTime(blocker.time_waiting_ms)}
              </span>
            </div>

            {/* Agent and Task Info */}
            <div className="text-sm text-gray-600">
              <div>
                <span className="font-medium">Agent:</span> {blocker.agent_name || blocker.agent_id}
              </div>
              {blocker.task_title && (
                <div>
                  <span className="font-medium">Task:</span> {blocker.task_title}
                </div>
              )}
            </div>

            {/* Question */}
            <div className="bg-gray-50 p-4 rounded-lg">
              <p className="text-sm font-medium text-gray-700 mb-2">Question:</p>
              <p className="text-gray-900 whitespace-pre-wrap">{blocker.question}</p>
            </div>
          </div>

          {/* Answer Input */}
          <div className="space-y-2">
            <label htmlFor="answer" className="block text-sm font-medium text-gray-700">
              Your Answer <span className="text-red-500">*</span>
            </label>
            <textarea
              id="answer"
              value={answer}
              onChange={(e) => setAnswer(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Enter your answer here... (Ctrl+Enter to submit)"
              disabled={isSubmitting}
              className={`w-full px-3 py-2 border ${
                showMaxLengthError ? 'border-red-500' : 'border-gray-300'
              } rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 resize-y min-h-[120px] disabled:bg-gray-100 disabled:cursor-not-allowed`}
            />

            {/* Character Counter and Validation */}
            <div className="flex items-center justify-between text-sm">
              <div>
                {showMaxLengthError && (
                  <span className="text-red-600">Answer cannot exceed maximum length of 5000 characters</span>
                )}
              </div>
              <span className={showMaxLengthError ? 'text-red-600 font-medium' : 'text-gray-500'}>
                {charCount} / 5000
              </span>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-gray-200 bg-gray-50">
          <button
            onClick={onClose}
            disabled={isSubmitting}
            className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={!isValid || isSubmitting}
            className="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isSubmitting ? 'Submitting...' : 'Submit Answer'}
          </button>
        </div>
      </div>

      {/* Toast Notifications */}
      <div className="fixed bottom-4 right-4 space-y-2 z-50">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className={`px-4 py-3 rounded-lg shadow-lg ${
              toast.type === 'success'
                ? 'bg-green-50 border border-green-200 text-green-800'
                : 'bg-red-50 border border-red-200 text-red-800'
            } animate-slide-in`}
          >
            <div className="flex items-center gap-2">
              {toast.type === 'success' ? (
                <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                  <path
                    fillRule="evenodd"
                    d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
                    clipRule="evenodd"
                  />
                </svg>
              ) : (
                <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                  <path
                    fillRule="evenodd"
                    d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
                    clipRule="evenodd"
                  />
                </svg>
              )}
              <span className="text-sm font-medium">{toast.message}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
