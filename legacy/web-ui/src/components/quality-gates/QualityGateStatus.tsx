/**
 * QualityGateStatus Component (T066)
 *
 * Displays quality gate status for a task, including:
 * - Overall status (pending, running, passed, failed)
 * - List of failures with gate type, reason, severity
 * - Color coding by status
 * - Manual trigger button
 * - Progress indicator for running state
 * - Human approval badge if required
 */

'use client';

import { useState, useEffect, useCallback } from 'react';
import type {
  QualityGateStatus as QualityGateStatusType,
  QualityGateFailure,
} from '@/types/qualityGates';
import { fetchQualityGateStatus, triggerQualityGates } from '@/api/qualityGates';
import { getStatusClasses, getSeverityClasses, getGateIcon, getStatusIcon } from '@/lib/qualityGateUtils';
import {
  Alert02Icon,
  Settings01Icon,
  UserIcon,
  RefreshIcon,
  Cancel01Icon,
  CheckmarkCircle01Icon,
} from '@hugeicons/react';

interface QualityGateStatusProps {
  taskId: number;
  autoRefresh?: boolean;
  refreshInterval?: number; // milliseconds
}

/**
 * QualityGateStatus Component
 *
 * Displays quality gate evaluation status for a task with real-time updates
 */
export default function QualityGateStatus({
  taskId,
  autoRefresh = true,
  refreshInterval = 5000,
}: QualityGateStatusProps) {
  const [status, setStatus] = useState<QualityGateStatusType | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [triggering, setTriggering] = useState<boolean>(false);
  const [warningDismissed, setWarningDismissed] = useState<boolean>(false);

  // Fetch quality gate status
  const fetchStatus = useCallback(async () => {
    try {
      setError(null);
      const result = await fetchQualityGateStatus(taskId);
      setStatus(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch quality gate status');
    } finally {
      setLoading(false);
    }
  }, [taskId]);

  // Initial fetch
  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  // Check localStorage for warning dismissal state on mount
  useEffect(() => {
    const storageKey = `qualityGates_warning_dismissed_${taskId}`;
    const dismissed = localStorage.getItem(storageKey);
    if (dismissed) {
      try {
        setWarningDismissed(JSON.parse(dismissed));
      } catch {
        // If parsing fails, set to false
        setWarningDismissed(false);
      }
    } else {
      // No stored value, reset to false for this task
      setWarningDismissed(false);
    }
  }, [taskId]);

  // Dismiss warning banner
  const dismissWarning = () => {
    const storageKey = `qualityGates_warning_dismissed_${taskId}`;
    setWarningDismissed(true);
    localStorage.setItem(storageKey, JSON.stringify(true));
  };

  // Auto-refresh when status is 'running'
  useEffect(() => {
    if (!autoRefresh || !status || status.status !== 'running') {
      return;
    }

    const intervalId = setInterval(fetchStatus, refreshInterval);
    return () => clearInterval(intervalId);
  }, [autoRefresh, status, refreshInterval, fetchStatus]);

  // Handle manual trigger
  const handleTrigger = async () => {
    setTriggering(true);
    setError(null);

    try {
      await triggerQualityGates({ task_id: taskId });
      // Refresh status after triggering
      await fetchStatus();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to trigger quality gates');
    } finally {
      setTriggering(false);
    }
  };

  // Loading state
  if (loading) {
    return (
      <div className="flex items-center justify-center p-4 bg-muted rounded-lg border border-border">
        <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-primary"></div>
        <span className="ml-3 text-sm text-muted-foreground">Loading quality gate status...</span>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="p-4 bg-destructive/10 rounded-lg border border-destructive">
        <div className="flex items-start">
          <Alert02Icon className="h-5 w-5 text-destructive mr-2 flex-shrink-0" aria-hidden="true" />
          <div className="flex-1">
            <h4 className="text-sm font-medium text-destructive">Error Loading Quality Gates</h4>
            <p className="text-sm text-destructive mt-1">{error}</p>
          </div>
        </div>
      </div>
    );
  }

  // No status available
  if (!status) {
    return (
      <div className="p-4 bg-muted rounded-lg border border-border">
        <div className="flex items-center justify-between">
          <div className="flex items-center">
            <Settings01Icon className="h-5 w-5 text-muted-foreground mr-2" aria-hidden="true" />
            <span className="text-sm text-muted-foreground">No quality gate results yet</span>
          </div>
          <button
            onClick={handleTrigger}
            disabled={triggering}
            className="px-3 py-1.5 text-sm font-medium text-primary-foreground bg-primary hover:bg-primary/90 disabled:bg-muted disabled:text-muted-foreground rounded-md transition-colors"
          >
            {triggering ? 'Running...' : 'Run Quality Gates'}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {/* Status Header */}
      <div className="flex items-center justify-between p-4 bg-card rounded-lg border border-border shadow-sm">
        <div className="flex items-center gap-3">
          {getStatusIcon(status.status)}
          <div>
            <div className="flex items-center gap-2">
              <h4 className="text-sm font-semibold text-foreground">Quality Gate Status</h4>
              <span
                className={`px-2 py-0.5 text-xs font-medium rounded-full border ${getStatusClasses(
                  status.status
                )}`}
              >
                {status.status || 'unknown'}
              </span>
              {status.requires_human_approval && (
                <span className="px-2 py-0.5 text-xs font-medium rounded-full bg-accent text-accent-foreground border border-accent inline-flex items-center gap-1">
                  <UserIcon className="h-3 w-3" aria-hidden="true" />
                  <span>Requires Approval</span>
                </span>
              )}
            </div>
            <p className="text-xs text-muted-foreground mt-0.5">
              Last updated: {new Date(status.timestamp).toLocaleString()}
            </p>
          </div>
        </div>

        {/* Manual Trigger Button */}
        <button
          onClick={handleTrigger}
          disabled={triggering || status.status === 'running'}
          className="px-3 py-1.5 text-sm font-medium text-primary-foreground bg-primary hover:bg-primary/90 disabled:bg-muted disabled:text-muted-foreground rounded-md transition-colors flex items-center gap-1"
          title="Re-run quality gates"
        >
          {triggering ? (
            <>
              <div className="animate-spin rounded-full h-3 w-3 border-b-2 border-primary-foreground"></div>
              <span>Running...</span>
            </>
          ) : (
            <>
              <RefreshIcon className="h-4 w-4" aria-hidden="true" />
              <span>Re-run</span>
            </>
          )}
        </button>
      </div>

      {/* Warning Banner */}
      {status.status === 'passed' &&
       (!status.failures || status.failures.length === 0) &&
       !warningDismissed && (
        <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
          <div className="flex items-start gap-3">
            <Alert02Icon className="h-5 w-5 text-yellow-600 flex-shrink-0" aria-hidden="true" />
            <div className="flex-1 min-w-0">
              <h4 className="text-sm font-bold text-yellow-900">Summary Status Only</h4>
              <p className="text-sm text-yellow-800 mt-1">
                This shows overall status. Individual gates may not have been evaluated yet.
              </p>
            </div>
            <button
              onClick={dismissWarning}
              className="text-yellow-600 hover:text-yellow-800 font-bold text-xl flex-shrink-0 ml-2"
              aria-label="Dismiss warning"
            >
              ×
            </button>
          </div>
        </div>
      )}

      {/* Running Progress Indicator */}
      {status.status === 'running' && (
        <div className="p-3 bg-yellow-50 rounded-lg border border-yellow-200">
          <div className="flex items-center gap-2">
            <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-yellow-600"></div>
            <span className="text-sm text-yellow-800 font-medium">
              Quality gates are running... Checking automatically every {refreshInterval / 1000}s
            </span>
          </div>
          <div className="mt-2 w-full bg-yellow-200 rounded-full h-1.5">
            <div className="bg-yellow-600 h-1.5 rounded-full animate-pulse" style={{ width: '100%' }}></div>
          </div>
        </div>
      )}

      {/* Failures List */}
      {status.failures && status.failures.length > 0 && (
        <div className="p-4 bg-card rounded-lg border border-border shadow-sm">
          <h5 className="text-sm font-semibold text-foreground mb-3 flex items-center gap-2">
            <Cancel01Icon className="h-4 w-4 text-destructive" aria-hidden="true" />
            <span>Quality Gate Failures ({status.failures.length})</span>
          </h5>
          <div className="space-y-2">
            {status.failures.map((failure: QualityGateFailure, index: number) => (
              <div
                key={index}
                className="p-3 bg-destructive/10 rounded-md border border-destructive"
              >
                <div className="flex items-start gap-2">
                  <span className="text-lg flex-shrink-0">{getGateIcon(failure.gate)}</span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-sm font-medium text-foreground capitalize">
                        {failure.gate.replace('_', ' ')}
                      </span>
                      <span
                        className={`px-2 py-0.5 text-xs font-medium rounded-full border ${getSeverityClasses(
                          failure.severity
                        )}`}
                      >
                        {failure.severity}
                      </span>
                    </div>
                    <p className="text-sm text-destructive">{failure.reason}</p>
                    {failure.details && (
                      <p className="text-xs text-destructive mt-1 font-mono bg-destructive/10 p-2 rounded border border-destructive">
                        {failure.details}
                      </p>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Success Message */}
      {status.status === 'passed' && (!status.failures || status.failures.length === 0) && (
        <div className="p-4 bg-green-50 rounded-lg border border-green-200">
          <div className="flex items-center gap-2">
            <CheckmarkCircle01Icon className="h-5 w-5 text-green-600" aria-hidden="true" />
            <span className="text-sm text-green-800 font-medium">
              All quality gates passed! Ready for deployment.
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
