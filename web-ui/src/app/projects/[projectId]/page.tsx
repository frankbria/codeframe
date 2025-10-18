/**
 * Individual Project Dashboard Page
 * Task: cf-27 - Frontend Project Initialization Workflow
 *
 * Dynamic route for viewing a specific project's dashboard.
 * Extracts projectId from URL parameters and passes to Dashboard component.
 */

import Dashboard from '@/components/Dashboard';

interface ProjectPageProps {
  params: {
    projectId: string;
  };
}

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

  return <Dashboard projectId={projectId} />;
}
