'use client';

import { Badge, type BadgeVariant } from '@/components/ui/badge';
import type { ProofReqStatus } from '@/types';

/** Requirement status → shared badge variant, so proof badges restyle with every other status badge. */
export const PROOF_STATUS_VARIANT: Record<ProofReqStatus, BadgeVariant> = {
  open: 'blocked',
  satisfied: 'done',
  waived: 'backlog',
};

interface ProofStatusBadgeProps {
  status: ProofReqStatus;
}

export function ProofStatusBadge({ status }: ProofStatusBadgeProps) {
  return <Badge variant={PROOF_STATUS_VARIANT[status]}>{status}</Badge>;
}
