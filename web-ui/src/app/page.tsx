/**
 * Home page - Project Creation Workflow
 * Feature: 011-project-creation-flow (User Story 1 & 4)
 * Sprint: 9.5 - Critical UX Fixes
 *
 * Displays welcome message and ProjectCreationForm at root route.
 * Automatically redirects to Dashboard after successful project creation.
 */

'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import ProjectCreationForm from '@/components/ProjectCreationForm';
import { Spinner } from '@/components/Spinner';

export default function HomePage() {
  const router = useRouter();
  const [isCreating, setIsCreating] = useState(false);

  /**
   * US4: Redirect to Dashboard after successful project creation
   * Called by ProjectCreationForm when project is created
   */
  const handleProjectCreated = (projectId: number) => {
    router.push(`/projects/${projectId}`);
  };

  /**
   * US1: Show loading spinner during project creation
   * Called by ProjectCreationForm before API request
   */
  const handleSubmit = () => {
    setIsCreating(true);
  };

  /**
   * US1: Hide loading spinner on error
   * Called by ProjectCreationForm if API request fails
   */
  const handleError = () => {
    setIsCreating(false);
  };

  return (
    <main className="min-h-screen bg-gray-50 flex items-center justify-center p-4">
      <div className="max-w-2xl w-full">
        {/* Welcome Header */}
        <div className="text-center mb-8">
          <h1 className="text-4xl font-bold text-gray-900 mb-2">
            Welcome to CodeFRAME
          </h1>
          <p className="text-lg text-gray-600">
            AI coding agents that work autonomously while you sleep
          </p>
        </div>

        {/* Form or Loading Spinner */}
        {isCreating ? (
          <div className="text-center">
            <Spinner size="lg" />
            <p className="mt-4 text-gray-600">Creating your project...</p>
          </div>
        ) : (
          <ProjectCreationForm
            onSuccess={handleProjectCreated}
            onSubmit={handleSubmit}
            onError={handleError}
          />
        )}
      </div>
    </main>
  );
}
