/**
 * PRCreationDialog Component
 * Dialog for creating new pull requests
 *
 * Features:
 * - Branch selection from available branches
 * - Pre-filled title and description from defaults
 * - Form validation
 * - Loading state during submission
 * - Error handling with display
 */

'use client';

import { useState, useEffect, useCallback } from 'react';
import { pullRequestsApi } from '@/lib/api';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { AlertCircleIcon, Loading03Icon } from '@hugeicons/react';
import type { CreatePRRequest } from '@/types/pullRequest';

// ============================================================================
// Types
// ============================================================================

export interface PRCreationDialogProps {
  projectId: number;
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
  defaultBranch?: string;
  defaultTitle?: string;
  defaultDescription?: string;
}

interface FormData {
  branch: string;
  title: string;
  description: string;
  baseBranch: string;
}

interface FormErrors {
  branch?: string;
  title?: string;
}

// ============================================================================
// Component
// ============================================================================

export default function PRCreationDialog({
  projectId,
  isOpen,
  onClose,
  onSuccess,
  defaultBranch = '',
  defaultTitle = '',
  defaultDescription = '',
}: PRCreationDialogProps) {
  // Form state
  const [formData, setFormData] = useState<FormData>({
    branch: defaultBranch,
    title: defaultTitle,
    description: defaultDescription,
    baseBranch: 'main',
  });

  // Validation and submission state
  const [errors, setErrors] = useState<FormErrors>({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  // Reset form when dialog opens/closes or defaults change
  useEffect(() => {
    if (isOpen) {
      setFormData({
        branch: defaultBranch,
        title: defaultTitle,
        description: defaultDescription,
        baseBranch: 'main',
      });
      setErrors({});
      setSubmitError(null);
    }
  }, [isOpen, defaultBranch, defaultTitle, defaultDescription]);

  // Validate form
  const validateForm = useCallback((): boolean => {
    const newErrors: FormErrors = {};

    if (!formData.branch.trim()) {
      newErrors.branch = 'Branch is required';
    }

    if (!formData.title.trim()) {
      newErrors.title = 'Title is required';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  }, [formData]);

  // Handle form submission
  const handleSubmit = useCallback(async () => {
    if (!validateForm()) {
      return;
    }

    setIsSubmitting(true);
    setSubmitError(null);

    try {
      const request: CreatePRRequest = {
        branch: formData.branch,
        title: formData.title,
        body: formData.description,
        base: formData.baseBranch,
      };

      await pullRequestsApi.create(projectId, request);
      onSuccess();
      onClose();
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to create pull request';
      setSubmitError(message);
    } finally {
      setIsSubmitting(false);
    }
  }, [formData, projectId, validateForm, onSuccess, onClose]);

  // Handle field changes
  const handleFieldChange = useCallback(
    (field: keyof FormData, value: string) => {
      setFormData((prev) => ({ ...prev, [field]: value }));
      // Clear field error on change
      if (errors[field as keyof FormErrors]) {
        setErrors((prev) => ({ ...prev, [field]: undefined }));
      }
    },
    [errors]
  );

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle>Create Pull Request</DialogTitle>
        </DialogHeader>

        <div className="space-y-4 py-4">
          {/* Error Message */}
          {submitError && (
            <div className="flex items-center gap-2 p-3 bg-destructive/10 text-destructive rounded-md">
              <AlertCircleIcon className="h-4 w-4 flex-shrink-0" />
              <span className="text-sm">{submitError}</span>
            </div>
          )}

          {/* Source Branch */}
          <div className="space-y-2">
            <Label htmlFor="branch">Source Branch</Label>
            <Input
              id="branch"
              value={formData.branch}
              onChange={(e) => handleFieldChange('branch', e.target.value)}
              placeholder="feature/my-feature"
              className={errors.branch ? 'border-destructive' : ''}
            />
            {errors.branch && (
              <p className="text-sm text-destructive">{errors.branch}</p>
            )}
          </div>

          {/* Target Branch */}
          <div className="space-y-2">
            <Label htmlFor="baseBranch">Target Branch</Label>
            <Select
              value={formData.baseBranch}
              onValueChange={(value) => handleFieldChange('baseBranch', value)}
            >
              <SelectTrigger id="baseBranch">
                <SelectValue placeholder="Select target branch" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="main">main</SelectItem>
                <SelectItem value="develop">develop</SelectItem>
                <SelectItem value="staging">staging</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {/* Title */}
          <div className="space-y-2">
            <Label htmlFor="title">Title</Label>
            <Input
              id="title"
              type="text"
              value={formData.title}
              onChange={(e) => handleFieldChange('title', e.target.value)}
              placeholder="Brief description of changes"
              className={errors.title ? 'border-destructive' : ''}
            />
            {errors.title && (
              <p className="text-sm text-destructive">{errors.title}</p>
            )}
          </div>

          {/* Description */}
          <div className="space-y-2">
            <Label htmlFor="description">Description</Label>
            <Textarea
              id="description"
              value={formData.description}
              onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => handleFieldChange('description', e.target.value)}
              placeholder="Detailed description of the changes..."
              rows={5}
            />
          </div>
        </div>

        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            onClick={onClose}
            disabled={isSubmitting}
          >
            Cancel
          </Button>
          <Button
            type="button"
            onClick={handleSubmit}
            disabled={isSubmitting}
          >
            {isSubmitting ? (
              <>
                <Loading03Icon className="h-4 w-4 mr-2 animate-spin" />
                Creating...
              </>
            ) : (
              'Create'
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
