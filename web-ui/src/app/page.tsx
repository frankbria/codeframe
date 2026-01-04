/**
 * Home page - Project List View
 * Feature: 011-project-creation-flow
 *
 * Displays the user's projects at root route with ability to create new projects.
 * Wrapped with ProtectedRoute to ensure only authenticated users can access.
 */

'use client';

import ProjectList from '@/components/ProjectList';
import { ProtectedRoute } from '@/components/auth/ProtectedRoute';

export default function HomePage() {
  return (
    <ProtectedRoute>
      <main className="min-h-screen bg-background">
        <div className="max-w-7xl mx-auto px-4 py-8">
          {/* Page Header */}
          <div className="mb-8">
            <h1 className="text-3xl font-bold text-foreground">
              Your Projects
            </h1>
            <p className="mt-2 text-muted-foreground">
              AI coding agents that work autonomously while you sleep
            </p>
          </div>

          {/* Project List with Create Button */}
          <ProjectList />
        </div>
      </main>
    </ProtectedRoute>
  );
}
