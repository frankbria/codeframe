/**
 * Type definitions for Project Creation Flow
 * Feature: 011-project-creation-flow
 * Sprint: 9.5 - Critical UX Fixes
 */


/**
 * Props for ProjectCreationForm component
 */
export interface ProjectCreationFormProps {
  /**
   * Called when project is successfully created
   * @param projectId - The ID of the newly created project
   */
  onSuccess: (projectId: number) => void;

  /**
   * Optional: Called before API request (for loading state)
   */
  onSubmit?: () => void;

  /**
   * Optional: Called on API error
   * @param error - The error object from the API
   */
  onError?: (error: Error) => void;
}

/**
 * Props for Spinner component
 */
export interface SpinnerProps {
  /**
   * Size variant for the spinner
   * - sm: 16px (4rem)
   * - md: 32px (8rem) - default
   * - lg: 48px (12rem)
   */
  size?: 'sm' | 'md' | 'lg';
}

/**
 * Form validation errors
 */
export interface FormErrors {
  name?: string;
  description?: string;
  submit?: string;
}

/**
 * Internal form state for ProjectCreationForm
 */
export interface ProjectFormState {
  name: string;
  description: string;
  errors: FormErrors;
  isSubmitting: boolean;
}
