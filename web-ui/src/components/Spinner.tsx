/**
 * Spinner Component
 * Feature: 011-project-creation-flow (User Story 5)
 * Sprint: 9.5 - Critical UX Fixes
 *
 * Reusable loading spinner with accessibility support
 */

import React from 'react';
import type { SpinnerProps } from '@/types/project';

export const Spinner: React.FC<SpinnerProps> = ({ size = 'md' }) => {
  // Size mappings: sm=16px, md=32px, lg=48px
  const sizeClasses = {
    sm: 'w-4 h-4 border-2',
    md: 'w-8 h-8 border-4',
    lg: 'w-12 h-12 border-4',
  } as const;

  // Defensive fallback: validate size and default to 'md' if invalid
  const validSize = (size && size in sizeClasses) ? size : 'md';

  return (
    <div
      className={`${sizeClasses[validSize]} border-blue-600 border-t-transparent rounded-full animate-spin`}
      role="status"
      aria-label="Loading"
      data-testid="spinner"
    />
  );
};

export default Spinner;
