/**
 * QualityGatesPanel Component
 *
 * Dashboard-level panel for quality gates with task selection
 * Displays overview of all gate types and detailed status view
 */

'use client';

import { useState, useEffect, useMemo, useRef } from 'react';
import type { Task } from '@/types/agentState';
import type {
  QualityGateStatus as QualityGateStatusType,
  GateTypeE2E,
  QualityGateStatusValue,
} from '@/types/qualityGates';
import { mapE2EToBackend } from '@/types/qualityGates';
import { fetchQualityGateStatus } from '@/api/qualityGates';
import QualityGateStatus from './QualityGateStatus';
import GateStatusIndicator from './GateStatusIndicator';

interface QualityGatesPanelProps {
  projectId: number;
  tasks: Task[];
}

/**
 * Get individual gate status from quality gate status response
 *
 * IMPORTANT: This function uses a conservative approach:
 * - Returns 'failed' if gate has explicit failures
 * - Returns 'running' if overall status is running
 * - Returns 'passed' ONLY if overall status is passed AND no failures exist for this gate
 * - Returns 'pending' (null) for all other cases (no explicit status for this gate)
 *
 * This prevents showing false positives where a gate appears passed when it hasn't run.
 */
function getGateStatus(
  status: QualityGateStatusType | null,
  gateType: GateTypeE2E
): QualityGateStatusValue {
  // No status available - gate hasn't run yet
  if (!status) {
    return null; // pending
  }

  // Map E2E type to backend type for lookup
  const backendType = mapE2EToBackend(gateType);

  // Check if this specific gate has failures
  const hasFailure = status.failures.some(f => f.gate === backendType);

  if (hasFailure) {
    return 'failed';
  }

  // If overall status is running, inherit that
  if (status.status === 'running') {
    return 'running';
  }

  // CRITICAL FIX: Only mark as passed if overall status is passed
  // This prevents false positives for gates that haven't been explicitly evaluated
  if (status.status === 'passed') {
    return 'passed';
  }

  // Default to pending for any other case (including null overall status)
  // This is conservative: better to show pending than incorrectly show passed
  return null; // pending
}

/**
 * QualityGatesPanel Component
 *
 * Main panel for quality gates with task selection and gate overview
 */
export default function QualityGatesPanel({
  projectId,
  tasks,
}: QualityGatesPanelProps) {
  const [selectedTaskId, setSelectedTaskId] = useState<number | null>(null);
  const [gateStatus, setGateStatus] = useState<QualityGateStatusType | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Track if we've already auto-selected a task to prevent unnecessary updates
  const hasAutoSelectedRef = useRef(false);

  // Filter tasks that are completed or in_progress (candidates for quality gates)
  const eligibleTasks = useMemo(() => {
    return tasks.filter(t => t.status === 'completed' || t.status === 'in_progress');
  }, [tasks]);

  // Auto-select first eligible task if none selected (optimized with useRef)
  useEffect(() => {
    // Reset flag if no eligible tasks (allows re-selection when tasks are re-added)
    if (eligibleTasks.length === 0) {
      hasAutoSelectedRef.current = false;
    }

    if (!hasAutoSelectedRef.current && eligibleTasks.length > 0 && selectedTaskId === null) {
      setSelectedTaskId(eligibleTasks[0].id);
      hasAutoSelectedRef.current = true;
    }
  }, [eligibleTasks, selectedTaskId]);

  // Fetch quality gate status when task is selected
  useEffect(() => {
    if (selectedTaskId === null) {
      setGateStatus(null);
      setError(null);
      return;
    }

    async function fetchStatus() {
      setLoading(true);
      setError(null);
      try {
        const status = await fetchQualityGateStatus(selectedTaskId!, projectId);
        setGateStatus(status);
      } catch (err) {
        const errorMessage = err instanceof Error ? err.message : 'Failed to fetch quality gate status';
        console.error('Quality gate fetch error:', err);
        setError(errorMessage);
        setGateStatus(null);
      } finally {
        setLoading(false);
      }
    }

    fetchStatus();
  }, [selectedTaskId, projectId]);

  // All gate types in order
  const gateTypes: GateTypeE2E[] = ['tests', 'coverage', 'type-check', 'lint', 'review'];

  // No eligible tasks
  if (eligibleTasks.length === 0) {
    return (
      <div
        className="p-4 bg-gray-50 rounded-lg border border-gray-200"
        role="status"
        aria-label="No tasks available"
      >
        <div className="flex items-center gap-2 text-gray-600">
          <span aria-hidden="true">ℹ️</span>
          <span className="text-sm">
            No tasks available for quality gate evaluation. Complete or start a task first.
          </span>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Task Selector */}
      <div className="flex items-center gap-3">
        <label htmlFor="task-selector" className="text-sm font-medium text-gray-700">
          Select Task:
        </label>
        <select
          id="task-selector"
          value={selectedTaskId || ''}
          onChange={(e) => setSelectedTaskId(Number(e.target.value))}
          className="flex-1 px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 text-sm"
          aria-label="Select task for quality gate status"
        >
          {eligibleTasks.map(task => (
            <option key={task.id} value={task.id}>
              Task #{task.id}: {task.title}
            </option>
          ))}
        </select>
      </div>

      {/* Error State */}
      {error && (
        <div
          className="p-4 bg-red-50 rounded-lg border border-red-200"
          role="alert"
          aria-live="polite"
        >
          <div className="flex items-start">
            <span className="text-red-600 text-xl mr-2" aria-hidden="true">⚠️</span>
            <div className="flex-1">
              <h4 className="text-sm font-medium text-red-900">Error Loading Quality Gates</h4>
              <p className="text-sm text-red-700 mt-1">{error}</p>
            </div>
          </div>
        </div>
      )}

      {/* Loading State */}
      {loading ? (
        <div
          className="flex items-center justify-center p-8"
          role="status"
          aria-live="polite"
          aria-label="Loading quality gates"
        >
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" aria-hidden="true"></div>
          <span className="ml-3 text-sm text-gray-600">Loading quality gates...</span>
        </div>
      ) : !error && (
        <>
          {/* Gate Status Indicators Grid */}
          <div
            className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3"
            role="list"
            aria-label="Quality gate status indicators"
          >
            {gateTypes.map(gateType => (
              <GateStatusIndicator
                key={gateType}
                gateType={gateType}
                status={getGateStatus(gateStatus, gateType)}
                testId={`gate-${gateType}`}
              />
            ))}
          </div>

          {/* Detailed Status View */}
          {selectedTaskId && (
            <div className="border-t border-gray-200 pt-4">
              <h3 className="text-sm font-semibold text-gray-900 mb-3">Detailed Status</h3>
              <QualityGateStatus taskId={selectedTaskId} />
            </div>
          )}
        </>
      )}
    </div>
  );
}
