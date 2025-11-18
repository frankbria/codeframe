# Frontend Integration Guide (T119-T124)

This document provides specifications for WebSocket events and frontend components for lint integration.

## T119: WebSocket Events

Add to `/codeframe/ui/websocket_broadcasts.py`:

```python
async def broadcast_lint_started(project_id: int, task_id: int):
    """Broadcast that linting has started for a task."""
    await broadcast_to_project(
        project_id,
        {
            "event": "lint_started",
            "timestamp": datetime.now().isoformat(),
            "task_id": task_id,
        }
    )

async def broadcast_lint_completed(
    project_id: int,
    task_id: int,
    results: list[dict],
    has_errors: bool
):
    """Broadcast that linting has completed."""
    total_errors = sum(r["error_count"] for r in results)
    total_warnings = sum(r["warning_count"] for r in results)

    await broadcast_to_project(
        project_id,
        {
            "event": "lint_completed",
            "timestamp": datetime.now().isoformat(),
            "task_id": task_id,
            "has_errors": has_errors,
            "total_errors": total_errors,
            "total_warnings": total_warnings,
            "linters": [r["linter"] for r in results],
        }
    )

async def broadcast_lint_failed(project_id: int, task_id: int, error: str):
    """Broadcast that linting failed with an error."""
    await broadcast_to_project(
        project_id,
        {
            "event": "lint_failed",
            "timestamp": datetime.now().isoformat(),
            "task_id": task_id,
            "error": error,
        }
    )
```

Update `/api/lint/run` endpoint to use broadcasts:

```python
# In server.py, POST /api/lint/run
await broadcast_lint_started(project_id, task_id)

try:
    results = await lint_runner.run_lint(file_paths)
    # ... store results ...

    await broadcast_lint_completed(
        project_id,
        task_id,
        [
            {
                "linter": r.linter,
                "error_count": r.error_count,
                "warning_count": r.warning_count,
            }
            for r in results
        ],
        has_errors=lint_runner.has_critical_errors(results)
    )
except Exception as e:
    await broadcast_lint_failed(project_id, task_id, str(e))
    raise
```

## T120-T121: Frontend Components (TypeScript)

### Types (`web-ui/src/types/lint.ts`)

```typescript
export interface LintResult {
  id: number;
  task_id: number;
  linter: 'ruff' | 'eslint' | 'other';
  error_count: number;
  warning_count: number;
  files_linted: number;
  output: string;
  created_at: string;
}

export interface LintTrendEntry {
  date: string;
  linter: string;
  error_count: number;
  warning_count: number;
}

export interface LintConfig {
  project_id: number;
  config: Record<string, any>;
  has_ruff_config: boolean;
  has_eslint_config: boolean;
}
```

### API Client (`web-ui/src/api/lint.ts`)

```typescript
// T122: Lint API client
import axios from 'axios';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export const lintApi = {
  // Get lint results for task
  getResults: async (taskId: number): Promise<{ task_id: number; results: LintResult[] }> => {
    const response = await axios.get(`${API_BASE}/api/lint/results`, {
      params: { task_id: taskId }
    });
    return response.data;
  },

  // Get lint trend
  getTrend: async (projectId: number, days: number = 7): Promise<{
    project_id: number;
    days: number;
    trend: LintTrendEntry[];
  }> => {
    const response = await axios.get(`${API_BASE}/api/lint/trend`, {
      params: { project_id: projectId, days }
    });
    return response.data;
  },

  // Get lint config
  getConfig: async (projectId: number): Promise<LintConfig> => {
    const response = await axios.get(`${API_BASE}/api/lint/config`, {
      params: { project_id: projectId }
    });
    return response.data;
  },

  // Run manual lint
  runLint: async (projectId: number, taskId?: number, files?: string[]): Promise<{
    status: string;
    has_errors: boolean;
    results: Array<{
      linter: string;
      error_count: number;
      warning_count: number;
      files_linted: number;
    }>;
  }> => {
    const response = await axios.post(`${API_BASE}/api/lint/run`, {
      project_id: projectId,
      task_id: taskId,
      files
    });
    return response.data;
  }
};
```

### LintTrendChart Component (`web-ui/src/components/lint/LintTrendChart.tsx`)

```typescript
// T120: Lint trend chart component
import React, { useEffect, useState } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { lintApi } from '@/api/lint';
import type { LintTrendEntry } from '@/types/lint';

interface LintTrendChartProps {
  projectId: number;
  days?: number;
  refreshInterval?: number; // ms, 0 = no auto-refresh
}

export const LintTrendChart: React.FC<LintTrendChartProps> = ({
  projectId,
  days = 7,
  refreshInterval = 0
}) => {
  const [data, setData] = useState<LintTrendEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = async () => {
    try {
      setLoading(true);
      const response = await lintApi.getTrend(projectId, days);
      setData(response.trend);
      setError(null);
    } catch (err) {
      setError('Failed to load lint trend data');
      console.error('Lint trend error:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();

    if (refreshInterval > 0) {
      const interval = setInterval(fetchData, refreshInterval);
      return () => clearInterval(interval);
    }
  }, [projectId, days, refreshInterval]);

  if (loading && data.length === 0) {
    return <div className="p-4 text-center">Loading lint trend...</div>;
  }

  if (error) {
    return <div className="p-4 text-red-500">{error}</div>;
  }

  if (data.length === 0) {
    return <div className="p-4 text-gray-500">No lint data available</div>;
  }

  return (
    <div className="p-4 bg-white rounded-lg shadow">
      <h3 className="text-lg font-semibold mb-4">Lint Quality Trend (Last {days} days)</h3>
      <ResponsiveContainer width="100%" height={300}>
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="date" />
          <YAxis />
          <Tooltip />
          <Legend />
          <Line
            type="monotone"
            dataKey="error_count"
            stroke="#ef4444"
            name="Errors"
            strokeWidth={2}
          />
          <Line
            type="monotone"
            dataKey="warning_count"
            stroke="#f59e0b"
            name="Warnings"
            strokeWidth={2}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
};
```

### LintResultsTable Component (`web-ui/src/components/lint/LintResultsTable.tsx`)

```typescript
// T121: Lint results table component
import React, { useEffect, useState } from 'react';
import { lintApi } from '@/api/lint';
import type { LintResult } from '@/types/lint';

interface LintResultsTableProps {
  taskId: number;
}

export const LintResultsTable: React.FC<LintResultsTableProps> = ({ taskId }) => {
  const [results, setResults] = useState<LintResult[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchResults = async () => {
      try {
        const response = await lintApi.getResults(taskId);
        setResults(response.results);
      } catch (err) {
        console.error('Failed to load lint results:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchResults();
  }, [taskId]);

  if (loading) {
    return <div>Loading...</div>;
  }

  if (results.length === 0) {
    return <div className="text-gray-500">No lint results for this task</div>;
  }

  return (
    <div className="overflow-x-auto">
      <table className="min-w-full divide-y divide-gray-200">
        <thead className="bg-gray-50">
          <tr>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
              Linter
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
              Errors
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
              Warnings
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
              Files
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">
              Time
            </th>
          </tr>
        </thead>
        <tbody className="bg-white divide-y divide-gray-200">
          {results.map((result) => (
            <tr key={result.id}>
              <td className="px-6 py-4 whitespace-nowrap">
                <span className="px-2 py-1 text-xs font-semibold rounded bg-blue-100 text-blue-800">
                  {result.linter}
                </span>
              </td>
              <td className="px-6 py-4 whitespace-nowrap">
                <span
                  className={`font-semibold ${
                    result.error_count > 0 ? 'text-red-600' : 'text-green-600'
                  }`}
                >
                  {result.error_count}
                </span>
              </td>
              <td className="px-6 py-4 whitespace-nowrap">
                <span
                  className={`font-semibold ${
                    result.warning_count > 0 ? 'text-yellow-600' : 'text-gray-400'
                  }`}
                >
                  {result.warning_count}
                </span>
              </td>
              <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                {result.files_linted}
              </td>
              <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                {new Date(result.created_at).toLocaleString()}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};
```

## T124: Dashboard Integration

Add to `web-ui/src/components/Dashboard.tsx`:

```typescript
import { LintTrendChart } from './lint/LintTrendChart';

// In Dashboard component render:
<div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
  {/* Existing charts... */}

  {/* Lint Quality Trend */}
  <div className="col-span-1">
    <LintTrendChart
      projectId={currentProjectId}
      days={7}
      refreshInterval={30000} // Refresh every 30 seconds
    />
  </div>
</div>
```

## T123: TypeScript Types Summary

All types consolidated in `web-ui/src/types/lint.ts` as shown above.

## WebSocket Event Handling

Add to Dashboard's WebSocket event handler:

```typescript
useEffect(() => {
  const ws = new WebSocket(WEBSOCKET_URL);

  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);

    switch (data.event) {
      case 'lint_started':
        console.log(`Linting started for task ${data.task_id}`);
        // Show spinner or status indicator
        break;

      case 'lint_completed':
        console.log(`Linting completed: ${data.total_errors} errors, ${data.total_warnings} warnings`);
        // Refresh lint trend chart
        setRefreshTrigger(Date.now());

        // Show notification if has errors
        if (data.has_errors) {
          showNotification('error', `Linting found ${data.total_errors} errors`);
        }
        break;

      case 'lint_failed':
        console.error(`Linting failed: ${data.error}`);
        showNotification('error', 'Linting failed');
        break;
    }
  };

  return () => ws.close();
}, []);
```

## Testing

### Unit Tests

```typescript
// web-ui/__tests__/components/LintTrendChart.test.tsx
import { render, screen, waitFor } from '@testing-library/react';
import { LintTrendChart } from '@/components/lint/LintTrendChart';
import { lintApi } from '@/api/lint';

jest.mock('@/api/lint');

describe('LintTrendChart', () => {
  it('renders trend data correctly', async () => {
    const mockData = {
      project_id: 1,
      days: 7,
      trend: [
        { date: '2025-11-15', linter: 'ruff', error_count: 5, warning_count: 10 },
        { date: '2025-11-16', linter: 'ruff', error_count: 3, warning_count: 8 },
      ]
    };

    (lintApi.getTrend as jest.Mock).mockResolvedValue(mockData);

    render(<LintTrendChart projectId={1} days={7} />);

    await waitFor(() => {
      expect(screen.getByText(/Lint Quality Trend/i)).toBeInTheDocument();
    });
  });
});
```

## Implementation Order

1. ✅ Backend APIs (T115-T118) - **COMPLETE**
2. Create WebSocket events (T119)
3. Create TypeScript types (T123)
4. Create API client (T122)
5. Create LintTrendChart (T120)
6. Create LintResultsTable (T121)
7. Integrate into Dashboard (T124)
8. Write frontend tests

## Next Steps

The backend implementation is complete and tested. To complete the frontend:

1. Copy type definitions to `web-ui/src/types/lint.ts`
2. Copy API client to `web-ui/src/api/lint.ts`
3. Copy components to `web-ui/src/components/lint/`
4. Add WebSocket event handlers to `codeframe/ui/websocket_broadcasts.py`
5. Integrate LintTrendChart into Dashboard
6. Write unit tests for frontend components
