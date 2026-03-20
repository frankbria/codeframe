'use client';

import Link from 'next/link';
import useSWR from 'swr';
import { CheckmarkCircle01Icon } from '@hugeicons/react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { proofApi } from '@/lib/api';
import type { ProofStatusResponse } from '@/types';

interface ProofStatusWidgetProps {
  workspacePath: string;
}

export function ProofStatusWidget({ workspacePath }: ProofStatusWidgetProps) {
  const { data, isLoading } = useSWR<ProofStatusResponse>(
    `/api/v2/proof/status?path=${workspacePath}`,
    () => proofApi.getStatus(workspacePath),
    { refreshInterval: 30000 }
  );

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium">PROOF9 Status</CardTitle>
        <CheckmarkCircle01Icon className="h-4 w-4 text-muted-foreground" />
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="h-6 w-32 animate-pulse rounded bg-muted" />
        ) : !data || data.total === 0 ? (
          <p className="text-sm text-muted-foreground">No requirements captured yet</p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {data.open > 0 && (
              <Badge className="bg-red-100 text-red-900">{data.open} open</Badge>
            )}
            {data.satisfied > 0 && (
              <Badge className="bg-green-100 text-green-900">{data.satisfied} satisfied</Badge>
            )}
            {data.waived > 0 && (
              <Badge className="bg-gray-100 text-gray-600">{data.waived} waived</Badge>
            )}
          </div>
        )}
        {data && data.total > 0 && (
          <Link
            href="/proof"
            className="mt-2 inline-block text-sm text-primary hover:underline"
          >
            View all →
          </Link>
        )}
      </CardContent>
    </Card>
  );
}
