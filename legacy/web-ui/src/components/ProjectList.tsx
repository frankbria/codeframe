'use client';

import { useState } from 'react';
import useSWR from 'swr';
import { useRouter } from 'next/navigation';
import { Add01Icon } from '@hugeicons/react';
import { projectsApi } from '@/lib/api';
import ProjectCreationForm from '@/components/ProjectCreationForm';
import { Spinner } from '@/components/Spinner';

/**
 * Formats an ISO date string to a readable format
 * @param dateString - ISO date string (e.g., "2025-01-15T10:00:00Z")
 * @returns Formatted date (e.g., "January 15, 2025")
 */
const formatDate = (dateString: string): string => {
  const date = new Date(dateString);
  return date.toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  });
};

/**
 * Renders the user's projects list with controls to create a new project and navigate to project details.
 *
 * Shows loading and error states, an empty placeholder when no projects exist, a responsive grid of project cards,
 * and a toggleable project creation form that hides on success and refreshes the project list.
 *
 * @returns The rendered project list UI including loading/error states, creation form, empty-state placeholder, and project cards.
 */
export default function ProjectList() {
  const router = useRouter();
  const [showForm, setShowForm] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [loadingMessage, setLoadingMessage] = useState('Creating your project...');

  // Fetch projects using SWR
  const { data, error, isLoading, mutate } = useSWR(
    '/projects',
    () => projectsApi.list().then((res) => res.data.projects)
  );

  const handleProjectClick = (projectId: number) => {
    router.push(`/projects/${projectId}`);
  };

  const handleProjectKeyDown = (e: React.KeyboardEvent, projectId: number) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      handleProjectClick(projectId);
    }
  };

  /**
   * Called by ProjectCreationForm before API request
   * Shows loading spinner during creation
   */
  const handleSubmit = () => {
    setLoadingMessage('Creating your project...');
    setIsCreating(true);
  };

  /**
   * Called by ProjectCreationForm if API request fails
   * Hides loading spinner on error
   */
  const handleError = () => {
    setIsCreating(false);
  };

  /**
   * Start discovery and redirect to Dashboard after successful project creation
   * Called by ProjectCreationForm when project is created
   *
   * Always refreshes project list to ensure consistency, even if discovery fails.
   * User is navigated to project dashboard regardless of discovery outcome.
   */
  const handleProjectCreated = async (projectId: number) => {
    // Update loading message to show discovery phase
    setLoadingMessage('Starting discovery...');

    try {
      // Start the project to initiate discovery process
      await projectsApi.startProject(projectId);
    } catch (error) {
      // Log error but still navigate - user can manually start if needed
      console.error('Failed to auto-start project discovery:', error);
    } finally {
      // Always refresh project list to ensure data consistency
      // This runs whether discovery succeeds or fails
      try {
        await mutate();
      } catch {
        // Silently handle mutate errors - navigation will still occur
      }
      setIsCreating(false);
    }

    // Navigate to the project dashboard
    router.push(`/projects/${projectId}`);
  };

  // Loading state
  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="text-muted-foreground">Loading projects...</div>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="text-destructive">Failed to load projects. Please try again.</div>
      </div>
    );
  }

  const projects = data || [];

  return (
    <div className="space-y-6">
      {/* Header with Create button */}
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold text-foreground">Your Projects</h2>
        <button
          onClick={() => setShowForm(true)}
          data-testid="create-project-button"
          className="px-4 py-2 bg-primary text-primary-foreground rounded-md hover:bg-primary/90 transition-colors"
        >
          Create New Project
        </button>
      </div>

      {/* Project Creation Form or Loading Spinner */}
      {showForm && (
        <div className="bg-muted rounded-lg p-6 border border-border">
          {isCreating ? (
            <div className="text-center py-8">
              <Spinner size="lg" />
              <p className="mt-4 text-muted-foreground">{loadingMessage}</p>
            </div>
          ) : (
            <>
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold text-foreground">Create New Project</h3>
                <button
                  onClick={() => setShowForm(false)}
                  aria-label="Close create project form"
                  className="text-muted-foreground hover:text-foreground"
                >
                  ✕
                </button>
              </div>
              <ProjectCreationForm
                onSuccess={handleProjectCreated}
                onSubmit={handleSubmit}
                onError={handleError}
              />
            </>
          )}
        </div>
      )}

      {/* Projects Grid or Empty State */}
      {projects.length === 0 ? (
        <div className="flex items-center justify-center min-h-[400px] bg-muted rounded-lg border-2 border-dashed border-border">
          <div className="text-center px-6 py-8">
            {/* Decorative icon */}
            <div
              data-testid="empty-state-icon"
              className="mx-auto w-16 h-16 mb-6 rounded-full bg-primary/10 flex items-center justify-center"
            >
              <Add01Icon className="w-8 h-8 text-primary" aria-hidden="true" />
            </div>

            {/* Message */}
            <h3 className="text-xl font-semibold text-foreground mb-2">
              No projects yet
            </h3>
            <p className="text-muted-foreground text-base mb-6 max-w-sm">
              Create your first project and let AI coding agents work autonomously while you sleep.
            </p>

            {/* CTA Button */}
            <button
              onClick={() => setShowForm(true)}
              data-testid="empty-state-create-button"
              className="px-6 py-3 bg-primary text-primary-foreground rounded-md hover:bg-primary/90 transition-colors font-medium"
            >
              Get Started
            </button>
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6" data-testid="project-list">
          {projects.map((project) => (
            <div
              key={project.id}
              role="button"
              tabIndex={0}
              aria-label={`Open project ${project.name}, status: ${project.status}, phase: ${project.phase}`}
              onClick={() => handleProjectClick(project.id)}
              onKeyDown={(e) => handleProjectKeyDown(e, project.id)}
              className="bg-card rounded-lg shadow p-6 cursor-pointer hover:shadow-lg transition-shadow focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2"
            >
              <h3 className="text-lg font-semibold text-foreground">{project.name}</h3>
              <div className="mt-2 space-y-1 text-sm text-foreground">
                <p>
                  Status: <span className="font-medium">{project.status}</span>
                </p>
                <p>
                  Phase: <span className="font-medium">{project.phase}</span>
                </p>
                {project.created_at && (
                  <p className="text-muted-foreground">{formatDate(project.created_at)}</p>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}