import type { PRResponse } from '@/types';

/**
 * The open PR for `branch`, or undefined (#944).
 *
 * `/review` restores its PR panel on load by listing open PRs. The first cut
 * took `pull_requests[0]` — the newest open PR in the whole repo. With several
 * feature branches, a dependabot PR, or a stale one, that restores someone
 * else's PR, and the panel's Merge button then merges it.
 *
 * A falsy branch (detached HEAD) matches nothing on purpose: a hidden panel
 * beats an arbitrary PR.
 */
export function pickOpenPr(
  prs: PRResponse[] | undefined,
  branch: string | undefined
): PRResponse | undefined {
  if (!branch) return undefined;
  return prs?.find((pr) => pr.head_branch === branch);
}
