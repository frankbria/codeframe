import { describe, expect, test } from 'claude-code/testing'

import { isGitCommit } from '../hooks/commit.ts'

describe('a commit is detected wherever git runs it', () => {
  for (const command of [
    'git commit -m x',
    'git  commit -m x',
    'git commit --amend --no-edit',
    'git add -A&&git commit -am wip',
    'npm test; git commit -m x',
    'npm test\ngit commit -m x',
    '(cd sub && git commit -m x)',
    'echo $(git commit -m x)',
    'git -C repo commit -m x',
    'git -C "dir with space" commit -m x',
    'git -c user.name="A B" commit -m x',
    'git -c user.name=t --no-pager commit -m x',
    'git --git-dir .git --work-tree . commit -m x',
    'git --git-dir=.git commit -m x',
    '/usr/bin/git commit -m x',
    'GIT_DIR=x git commit -m x',
    'GIT_AUTHOR_DATE="2026-01-01 00:00" git commit -m x',
    'env X=1 git commit -m x',
    'time git commit -m x',
    'sudo git commit -m x',
    '! git commit -m x',
    'if true; then git commit -m x; fi',
    '{ git commit -m x; }',
    'git \\\ncommit -m x',
    'git commit -F - <<EOF\nmessage; with separators && more\nEOF',
    'git >/dev/null commit -m x',
    'git 2>&1 commit -m x',
    'git 2> err.log commit -m x',
    'git commit -m x &>/dev/null',
    'if false; then :; elif git commit -m x; then :; fi',
  ]) {
    test(JSON.stringify(command), () => {
      expect(isGitCommit(command)).toBe(true)
    })
  }
})

describe('text that merely mentions a commit is not one', () => {
  for (const command of [
    'git status',
    'echo git commit',
    'echo "done; git commit later"',
    "grep '&& git commit' notes.md",
    'printf "%s\\n" "reverted fix; git commit later" >> notes.md',
    'git commit-tree HEAD^{tree}',
    'git log --grep commit',
    'git -C commit status',
    'cat > hook.sh <<EOF\ngit commit -m x\nEOF',
    "cat > hook.sh <<'END'\ngit commit -m x\nEND",
    'gh pr create --body "steps:\ngit commit -m x"',
    'git status > commit',
    'git log 2>&1 | grep commit',
    'ls',
    '',
  ]) {
    test(JSON.stringify(command), () => {
      expect(isGitCommit(command)).toBe(false)
    })
  }
})
