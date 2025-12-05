/**
 * QualityGatesPanel Component
 *
 * Dashboard-level panel for quality gates with task selection
 * Displays overview of all gate types and detailed status view
 */

'use client';

import { useState, useEffect, useMemo } from 'react';
import type { Task } from '@/types/agentState';
import type {
  QualityGateStatus as QualityGateStatusType,
  GateTypeE2E,
  QualityGateStatusValue,
  GateTypeBackend,
} from '@/types/qualityGates';
import { fetchQualityGateStatus } from '@/api/qualityGates';
import QualityGateStatus from './QualityGateStatus';
import GateStatusIndicator from './GateStatusIndicator';

interface QualityGatesPanelProps {
  projectId: number;
  tasks: Task[];
}

/**
 * Get individual gate status from quality gate status response
 */
function getGateStatus(
  status: QualityGateStatusType | null,
  gateType: GateTypeE2E
): QualityGateStatusValue {
  if (!status) {
    return null;
  }

  // Map E2E type to backend type for lookup
  const backendTypes: Record<GateTypeE2E, GateTypeBackend> = {
    'tests': 'tests',
    'coverage': 'coverage',
    'type-check': 'type_check',
    'lint': 'linting',
    'review': 'code_review',
  };
  const backendType = backendTypes[gateType];

  // Check if this gate has failures
  const hasFailure = status.failures.some(f => f.gate === backendType);

  if (hasFailure) {
    return 'failed';
  }

  // If overall status is passed and no failures, gate passed
  if (status.status === 'passed') {
    return 'passed';
  }

  // Otherwise, inherit overall status
  return status.status;
}

/**
 * QualityGatesPanel Component
 *
 * Main panel for quality gates with task selection and gate overview
 */
export default function QualityGatesPanel({
  projectId: _projectId,
  tasks,
}: QualityGatesPanelProps) {
  const [selectedTaskId, setSelectedTaskId] = useState<number | null>(null);
  const [gateStatus, setGateStatus] = useState<QualityGateStatusType | null>(null);
  const [loading, setLoading] = useState(false);

  // Filter tasks that are completed or in_progress (candidates for quality gates)
  const eligibleTasks = useMemo(() => {
    return tasks.filter(t => t.status === 'completed' || t.status === 'in_progress');
  }, [tasks]);

  // Auto-select first eligible task if none selected
  useEffect(() => {
    if (eligibleTasks.length > 0 && selectedTaskId === null) {
      setSelectedTaskId(eligibleTasks[0].id);
    }
  }, [eligibleTasks, selectedTaskId]);

  // Fetch quality gate status when task is selected
  useEffect(() => {
    if (selectedTaskId === null) {
      setGateStatus(null);
      return;
    }

    async function fetchStatus() {
      setLoading(true);
      try {
        const status = await fetchQualityGateStatus(selectedTaskId!);
        setGateStatus(status);
      } catch (err) {
        console.error('Failed to fetch quality gate status:', err);
        setGateStatus(null);
      } finally {
        setLoading(false);
      }
    }

    fetchStatus();
  }, [selectedTaskId]);

  // All gate types in order
  const gateTypes: GateTypeE2E[] = ['tests', 'coverage', 'type-check', 'lint', 'review'];

  // No eligible tasks
  if (eligibleTasks.length === 0) {
    return (
      <div className="p-4 bg-gray-50 rounded-lg border border-gray-200">
        <div className="flex items-center gap-2 text-gray-600">
          <span>ℹ️</span>
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
        >
          {eligibleTasks.map(task => (
            <option key={task.id} value={task.id}>
              Task #{task.id}: {task.title}
            </option>
          ))}
        </select>
      </div>

      {/* Gate Status Indicators Grid */}
      {loading ? (
        <div className="flex items-center justify-center p-8">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
          <span className="ml-3 text-sm text-gray-600">Loading quality gates...</span>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
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
