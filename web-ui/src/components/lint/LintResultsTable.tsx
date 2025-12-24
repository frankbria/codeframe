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
    return <div className="text-muted-foreground">No lint results for this task</div>;
  }

  return (
    <div className="overflow-x-auto">
      <table className="min-w-full divide-y divide-border">
        <thead className="bg-muted">
          <tr>
            <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase">
              Linter
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase">
              Errors
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase">
              Warnings
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase">
              Files
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase">
              Time
            </th>
          </tr>
        </thead>
        <tbody className="bg-card divide-y divide-border">
          {results.map((result) => (
            <tr key={result.id}>
              <td className="px-6 py-4 whitespace-nowrap">
                <span className="px-2 py-1 text-xs font-semibold rounded bg-primary/10 text-primary">
                  {result.linter}
                </span>
              </td>
              <td className="px-6 py-4 whitespace-nowrap">
                <span
                  className={`font-semibold ${
                    result.error_count > 0 ? 'text-destructive' : 'text-secondary'
                  }`}
                >
                  {result.error_count}
                </span>
              </td>
              <td className="px-6 py-4 whitespace-nowrap">
                <span
                  className={`font-semibold ${
                    result.warning_count > 0 ? 'text-yellow-600' : 'text-muted-foreground'
                  }`}
                >
                  {result.warning_count}
                </span>
              </td>
              <td className="px-6 py-4 whitespace-nowrap text-sm text-muted-foreground">
                {result.files_linted}
              </td>
              <td className="px-6 py-4 whitespace-nowrap text-sm text-muted-foreground">
                {new Date(result.created_at).toLocaleString()}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};
