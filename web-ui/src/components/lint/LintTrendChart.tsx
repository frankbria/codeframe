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
