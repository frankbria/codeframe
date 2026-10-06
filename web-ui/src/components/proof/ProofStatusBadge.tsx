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
  /** WAIVED past the waiver's expiry: the merge gate blocks on it (#1276, #1360). */
  waiverExpired?: boolean;
}

export function ProofStatusBadge({ status, waiverExpired = false }: ProofStatusBadgeProps) {
  if (status === 'waived' && waiverExpired) {
    return <Badge variant={PROOF_STATUS_VARIANT.open}>waiver expired</Badge>;
  }
  return <Badge variant={PROOF_STATUS_VARIANT[status]}>{status}</Badge>;
}
