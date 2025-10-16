/**
 * Home page - Project dashboard
 */

import Dashboard from '@/components/Dashboard';

export default function Home() {
  // In a real app, this would come from URL params or project selection
  const projectId = 1;

  return <Dashboard projectId={projectId} />;
}
