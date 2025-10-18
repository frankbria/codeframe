/**
 * Home page - Project list and creation
 * Task: cf-27 - Frontend Project Initialization Workflow
 */

import ProjectList from '@/components/ProjectList';

export default function Home() {
  return (
    <main className="min-h-screen bg-gray-50">
      <div className="max-w-7xl mx-auto px-4 py-8 sm:px-6 lg:px-8">
        <ProjectList />
      </div>
    </main>
  );
}
