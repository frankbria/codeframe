import { describe, expect, test } from 'claude-code/testing'
import type { CommandRunResult, On } from 'claude-code'
import type { Engine } from 'claude-code/testing'

type Call = { argv: readonly string[]; env?: Record<string, string>; timeoutMs?: number }
type Answer = { exitCode?: number; stdout?: string; stderr?: string } | 'missing'

const CAPTURED = {
  requirement: {
    id: 'REQ-0003',
    title: 'Login 500s on empty password',
    obligations: [{ gate: 'unit', status: 'pending' }, { gate: 'sec', status: 'pending' }],
    scope: { files: ['.'], routes: [], apis: [], components: [], tags: [] },
  },
  stubs: { unit: 'tests/proof/REQ-0003/draft_test_unit.py', sec: 'tests/proof/REQ-0003/draft_test_sec.py' },
  workspace_created: true,
  warnings: [],
}

/** The world beneath the plugin: `cf` answered by `answer`, a repo at /repo, toasts recorded. */
function world(
  on: On,
  answer: (argv: readonly string[]) => Answer,
  opts: { selection?: string; repo?: boolean | 'throws'; selectionThrows?: boolean } = {},
) {
  const calls: Call[] = []
  const toasts: string[] = []
  const opened: string[] = []
  on('process.run', (_$, e) => {
    calls.push({ argv: e.argv, env: e.init?.env, timeoutMs: e.init?.timeoutMs })
    const a = answer(e.argv)
    if (a === 'missing') return { deny: 'failed to start: ENOENT: Executable not found in $PATH: "cf"' }
    return {
      value: {
        exitCode: a.exitCode ?? 0,
        stdout: a.stdout ?? '',
        stderr: a.stderr ?? '',
        isStdoutTruncated: false,
        isStderrTruncated: false,
      },
    }
  })
  // Hooks under a `$` noun call answer `{ value }`.
  on('session.repo', () => {
    if (opts.repo === 'throws') throw new Error('git unavailable')
    return {
      value: opts.repo === false ? null : { root: '/repo', remote: null, internal: false, name: null },
    }
  })
  on('ui.selection', () => {
    if (opts.selectionThrows) throw new Error('no surface')
    return { value: opts.selection === undefined ? undefined : { text: opts.selection } }
  })
  on('ui.toast', (_$, e) => {
    toasts.push(e.text)
    return { value: undefined }
  })
  on('ui.open', (_$, e) => {
    opened.push(e.id)
    return { value: { isPlaced: true } }
  })
  on('ui.status', () => ({ value: undefined }))
  return { calls, toasts, opened }
}

/** `/proof <args>` typed at the composer of a fullscreen terminal. */
const proof = ($: Engine, args: string): Promise<CommandRunResult> =>
  $.command.run({
    command: 'proof',
    args,
    origin: { kind: 'composer' },
    presentation: { isFullscreen: true, columns: 120 },
  })

const capture = (argv: readonly string[]): Answer =>
  argv[2] === 'capture' ? { stdout: JSON.stringify(CAPTURED) } : { stdout: 'codeframe 0.9.7\n' }

describe('/proof <text>', () => {
  test('captures through cf with the text as argv and reports the requirement', async ($, on) => {
    const w = world(on, capture)
    const out = await proof($, 'Login 500s on empty password\nSteps: submit the form')

    const call = w.calls.find(c => c.argv[2] === 'capture')
    expect(call?.argv).toEqual([
      'cf', 'proof', 'capture', '--json',
      '--title', 'Login 500s on empty password',
      '--description', 'Login 500s on empty password\nSteps: submit the form',
      '--where', '/repo',
      '--severity', 'medium',
      '--source', 'qa',
    ])
    expect(call?.env).toEqual({ CODEFRAME_CLIENT: 'proof9' })
    expect(out.text).toContain('REQ-0003')
    expect(out.text).toContain('Login 500s on empty password')
    expect(out.text).toContain('unit, sec')
    expect(out.text).toContain('tests/proof/REQ-0003/draft_test_unit.py')
    expect(out.text).toContain('Created .codeframe/')
  })

  test('a long first line is cut for the title, never for the description', async ($, on) => {
    const w = world(on, capture)
    const long = 'x'.repeat(200)
    await proof($, long)
    const argv = w.calls.find(c => c.argv[2] === 'capture')?.argv ?? []
    expect(argv[argv.indexOf('--title') + 1]?.length).toBe(80)
    expect(argv[argv.indexOf('--description') + 1]).toBe(long)
  })

  test('shell metacharacters stay one argument', async ($, on) => {
    const w = world(on, capture)
    const hostile = '"; rm -rf ~ #`whoami` $(id)'
    await proof($, hostile)
    const argv = w.calls.find(c => c.argv[2] === 'capture')?.argv ?? []
    expect(argv[argv.indexOf('--description') + 1]).toBe(hostile)
  })

  test('outside a git repository the scope falls back to "." and cf decides', async ($, on) => {
    const w = world(on, capture, { repo: false })
    await proof($, 'bug')
    const argv = w.calls.find(c => c.argv[2] === 'capture')?.argv ?? []
    expect(argv[argv.indexOf('--where') + 1]).toBe('.')
  })

  test('a title is cut by character, not UTF-16 unit, and trimmed', async ($, on) => {
    const w = world(on, capture)
    await proof($, '🐛'.repeat(79) + ' ' + 'x'.repeat(50))
    const argv = w.calls.find(c => c.argv[2] === 'capture')?.argv ?? []
    expect(argv[argv.indexOf('--title') + 1]).toBe('🐛'.repeat(79))
  })

  test('words after "ratchet" are a description, not the ratchet', async ($, on) => {
    const w = world(on, capture)
    await proof($, 'ratchet wrench test fails on CI')
    expect(w.calls.some(c => c.argv[2] === 'capture')).toBe(true)
    expect(w.calls.some(c => c.argv[2] === 'ratchet')).toBe(false)
  })

  test('a repo lookup that throws falls back to "."', async ($, on) => {
    const w = world(on, capture, { repo: 'throws' })
    const out = await proof($, 'bug')
    const argv = w.calls.find(c => c.argv[2] === 'capture')?.argv ?? []
    expect(argv[argv.indexOf('--where') + 1]).toBe('.')
    expect(out.text).toContain('REQ-0003')
  })

  test('a refused capture shows what cf said', async ($, on) => {
    world(on, () => ({ exitCode: 1, stderr: 'Error: not inside a git repository' }))
    const out = await proof($, 'bug')
    expect(out.text).toContain('not inside a git repository')
  })
})

describe('/proof with no text', () => {
  test('uses the transcript selection as the description', async ($, on) => {
    const trace = 'Traceback (most recent call last):\n  File "app.py", line 3\nKeyError: user'
    const w = world(on, capture, { selection: trace })
    await proof($, '')
    const argv = w.calls.find(c => c.argv[2] === 'capture')?.argv ?? []
    expect(argv[argv.indexOf('--description') + 1]).toBe(trace)
    expect(argv[argv.indexOf('--title') + 1]).toBe('Traceback (most recent call last):')
  })

  test('typed text wins over a selection', async ($, on) => {
    const w = world(on, capture, { selection: 'selected trace' })
    await proof($, 'typed words')
    const argv = w.calls.find(c => c.argv[2] === 'capture')?.argv ?? []
    expect(argv[argv.indexOf('--description') + 1]).toBe('typed words')
  })

  // Since #1491, no text and no selection opens the ledger pane (it shows the usage).
  test('a selection lookup that throws is treated as no selection', async ($, on) => {
    const w = world(on, capture, { selectionThrows: true })
    await proof($, '')
    expect(w.calls.some(c => c.argv[2] === 'capture')).toBe(false)
    expect(w.opened).toEqual(['proof9'])
  })

  test('with no selection either, opens the ledger pane and captures nothing', async ($, on) => {
    const w = world(on, capture)
    await proof($, '   ')
    expect(w.calls.some(c => c.argv[2] === 'capture')).toBe(false)
    expect(w.opened).toEqual(['proof9'])
  })
})

describe('/proof ratchet', () => {
  const RATCHETED = {
    dry_run: false, workspace_created: false,
    locked: { test_add: ['calc.py'], test_sub: ['calc.py'] }, req_ids: ['REQ-0001', 'REQ-0002'],
    already_locked: ['test_old'], failed: ['test_broken'], skipped: [], unenforceable: [],
    per_test_scope: false,
  }

  test('runs the ratchet with a long timeout and summarises it', async ($, on) => {
    const w = world(on, () => ({ stdout: JSON.stringify(RATCHETED) }))
    const out = await proof($, 'ratchet')
    const call = w.calls.find(c => c.argv[2] === 'ratchet')
    expect(call?.argv).toEqual(['cf', 'proof', 'ratchet', '--json'])
    expect(call?.timeoutMs).toBe(600_000)
    expect(w.toasts.some(t => t.includes('test suite'))).toBe(true)
    expect(out.text).toContain('Locked in 2 passing tests')
    expect(out.text).toContain('1 already locked')
    expect(out.text).toContain('1 failed')
    expect(out.text).toContain('pytest-cov')
    expect(out.text).toContain('cf proof run --full')
  })

  test('--dry-run is passed through and reported as such', async ($, on) => {
    const w = world(on, () => ({ stdout: JSON.stringify({ ...RATCHETED, dry_run: true }) }))
    const out = await proof($, 'ratchet --dry-run')
    expect(w.calls.find(c => c.argv[2] === 'ratchet')?.argv).toEqual(['cf', 'proof', 'ratchet', '--json', '--dry-run'])
    expect(out.text).toContain('Would lock in 2')
  })

  test('--path is passed through with its glob', async ($, on) => {
    const w = world(on, () => ({ stdout: JSON.stringify(RATCHETED) }))
    await proof($, "ratchet --path tests/unit/* --dry-run")
    expect(w.calls.find(c => c.argv[2] === 'ratchet')?.argv).toEqual([
      'cf', 'proof', 'ratchet', '--json', '--path', 'tests/unit/*', '--dry-run',
    ])
  })

  test('an unknown ratchet flag shows usage and creates nothing', async ($, on) => {
    const w = world(on, capture)
    for (const args of ['ratchet --dryrun', 'ratchet --path', 'ratchet --dry-run extra', 'ratchet --path --dry-run']) {
      const out = await proof($, args)
      expect(out.text).toContain('/proof ratchet')
    }
    expect(w.calls.filter(c => c.argv[1] === 'proof')).toEqual([])
  })

  test('a dry run with nothing new to lock does not say "0"', async ($, on) => {
    world(on, () => ({
      stdout: JSON.stringify({ ...RATCHETED, dry_run: true, locked: {}, req_ids: [] }),
    }))
    const out = await proof($, 'ratchet --dry-run')
    expect(out.text).toContain('already locked in')
    expect(out.text).not.toContain('Would lock in 0')
  })

  test('exit 2 with no document (an old cf rejecting --json) shows the error', async ($, on) => {
    world(on, () => ({ exitCode: 2, stderr: 'No such option: --json' }))
    const out = await proof($, 'ratchet')
    expect(out.text).toContain('No such option: --json')
    expect(out.text).not.toContain('Nothing to lock')
  })

  test('a timeout is reported as a timeout, without the install hint', async ($, on) => {
    // `{ deny }` is how a hook beneath the plugin makes its call reject.
    on('process.run', () => ({ deny: 'proof9: $.process.run(cf) timed out after 600000 ms' }))
    on('ui.toast', () => ({ value: undefined }))
    const out = await proof($, 'ratchet')
    expect(out.text).toContain('timed out')
    expect(out.text).not.toContain('uv tool install')
  })

  test('nothing to lock (exit 2) says so', async ($, on) => {
    world(on, () => ({
      exitCode: 2,
      stdout: JSON.stringify({ ...RATCHETED, locked: {}, req_ids: [], already_locked: [] }),
    }))
    const out = await proof($, 'ratchet')
    expect(out.text).toContain('Nothing to lock')
  })

  test('a suite that cannot run (exit 1) shows the error', async ($, on) => {
    world(on, () => ({ exitCode: 1, stderr: 'Error: pytest is not in the project' }))
    const out = await proof($, 'ratchet')
    expect(out.text).toContain('pytest is not in the project')
  })
})

describe('when cf is missing or too old', () => {
  test('/proof gives the install command', async ($, on) => {
    on('process.run', () => ({ deny: 'ENOENT: Executable not found in $PATH: "cf"' }))
    on('session.repo', () => ({ value: null }))
    const out = await proof($, 'bug')
    expect(out.text).toContain('uv tool install codeframe-ai')
  })

  test('session start warns once with the install command', async ($, on) => {
    const w = world(on, () => 'missing')
    on('session.start', (_$, e) => ({ cwd: e.cwd }))
    on('command.register', (_$, e) => ({ value: { command: e.name } }))
    await $.session.start({ cwd: '/repo', surface: 'terminal', isInteractive: true })
    expect(w.toasts.filter(t => t.includes('uv tool install codeframe-ai')).length).toBe(1)
  })

  test('session start warns about an old cf with the upgrade command', async ($, on) => {
    const w = world(on, () => ({ stdout: 'codeframe 0.9.5\n' }))
    on('session.start', (_$, e) => ({ cwd: e.cwd }))
    on('command.register', (_$, e) => ({ value: { command: e.name } }))
    await $.session.start({ cwd: '/repo', surface: 'terminal', isInteractive: true })
    expect(w.toasts.some(t => t.includes('0.9.5') && t.includes('uv tool upgrade codeframe-ai'))).toBe(true)
  })

  test('a failing cf --version warns instead of staying silent', async ($, on) => {
    const w = world(on, () => ({ exitCode: 1, stderr: 'Traceback ...' }))
    on('session.start', (_$, e) => ({ cwd: e.cwd }))
    on('command.register', (_$, e) => ({ value: { command: e.name } }))
    await $.session.start({ cwd: '/repo', surface: 'terminal', isInteractive: true })
    expect(w.toasts.some(t => t.includes('cf --version'))).toBe(true)
    expect(w.calls[0]?.timeoutMs).toBe(10_000)
  })

  test('a current cf starts silently and registers /proof', async ($, on) => {
    const w = world(on, () => ({ stdout: 'codeframe 0.10.0\n' }))
    const registered: string[] = []
    on('session.start', (_$, e) => ({ cwd: e.cwd }))
    on('command.register', (_$, e) => {
      registered.push(e.name)
      return { value: { command: e.name } }
    })
    await $.session.start({ cwd: '/repo', surface: 'terminal', isInteractive: true })
    expect(w.toasts).toEqual([])
    expect(registered).toEqual(['proof'])
  })
})
