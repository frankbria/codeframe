/**
 * The restored PR panel must show THIS branch's PR (#944).
 *
 * Raised as a major on the PR: the first cut took `pull_requests[0]` — the
 * newest open PR in the connected repo, not this workspace's branch. With more
 * than one open PR (several feature branches, dependabot, a stale one), the
 * panel restored the wrong PR, and its Merge button — the only merge surface in
 * the web UI — would then merge it.
 */
import { pickOpenPr } from '@/lib/pickOpenPr';
import type { PRResponse } from '@/types';

const pr = (number: number, head_branch: string): PRResponse =>
  ({
    number,
    head_branch,
    url: `https://github.com/o/r/pull/${number}`,
    state: 'open',
    title: `PR ${number}`,
    body: null,
    created_at: '2026-01-01T00:00:00Z',
    merged_at: null,
    base_branch: 'main',
  }) as PRResponse;

// Newest first, as the API returns them. #99 is somebody else's.
const OPEN = [pr(99, 'dependabot/npm/lodash'), pr(42, 'fix/944-web-ui-defects')];

describe('pickOpenPr (#944)', () => {
  it('picks the PR whose head is the current branch, not the newest', () => {
    expect(pickOpenPr(OPEN, 'fix/944-web-ui-defects')?.number).toBe(42);
  });

  it('does not return the newest PR when it belongs to another branch', () => {
    // The exact failure: merging #99 from a page showing #42's diff.
    expect(pickOpenPr(OPEN, 'fix/944-web-ui-defects')?.number).not.toBe(99);
  });

  it('returns nothing when this branch has no open PR', () => {
    expect(pickOpenPr(OPEN, 'fix/some-other-work')).toBeUndefined();
  });

  it('returns nothing on a detached HEAD rather than guessing', () => {
    expect(pickOpenPr(OPEN, undefined)).toBeUndefined();
    expect(pickOpenPr(OPEN, '')).toBeUndefined();
  });

  it('tolerates a missing list', () => {
    expect(pickOpenPr(undefined, 'main')).toBeUndefined();
  });

  it('still works when the branch has the only open PR', () => {
    expect(pickOpenPr([pr(7, 'main')], 'main')?.number).toBe(7);
  });

  it('matches exactly, not by prefix', () => {
    // 'fix/944' must not claim 'fix/944-web-ui-defects'.
    expect(pickOpenPr(OPEN, 'fix/944')).toBeUndefined();
  });
});
