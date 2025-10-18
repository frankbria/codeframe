'use client';

import React, { useState } from 'react';
import { useRouter } from 'next/navigation';
import { projectsApi } from '@/lib/api';
import type { ProjectResponse } from '@/types';

type FormState = 'idle' | 'submitting' | 'success' | 'error';
type StartState = 'idle' | 'starting';

interface ProjectCreationFormProps {
  onSuccess?: (project: ProjectResponse) => void;
}

const ProjectCreationForm: React.FC<ProjectCreationFormProps> = ({ onSuccess }) => {
  const router = useRouter();

  // Form fields
  const [projectName, setProjectName] = useState('');
  const [projectType, setProjectType] = useState('python');

  // Component states
  const [formState, setFormState] = useState<FormState>('idle');
  const [startState, setStartState] = useState<StartState>('idle');
  const [errorMessage, setErrorMessage] = useState('');
  const [createdProject, setCreatedProject] = useState<ProjectResponse | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    // Client-side validation
    if (!projectName.trim()) {
      setErrorMessage('Project name cannot be empty');
      setFormState('error');
      return;
    }

    setFormState('submitting');
    setErrorMessage('');

    try {
      const response = await projectsApi.createProject(projectName, projectType);
      setCreatedProject(response.data);
      setFormState('success');
      setErrorMessage('');

      // Call onSuccess callback if provided
      if (onSuccess) {
        onSuccess(response.data);
      }
    } catch (error: any) {
      setFormState('error');

      // Extract error message from API response
      if (error.response?.data?.detail) {
        setErrorMessage(error.response.data.detail);
      } else if (error.response?.data?.error) {
        setErrorMessage(error.response.data.error);
      } else {
        setErrorMessage('An unexpected error occurred');
      }
    }
  };

  const handleStartProject = async () => {
    if (!createdProject) return;

    setStartState('starting');

    try {
      await projectsApi.startProject(createdProject.id);
      // Navigate to project page after successful start
      router.push(`/projects/${createdProject.id}`);
    } catch (error: any) {
      setStartState('idle');
      setErrorMessage(error.response?.data?.detail || 'Failed to start project');
    }
  };

  return (
    <div className="bg-white shadow-md rounded-lg p-6 max-w-md">
      <h2 className="text-2xl font-bold mb-6 text-gray-800">Create New Project</h2>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label htmlFor="project-name" className="block text-sm font-medium text-gray-700 mb-1">
            Project Name
          </label>
          <input
            id="project-name"
            type="text"
            value={projectName}
            onChange={(e) => setProjectName(e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 text-gray-900"
            disabled={formState === 'submitting' || formState === 'success'}
          />
        </div>

        <div>
          <label htmlFor="project-type" className="block text-sm font-medium text-gray-700 mb-1">
            Project Type
          </label>
          <select
            id="project-type"
            value={projectType}
            onChange={(e) => setProjectType(e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 text-gray-900"
            disabled={formState === 'submitting' || formState === 'success'}
          >
            <option value="python">python</option>
            <option value="javascript">javascript</option>
            <option value="typescript">typescript</option>
            <option value="java">java</option>
            <option value="go">go</option>
            <option value="rust">rust</option>
          </select>
        </div>

        <button
          type="submit"
          disabled={formState === 'submitting' || formState === 'success'}
          className="w-full bg-blue-600 text-white py-2 px-4 rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:bg-gray-400 disabled:cursor-not-allowed"
        >
          {formState === 'submitting' ? 'Creating...' : 'Create Project'}
        </button>
      </form>

      {/* Error Message */}
      {formState === 'error' && errorMessage && (
        <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded-md">
          <p className="text-red-700 text-sm">
            <span className="mr-2">⚠️</span>
            Error: {errorMessage}
          </p>
        </div>
      )}

      {/* Success Message */}
      {formState === 'success' && createdProject && (
        <div className="mt-4 space-y-3">
          <div className="p-3 bg-green-50 border border-green-200 rounded-md">
            <p className="text-green-700 text-sm">
              <span className="mr-2" aria-hidden="true">✅</span>
              <span>Project created successfully: {createdProject.name}</span>
            </p>
          </div>

          {/* Start Project Button */}
          <button
            onClick={handleStartProject}
            disabled={startState === 'starting'}
            className="w-full bg-green-600 text-white py-2 px-4 rounded-md hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-green-500 focus:ring-offset-2 disabled:bg-gray-400 disabled:cursor-not-allowed"
          >
            {startState === 'starting' ? 'Starting...' : 'Start Project'}
          </button>
        </div>
      )}
    </div>
  );
};

export default ProjectCreationForm;
