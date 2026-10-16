import { describe, expect, test } from 'claude-code/testing'
import type { On, ToolCallResult } from 'claude-code'
import type { Engine } from 'claude-code/testing'

type Call = { argv: readonly string[]; timeoutMs?: number }
type Answer = { exitCode?: number; stdout?: string; stderr?: string } | { deny: string }

const FAILING_RUN = {
  run_id: 'r1', mode: 'scope', gate: null, passed: false, failed: true, vacuous: false,
  empty_reason: null, description: null,
  requirements: [
    {
      id: 'REQ-0003', title: 'Login 500s on an empty form', status_before: 'satisfied', status_after: 'open',
      gates: [{ gate: 'unit', outcome: 'failed', tests: ['test_unit_empty_form'] }],
    },
    {
      id: 'REQ-0004', title: 'Totals round correctly', status_before: 'open', status_after: 'satisfied',
      gates: [{ gate: 'unit', outcome: 'passed', tests: ['test_unit_totals'] }],
    },
  ],
}
const PASSING_RUN = { ...FAILING_RUN, passed: true, failed: false, requirements: [FAILING_RUN.requirements[1]] }
const EMPTY_LEDGER = {
  ...FAILING_RUN, passed: false, failed: false, requirements: [],
  empty_reason: 'no_requirements', description: 'the requirement ledger is empty',
}
const OUT_OF_SCOPE = {
  ...EMPTY_LEDGER, empty_reason: 'excluded_by_scope', description: 'all 2 requirement(s) are out of scope',
}
const VACUOUS = { ...PASSING_RUN, vacuous: true }
const listed = (failed: boolean[]) => ({
  requirements: failed.map((f, i) => ({
    id: `REQ-${i + 1}`, title: `r${i + 1}`, status: 'open', source: 'qa',
    obligations: [{ gate: 'unit', status: f ? 'failed' : 'satisfied' }],
    evidence_rules: [{ test_id: `test_unit_${i + 1}`, gate: 'unit', must_pass: true }],
  })),
})
const STATUS = listed([true, false])

const json = (doc: unknown, exitCode = 0): Answer => ({ exitCode, stdout: JSON.stringify(doc) })

function world(on: On, run: Answer, status: Answer = json(STATUS), opts: { commitFails?: boolean } = {}) {
  const calls: Call[] = []
  const toasts: string[] = []
  const statuses: (string | undefined)[] = []
  const commands: string[] = []
  on('process.run', (_$, e) => {
    calls.push({ argv: e.argv, timeoutMs: e.init?.timeoutMs })
    const a = e.argv[1] === 'proof' && e.argv[2] === 'run' ? run : e.argv[2] === 'list' ? status : json({})
    if ('deny' in a) return a
    return {
      value: {
        exitCode: a.exitCode ?? 0, stdout: a.stdout ?? '', stderr: a.stderr ?? '',
        isStdoutTruncated: false, isStderrTruncated: false,
      },
    }
  })
  on('ui.toast', (_$, e) => {
    toasts.push(e.text)
    return { value: undefined }
  })
  on('ui.status', (_$, e) => {
    statuses.push(e.text)
    return { value: undefined }
  })
  // The real Bash, beneath the plugin.
  on('tool.call', { tool: 'Bash' }, (_$, e) => {
    commands.push(e.command)
    if (opts.commitFails) return { isError: true, result: 'hook rejected', text: 'pre-commit hook failed' }
    return { result: { stdout: '[main abc123] msg', stderr: '', interrupted: false }, text: '[main abc123] msg' }
  })
  return { calls, toasts, statuses, commands }
}

const bash = ($: Engine, command: string): Promise<ToolCallResult> => $.tool.call({ tool: 'Bash', command })

const ranProof = (w: { calls: Call[] }) => w.calls.some(c => c.argv[1] === 'proof' && c.argv[2] === 'run')

describe('which commands are commits', () => {
  for (const command of [
    'git commit -m "x"',
    'git commit --amend --no-edit',
    'git add -A && git commit -am wip',
    'git -C repo commit -m x',
    'git -c user.name=t --no-pager commit -m x',
    'npm test; git commit -m x',
    '(cd sub && git commit -m x)',
  ]) {
    test(`runs proof before: ${command}`, async ($, on) => {
      const w = world(on, json(PASSING_RUN))
      await bash($, command)
      expect(ranProof(w)).toBe(true)
      expect(w.commands).toEqual([command])
    })
  }

  for (const command of ['git status', 'echo git commit', 'git commit-tree HEAD^{tree}', 'ls', 'git log --grep commit']) {
    test(`leaves alone: ${command}`, async ($, on) => {
      const w = world(on, json(FAILING_RUN, 1))
      const out = await bash($, command)
      expect(w.calls).toEqual([])
      expect(w.commands).toEqual([command])
      expect(out.context).toBeUndefined()
    })
  }
})

describe('warn mode (default)', () => {
  test('failing obligations warn the person, tell Claude, and the commit still runs', async ($, on) => {
    const w = world(on, json(FAILING_RUN, 1))
    const out = await bash($, 'git commit -m x')

    expect(w.commands).toEqual(['git commit -m x'])
    expect(out.deny).toBeUndefined()
    expect(w.toasts.some(t => t.includes('REQ-0003'))).toBe(true)
    // #1473: the person learns what broke, that Claude knows, and that the commit went ahead.
    const toast = w.toasts.find(t => t.includes('REQ-0003')) ?? ''
    expect(toast).toContain('Login 500s on an empty form')
    expect(toast).toMatch(/Claude/)
    expect(toast).toMatch(/went ahead/)
    const said = (out.context ?? []).join('\n')
    expect(said).toContain('REQ-0003')
    expect(said).toContain('Login 500s on an empty form')
    expect(said).toContain('test_unit_empty_form')
    expect(said).not.toContain('REQ-0004')
  })

  test('the run is plain `cf proof run --json`: working-tree scope, a superset of the commit', async ($, on) => {
    const w = world(on, json(PASSING_RUN))
    await bash($, 'git commit -m x')
    const run = w.calls.find(c => c.argv[2] === 'run')
    expect(run?.argv).toEqual(['cf', 'proof', 'run', '--json'])
    expect(run?.timeoutMs).toBe(120_000)
  })

  test('a pass is silent and refreshes the status line', async ($, on) => {
    const w = world(on, json(PASSING_RUN))
    const out = await bash($, 'git commit -m x')
    expect(w.toasts).toEqual([])
    expect(out.context).toBeUndefined()
    expect(w.statuses.at(-1)).toBe('2 requirements · 1 failing')
  })

  test('an empty ledger points at /proof and /proof ratchet and does not block', async ($, on) => {
    const w = world(on, json(EMPTY_LEDGER, 2))
    const out = await bash($, 'git commit -m x')
    expect(w.commands).toEqual(['git commit -m x'])
    expect(out.deny).toBeUndefined()
    expect(w.toasts.some(t => t.includes('/proof') && t.includes('/proof ratchet'))).toBe(true)
    expect(w.toasts.some(t => /obligation/i.test(t))).toBe(false)
  })

  test('a vacuous run is reported as vacuous, never as a pass', async ($, on) => {
    const w = world(on, json(VACUOUS))
    await bash($, 'git commit -m x')
    expect(w.toasts.some(t => /nothing was verified/i.test(t))).toBe(true)
    expect(w.toasts.some(t => /passed/i.test(t))).toBe(false)
  })

  test('nothing in scope is silent', async ($, on) => {
    const w = world(on, json(OUT_OF_SCOPE))
    const out = await bash($, 'git commit -m x')
    expect(w.toasts).toEqual([])
    expect(out.context).toBeUndefined()
  })

  test('a missing cf warns and lets the commit through', async ($, on) => {
    const w = world(on, { deny: 'failed to start: ENOENT: Executable not found in $PATH: "cf"' })
    const out = await bash($, 'git commit -m x')
    expect(w.commands).toEqual(['git commit -m x'])
    expect(out.deny).toBeUndefined()
    expect(w.toasts.some(t => t.includes('uv tool install codeframe-ai'))).toBe(true)
  })

  test('a timeout says it was cut short and lets the commit through', async ($, on) => {
    const w = world(on, { deny: 'proof9: $.process.run(cf) timed out after 120000 ms' })
    await bash($, 'git commit -m x')
    expect(w.commands).toEqual(['git commit -m x'])
    expect(w.toasts.some(t => /cut short/i.test(t))).toBe(true)
  })
})

describe('block mode (opt-in)', () => {
  test('failing obligations deny the commit, naming the requirement', { options: { mode: 'block' } }, async ($, on) => {
    const w = world(on, json(FAILING_RUN, 1))
    const out = await bash($, 'git commit -m x')
    expect(w.commands).toEqual([])
    expect(out.deny).toContain('REQ-0003')
    expect(out.deny).toContain('test_unit_empty_form')
    // The person must not be told the commit went ahead when it was refused.
    expect(w.toasts.some(t => /went ahead/.test(t))).toBe(false)
    expect(w.toasts.some(t => /blocked/.test(t))).toBe(true)
  })

  test('a pass lets the commit run', { options: { mode: 'block' } }, async ($, on) => {
    const w = world(on, json(PASSING_RUN))
    const out = await bash($, 'git commit -m x')
    expect(w.commands).toEqual(['git commit -m x'])
    expect(out.deny).toBeUndefined()
  })

  test('an empty ledger does not block', { options: { mode: 'block' } }, async ($, on) => {
    const w = world(on, json(EMPTY_LEDGER, 2))
    await bash($, 'git commit -m x')
    expect(w.commands).toEqual(['git commit -m x'])
  })

  test('a missing cf fails closed', { options: { mode: 'block' } }, async ($, on) => {
    const w = world(on, { deny: 'ENOENT: Executable not found in $PATH: "cf"' })
    const out = await bash($, 'git commit -m x')
    expect(w.commands).toEqual([])
    expect(out.deny).toContain('uv tool install codeframe-ai')
  })

  test('a timeout fails closed, using the configured limit', { options: { mode: 'block', timeoutSeconds: 5 } }, async ($, on) => {
    const w = world(on, { deny: 'timed out after 5000 ms' })
    const out = await bash($, 'git commit -m x')
    expect(w.calls.find(c => c.argv[2] === 'run')?.timeoutMs).toBe(5_000)
    expect(w.commands).toEqual([])
    expect(out.deny).toMatch(/cut short/i)
  })

  test('unreadable output fails closed', { options: { mode: 'block' } }, async ($, on) => {
    const w = world(on, { exitCode: 1, stdout: 'Traceback ...', stderr: '' })
    const out = await bash($, 'git commit -m x')
    expect(w.commands).toEqual([])
    expect(out.deny).toBeDefined()
  })
})

describe('block mode never denies what is not a commit', () => {
  for (const command of ['echo "done; git commit later"', 'cat > h.sh <<EOF\ngit commit -m x\nEOF', 'git -C commit status']) {
    test(JSON.stringify(command), { options: { mode: 'block' } }, async ($, on) => {
      const w = world(on, json(FAILING_RUN, 1))
      const out = await bash($, command)
      expect(out.deny).toBeUndefined()
      expect(w.calls).toEqual([])
      expect(w.commands).toEqual([command])
    })
  }
})

describe('review fixes', () => {
  test('exit 1 without failed:true is an error, so block mode denies', { options: { mode: 'block' } }, async ($, on) => {
    const w = world(on, json({ detail: 'something else' }, 1))
    const out = await bash($, 'git commit -m x')
    expect(w.commands).toEqual([])
    expect(out.deny).toBeDefined()
  })

  test('exit 1 with failed:false is an error too, so block mode denies', { options: { mode: 'block' } }, async ($, on) => {
    const w = world(on, json(PASSING_RUN, 1))
    const out = await bash($, 'git commit -m x')
    expect(w.commands).toEqual([])
    expect(out.deny).toBeDefined()
  })

  test('a non-empty ledger that verified nothing (exit 2) says so and does not block', { options: { mode: 'block' } }, async ($, on) => {
    const w = world(on, json({ ...EMPTY_LEDGER, empty_reason: 'excluded_by_config', description: 'gates disabled' }, 2))
    await bash($, 'git commit -m x')
    expect(w.commands).toEqual(['git commit -m x'])
    expect(w.toasts.some(t => t.includes('nothing was verified') && t.includes('gates disabled'))).toBe(true)
  })

  test('a nonsense time limit falls back to 120 s', { options: { timeoutSeconds: 0 } }, async ($, on) => {
    const w = world(on, json(PASSING_RUN))
    await bash($, 'git commit -m x')
    expect(w.calls.find(c => c.argv[2] === 'run')?.timeoutMs).toBe(120_000)
  })

  test('a status-line failure after the commit does not lose what Claude is told', async ($, on) => {
    const w = world(on, json(FAILING_RUN, 1), { deny: 'status exploded' })
    const out = await bash($, 'git commit -m x')
    expect(w.commands).toEqual(['git commit -m x'])
    expect((out.context ?? []).join('\n')).toContain('REQ-0003')
  })

  test('a failed run with no failing gate still says why it blocked', { options: { mode: 'block' } }, async ($, on) => {
    const w = world(on, json({ ...FAILING_RUN, requirements: [] }, 1))
    const out = await bash($, 'git commit -m x')
    expect(w.commands).toEqual([])
    expect(out.deny).toContain('cf proof run')
    expect(out.deny).not.toMatch(/commit: \./)
  })

  test('one obligation is singular', async ($, on) => {
    const w = world(on, json(PASSING_RUN), json(listed([false])))
    await bash($, 'git commit -m x')
    expect(w.statuses.at(-1)).toBe('1 requirement · 0 failing')
  })
})

describe('status line', () => {
  test('is cleared when there is no workspace', async ($, on) => {
    const w = world(on, json(EMPTY_LEDGER, 2), { exitCode: 1, stderr: 'Error: No workspace found' })
    await bash($, 'git commit -m x')
    expect(w.statuses.at(-1)).toBeUndefined()
  })

  test('says so when the ledger is empty', async ($, on) => {
    const w = world(on, json(EMPTY_LEDGER, 2), json(listed([])))
    await bash($, 'git commit -m x')
    expect(w.statuses.at(-1)).toBe('nothing checked yet')
  })
})

describe('a requirement that was never proven is not called a regression (#1473 walk)', () => {
  const NEVER_PROVEN = {
    ...FAILING_RUN,
    requirements: [{ ...FAILING_RUN.requirements[0], status_before: 'open', status_after: 'open' }],
  }

  test('the person is told it is not proven yet, not that it broke', async ($, on) => {
    const w = world(on, json(NEVER_PROVEN, 1))
    await bash($, 'git commit -m x')
    const toast = w.toasts.find(t => t.includes('REQ-0003')) ?? ''
    expect(toast).toMatch(/not proven yet: its test does not pass/)
    expect(toast).not.toMatch(/proven to work|breaks|as expected/)
  })

  test('Claude is told the same, and what to do for each kind', async ($, on) => {
    const w = world(on, json(NEVER_PROVEN, 1))
    const out = await bash($, 'git commit -m x')
    const said = (out.context ?? []).join('\n')
    expect(said).toMatch(/not proven yet/)
    expect(said).not.toMatch(/proven to hold/)
    expect(said).toMatch(/still a generated draft, fill it in/i)
    expect(said).not.toMatch(/as expected/)
    expect(w.commands).toEqual(['git commit -m x'])
  })
})

describe('#1473 review: tell the truth about the commit and the mode', () => {
  test('warn mode says the commit went ahead only after it did', async ($, on) => {
    const w = world(on, json(FAILING_RUN, 1), json(STATUS), { commitFails: true })
    await bash($, 'git commit -m x')
    const toast = w.toasts.find(t => t.includes('REQ-0003')) ?? ''
    expect(toast).not.toMatch(/went ahead/)
  })

  test('block mode explains the mode, where to change it, and toasts one short line', { options: { mode: 'block' } }, async ($, on) => {
    const w = world(on, json(FAILING_RUN, 1))
    const out = await bash($, 'git commit -m x')
    expect(out.deny).toMatch(/block mode/)
    expect(out.deny).toMatch(/\/config/)
    const toast = w.toasts.find(t => t.includes('REQ-0003')) ?? ''
    expect(toast.length).toBeLessThan(140)
    expect(toast).not.toEqual(out.deny)
  })
})
