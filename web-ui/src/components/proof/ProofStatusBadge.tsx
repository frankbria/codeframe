'use client';

import { Badge } from '@/components/ui/badge';
import type { ProofReqStatus } from '@/types';

interface ProofStatusBadgeProps {
  status: ProofReqStatus;
}

export function ProofStatusBadge({ status }: ProofStatusBadgeProps) {
  const styles: Record<ProofReqStatus, string> = {
    open: 'bg-red-100 text-red-900',
    satisfied: 'bg-green-100 text-green-900',
    waived: 'bg-gray-100 text-gray-600',
  };

  return (
    <Badge className={styles[status]}>
      {status}
    </Badge>
  );
}
