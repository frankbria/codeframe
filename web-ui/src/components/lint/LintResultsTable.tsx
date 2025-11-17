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
