/**
 * Individual Project Dashboard Page
 * Task: cf-27 - Frontend Project Initialization Workflow
 *
 * Dynamic route for viewing a specific project's dashboard.
 * Extracts projectId from URL parameters and passes to Dashboard component.
 */

'use client';

import { Profiler, ProfilerOnRenderCallback } from 'react';
import Dashboard from '@/components/Dashboard';
import { AgentStateProvider } from '@/components/AgentStateProvider';

interface ProjectPageProps {
  params: {
    projectId: string;
  };
}

// Profiler callback for performance monitoring (T128, T129)
const onRenderCallback: ProfilerOnRenderCallback = (
  id,
  phase,
  actualDuration,
  baseDuration,
  startTime,
  commitTime
) => {
  // Only log in development mode
  if (process.env.NODE_ENV === 'development') {
    // Warn if render takes longer than 50ms (T129)
    if (actualDuration > 50) {
      console.warn(
        `[Performance] Slow render detected in ${id}:`,
        `\n  Phase: ${phase}`,
        `\n  Duration: ${actualDuration.toFixed(2)}ms (exceeds 50ms threshold)`,
        `\n  Base duration: ${baseDuration.toFixed(2)}ms`
      );
    }

    // Log all render times for monitoring (T128)
    console.debug(
      `[Profiler] ${id} ${phase}:`,
      `${actualDuration.toFixed(2)}ms`,
      `(base: ${baseDuration.toFixed(2)}ms)`
    );
  }
};

export default function ProjectPage({ params }: ProjectPageProps) {
  const projectId = parseInt(params.projectId, 10);

  // Handle invalid project ID
  if (isNaN(projectId)) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <h1 className="text-2xl font-bold text-gray-900">Invalid Project ID</h1>
          <p className="mt-2 text-gray-600">
            The project ID must be a number.
          </p>
          <a
            href="/"
            className="mt-4 inline-block px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700"
          >
            Back to Projects
          </a>
        </div>
      </div>
    );
  }

  return (
    <Profiler id="Dashboard" onRender={onRenderCallback}>
      <AgentStateProvider projectId={projectId}>
        <Dashboard projectId={projectId} />
      </AgentStateProvider>
    </Profiler>
  );
}