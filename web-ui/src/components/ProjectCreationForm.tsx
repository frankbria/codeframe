/**
 * ProjectCreationForm Component
 * Feature: 011-project-creation-flow (User Stories 2, 3, 4)
 * Sprint: 9.5 - Critical UX Fixes
 *
 * Enhanced form with description field, comprehensive validation,
 * and improved error handling.
 */

'use client';

import React, { useState } from 'react';
import { projectsApi } from '@/lib/api';
import type { ProjectCreationFormProps, FormErrors } from '@/types/project';

const ProjectCreationForm: React.FC<ProjectCreationFormProps> = ({
  onSuccess,
  onSubmit,
  onError,
}) => {
  // Form fields
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');

  // Validation and submission state
  const [errors, setErrors] = useState<FormErrors>({});
  const [isSubmitting, setIsSubmitting] = useState(false);

  /**
   * US2: Validate project name (min 3 chars, pattern /^[a-z0-9-_]+$/)
   */
  const validateName = (): boolean => {
    const newErrors = { ...errors };

    if (!name.trim()) {
      newErrors.name = 'Project name is required';
    } else if (name.length < 3) {
      newErrors.name = 'Project name must be at least 3 characters';
    } else if (!/^[a-z0-9-_]+$/.test(name)) {
      newErrors.name = 'Only lowercase letters, numbers, hyphens, and underscores allowed';
    } else {
      delete newErrors.name;
    }

    setErrors(newErrors);
    return !newErrors.name;
  };

  /**
   * US2: Validate description (min 10 chars, max 500 chars)
   */
  const validateDescription = (): boolean => {
    const newErrors = { ...errors };

    if (!description.trim()) {
      newErrors.description = 'Project description is required';
    } else if (description.length < 10) {
      newErrors.description = 'Description must be at least 10 characters';
    } else if (description.length > 500) {
      newErrors.description = 'Description must be 500 characters or less';
    } else {
      delete newErrors.description;
    }

    setErrors(newErrors);
    return !newErrors.description;
  };

  /**
   * US3: Handle form submission with validation and API call
   */
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    // Clear previous submit errors
    const newErrors = { ...errors };
    delete newErrors.submit;
    setErrors(newErrors);

    // Validate all fields before submission
    const nameValid = validateName();
    const descValid = validateDescription();

    if (!nameValid || !descValid) {
      return;
    }

    // Call parent onSubmit callback (for loading spinner)
    onSubmit?.();

    setIsSubmitting(true);

    try {
      // US3: API call with name and description
      const response = await projectsApi.createProject(name, description);

      // US3: Call parent onSuccess callback with project ID
      onSuccess(response.data.id);
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } catch (error: any) {
      setIsSubmitting(false);

      // Call parent onError callback
      onError?.(error);

      const newErrors: FormErrors = {};

      // US3: Handle different error types
      if (error.response?.status === 409) {
        // Duplicate project name
        newErrors.name = `Project '${name}' already exists`;
      } else if (error.response?.status === 400 || error.response?.status === 422) {
        // Validation errors from backend
        if (error.response?.data?.detail) {
          if (Array.isArray(error.response.data.detail)) {
            const errorMsg = error.response.data.detail
              // eslint-disable-next-line @typescript-eslint/no-explicit-any
              .map((err: any) => err.msg || JSON.stringify(err))
              .join(', ');
            newErrors.submit = errorMsg;
          } else if (typeof error.response.data.detail === 'string') {
            newErrors.submit = error.response.data.detail;
          } else {
            newErrors.submit = JSON.stringify(error.response.data.detail);
          }
        } else {
          newErrors.submit = 'Validation error occurred';
        }
      } else if (error.response?.status === 500) {
        // Server error
        newErrors.submit = 'Server error occurred. Please try again later.';
      } else if (error.message === 'Network Error' || !error.response) {
        // Network failure
        newErrors.submit = 'Failed to create project. Please check your connection and try again.';
      } else {
        newErrors.submit = 'An unexpected error occurred';
      }

      setErrors(newErrors);
    }
  };

  // Check if form is valid (for submit button disabled state)
  const isFormValid = name.trim().length >= 3 &&
                      description.trim().length >= 10 &&
                      /^[a-z0-9-_]+$/.test(name) &&
                      !isSubmitting;

  return (
    <div className="bg-white shadow-md rounded-lg p-6 max-w-md w-full">
      <h2 className="text-2xl font-bold mb-6 text-gray-800">Create New Project</h2>

      <form onSubmit={handleSubmit} className="space-y-4">
        {/* US2: Project Name Field with Validation */}
        <div>
          <label htmlFor="project-name" className="block text-sm font-medium text-gray-700 mb-1">
            Project Name <span className="text-red-500">*</span>
          </label>
          <input
            id="project-name"
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            onBlur={validateName}
            className={`w-full px-3 py-2 border rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 text-gray-900 ${
              errors.name ? 'border-red-500' : 'border-gray-300'
            }`}
            placeholder="my-awesome-project"
            disabled={isSubmitting}
            maxLength={100}
          />
          {errors.name && (
            <p className="mt-1 text-sm text-red-600">{errors.name}</p>
          )}
          <p className="mt-1 text-xs text-gray-500">
            Lowercase letters, numbers, hyphens, and underscores only (min 3 chars)
          </p>
        </div>

        {/* US2: Description Field with Validation and Character Counter */}
        <div>
          <label htmlFor="description" className="block text-sm font-medium text-gray-700 mb-1">
            Description <span className="text-red-500">*</span>
          </label>
          <textarea
            id="description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            onBlur={validateDescription}
            className={`w-full px-3 py-2 border rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 text-gray-900 ${
              errors.description ? 'border-red-500' : 'border-gray-300'
            }`}
            rows={4}
            placeholder="Describe what your project will do..."
            disabled={isSubmitting}
            maxLength={500}
          />
          {errors.description && (
            <p className="mt-1 text-sm text-red-600">{errors.description}</p>
          )}
          {/* US2: Character Counter */}
          <p className="mt-1 text-xs text-gray-500">
            {description.length} / 500 characters (min 10)
          </p>
        </div>

        {/* US2: Submit Button (disabled when form invalid) */}
        <button
          type="submit"
          disabled={!isFormValid}
          className="w-full bg-blue-600 text-white py-2 px-4 rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors"
        >
          {isSubmitting ? 'Creating...' : 'Create Project & Start Discovery'}
        </button>

        {/* US2: Hint text below button */}
        <p className="text-xs text-gray-500 text-center">
          After creation, you&apos;ll begin Socratic discovery with AI agents
        </p>
      </form>

      {/* US3: Error Message Display */}
      {errors.submit && (
        <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded-md">
          <p className="text-red-700 text-sm">
            <span className="mr-2">⚠️</span>
            Error: {errors.submit}
          </p>
        </div>
      )}
    </div>
  );
};

export default ProjectCreationForm;
