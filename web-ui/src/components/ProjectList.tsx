'use client';

import { useState } from 'react';
import useSWR from 'swr';
import { useRouter } from 'next/navigation';
import { projectsApi } from '@/lib/api';
import ProjectCreationForm from '@/components/ProjectCreationForm';

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

  // Fetch projects using SWR
  const { data, error, isLoading, mutate } = useSWR(
    '/projects',
    () => projectsApi.list().then((res) => res.data.projects)
  );

  const handleProjectClick = (projectId: number) => {
    router.push(`/projects/${projectId}`);
  };

  const handleProjectCreated = (_projectId: number) => {
    // Hide form
    setShowForm(false);
    // Refresh project list
    mutate();
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

      {/* Project Creation Form */}
      {showForm && (
        <div className="bg-muted rounded-lg p-6 border border-border">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold text-foreground">Create New Project</h3>
            <button
              onClick={() => setShowForm(false)}
              className="text-muted-foreground hover:text-foreground"
            >
              ✕
            </button>
          </div>
          <ProjectCreationForm onSuccess={handleProjectCreated} />
        </div>
      )}

      {/* Projects Grid or Empty State */}
      {projects.length === 0 ? (
        <div className="flex items-center justify-center min-h-[300px] bg-muted rounded-lg border-2 border-dashed border-border">
          <div className="text-center">
            <p className="text-muted-foreground text-lg">
              No projects yet. Create your first project!
            </p>
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6" data-testid="project-list">
          {projects.map((project) => (
            <div
              key={project.id}
              onClick={() => handleProjectClick(project.id)}
              className="bg-card rounded-lg shadow p-6 cursor-pointer hover:shadow-lg transition-shadow"
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