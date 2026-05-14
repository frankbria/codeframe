'use client';

import { useEffect, useState } from 'react';
import useSWR from 'swr';
import {
  MoneyBag02Icon,
  Task01Icon,
  Analytics01Icon,
} from '@hugeicons/react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { SpendBarChart } from '@/components/costs/SpendBarChart';
import { TopTasksTable } from '@/components/costs/TopTasksTable';
import { AgentCostBars } from '@/components/costs/AgentCostBars';
import { WorkspaceSelector } from '@/components/workspace/WorkspaceSelector';
import { costsApi, workspaceApi } from '@/lib/api';
import {
  getSelectedWorkspacePath,
  setSelectedWorkspacePath,
} from '@/lib/workspace-storage';
import type {
  CostSummaryResponse,
  TaskCostsResponse,
  AgentCostsResponse,
  ApiError,
} from '@/types';

const DAY_OPTIONS = [
  { value: 7, label: 'Last 7 days' },
  { value: 30, label: 'Last 30 days' },
  { value: 90, label: 'Last 90 days' },
];

function formatCurrency(value: number, fractionDigits = 4): string {
  return value.toLocaleString('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  });
}

export default function CostsPage() {
  const [workspacePath, setWorkspacePath] = useState<string | null>(null);
  const [days, setDays] = useState<number>(30);
  const [isSelecting, setIsSelecting] = useState(false);
  const [selectionError, setSelectionError] = useState<string | null>(null);

  useEffect(() => {
    setWorkspacePath(getSelectedWorkspacePath());
  }, []);

  const { data, error, isLoading } = useSWR<CostSummaryResponse, ApiError>(
    workspacePath ? ['/api/v2/costs/summary', workspacePath, days] : null,
    () => costsApi.getSummary(workspacePath!, days),
    { refreshInterval: 60000 }
  );

  const { data: tasksData, isLoading: tasksLoading } = useSWR<TaskCostsResponse, ApiError>(
    workspacePath ? ['/api/v2/costs/tasks', workspacePath, days] : null,
    () => costsApi.getTopTasks(workspacePath!, days),
    { refreshInterval: 60000 }
  );

  const { data: agentsData, isLoading: agentsLoading } = useSWR<AgentCostsResponse, ApiError>(
    workspacePath ? ['/api/v2/costs/by-agent', workspacePath, days] : null,
    () => costsApi.getByAgent(workspacePath!, days),
    { refreshInterval: 60000 }
  );

  const handleSelectWorkspace = async (path: string) => {
    setIsSelecting(true);
    setSelectionError(null);
    try {
      const exists = await workspaceApi.checkExists(path);
      if (!exists.exists) {
        await workspaceApi.init(path, { detect: true });
      }
      setSelectedWorkspacePath(path);
      setWorkspacePath(path);
    } catch (err) {
      const apiError = err as ApiError;
      setSelectionError(apiError.detail || 'Failed to open project');
    } finally {
      setIsSelecting(false);
    }
  };

  if (!workspacePath) {
    return (
      <WorkspaceSelector
        onSelectWorkspace={handleSelectWorkspace}
        isLoading={isSelecting}
        error={selectionError}
      />
    );
  }

  return (
    <main className="min-h-screen bg-background">
      <div className="mx-auto max-w-7xl px-4 py-8">
        <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold">Costs</h1>
            <p className="text-sm text-muted-foreground">
              Total AI spend across this workspace.
            </p>
          </div>

          <label className="flex items-center gap-2 text-sm">
            <span className="text-muted-foreground">Time range:</span>
            <select
              aria-label="Time range"
              data-testid="time-range-select"
              value={days}
              onChange={(e) => setDays(Number(e.target.value))}
              className="rounded-md border bg-background px-2 py-1 text-sm shadow-sm"
            >
              {DAY_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </label>
        </div>

        {error && (
          <div
            data-testid="costs-error"
            className="mb-4 rounded-md border border-destructive bg-destructive/10 p-4 text-sm text-destructive"
          >
            {error.detail || 'Failed to load cost summary.'}
          </div>
        )}

        {isLoading && !data ? (
          <div data-testid="costs-loading" className="animate-pulse">
            <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
              <div className="h-28 rounded-xl bg-muted" />
              <div className="h-28 rounded-xl bg-muted" />
              <div className="h-28 rounded-xl bg-muted" />
            </div>
            <div className="mt-6 h-56 rounded-xl bg-muted" />
          </div>
        ) : data ? (
          <>
            <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
              <Card>
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                  <CardTitle className="text-sm font-medium">Total Spend</CardTitle>
                  <MoneyBag02Icon className="h-4 w-4 text-muted-foreground" />
                </CardHeader>
                <CardContent>
                  <p
                    data-testid="total-spend"
                    className="text-2xl font-bold"
                  >
                    {formatCurrency(data.total_spend_usd)}
                  </p>
                </CardContent>
              </Card>

              <Card>
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                  <CardTitle className="text-sm font-medium">Tasks Run</CardTitle>
                  <Task01Icon className="h-4 w-4 text-muted-foreground" />
                </CardHeader>
                <CardContent>
                  <p
                    data-testid="total-tasks"
                    className="text-2xl font-bold"
                  >
                    {data.total_tasks.toLocaleString('en-US')}
                  </p>
                </CardContent>
              </Card>

              <Card>
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                  <CardTitle className="text-sm font-medium">Avg Cost / Task</CardTitle>
                  <Analytics01Icon className="h-4 w-4 text-muted-foreground" />
                </CardHeader>
                <CardContent>
                  <p
                    data-testid="avg-cost"
                    className="text-2xl font-bold"
                  >
                    {formatCurrency(data.avg_cost_per_task)}
                  </p>
                </CardContent>
              </Card>
            </div>

            <div className="mt-6">
              <SpendBarChart daily={data.daily} days={days} />
            </div>

            <section className="mt-8" aria-labelledby="top-tasks-heading">
              <div className="mb-3 flex items-center justify-between">
                <h2 id="top-tasks-heading" className="text-lg font-semibold">
                  Top tasks by cost
                </h2>
                <p className="text-xs text-muted-foreground">
                  Top 10 over the selected window
                </p>
              </div>
              <TopTasksTable
                tasks={tasksData?.tasks ?? []}
                isLoading={tasksLoading && !tasksData}
              />
            </section>

            <section className="mt-8" aria-labelledby="by-agent-heading">
              <div className="mb-3 flex items-center justify-between">
                <h2 id="by-agent-heading" className="text-lg font-semibold">
                  Cost by agent
                </h2>
                <p className="text-xs text-muted-foreground">
                  Spend grouped by agent over the selected window
                </p>
              </div>
              <AgentCostBars
                data={
                  agentsData ?? {
                    by_agent: [],
                    total_input_tokens: 0,
                    total_output_tokens: 0,
                  }
                }
                isLoading={agentsLoading && !agentsData}
              />
            </section>
          </>
        ) : null}
      </div>
    </main>
  );
}
