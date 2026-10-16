import { describe, expect, mock, test } from 'claude-code/testing'
import type { On, RenderElement } from 'claude-code'
import type { Engine } from 'claude-code/testing'

type Call = { argv: readonly string[] }
type Answer = { exitCode?: number; stdout?: string; stderr?: string }

const req = (id: string, title: string, failed: boolean, status = 'open') => ({
  id, title, status, source: 'qa',
  obligations: [{ gate: 'unit', status: failed ? 'failed' : 'satisfied' }],
  evidence_rules: [{ test_id: `test_unit_${id.toLowerCase().replace('-', '_')}`, gate: 'unit', must_pass: true }],
})
const ledger = (...requirements: unknown[]): Answer => ({ stdout: JSON.stringify({ requirements }) })
const FAILING = ledger(req('REQ-0003', 'Login 500s on an empty form', true), req('REQ-0004', 'Totals', false, 'satisfied'))
const CLEAN = ledger(req('REQ-0003', 'Login 500s on an empty form', false, 'satisfied'))
const EMPTY = ledger()

const PROPS = {
  hasSurvey: false, isWorking: false, maxRows: 10, bodyColumns: 120,
  scroll: { offset: 0, bodyRows: 10 }, view: {},
}

/** The world beneath the plugin. `lists` answers successive `cf proof list` calls. */
function world(
  on: On, lists: Answer[], store: Record<string, unknown> = {}, opts: { noRepo?: boolean; waiveFails?: boolean } = {},
) {
  const calls: Call[] = []
  const submitted: string[] = []
  const filled: string[] = []
  const toasts: string[] = []
  let n = 0
  on('process.run', (_$, e) => {
    calls.push({ argv: e.argv })
    const a: Answer = e.argv[0] === 'cf' && e.argv[1] === '--version'
      ? { stdout: 'codeframe 0.9.7\n' }
      : e.argv[2] === 'list'
        ? (lists[Math.min(n++, lists.length - 1)] ?? EMPTY)
        : e.argv[2] === 'show'
          ? { stdout: 'REQ-0003: Login 500s on an empty form\n  Evidence (1): unit FAIL' }
          : e.argv[2] === 'ratchet'
            ? { stdout: JSON.stringify({ dry_run: false, locked: { test_add: ['calc.py'] }, req_ids: ['REQ-0001'], already_locked: [], failed: [], skipped: [], unenforceable: [], per_test_scope: true }) }
            : e.argv[2] === 'waive' && opts.waiveFails
              ? { exitCode: 1, stderr: 'Error: Invalid date' }
              : { stdout: '' }
    return { value: { exitCode: a.exitCode ?? 0, stdout: a.stdout ?? '', stderr: a.stderr ?? '', isStdoutTruncated: false, isStderrTruncated: false } }
  })
  on('ui.toast', (_$, e) => {
    toasts.push(e.text)
    return { value: undefined }
  })
  on('ui.status', () => ({ value: undefined }))
  on('session.repo', () => (opts.noRepo ? { value: null } : { value: { root: '/repo', remote: null, internal: false, name: null } }))
  on('session.cwd', () => ({ value: '/elsewhere' }))
  on('command.register', (_$, e) => ({ value: { command: e.name } }))
  on('session.start', (_$, e) => ({ cwd: e.cwd }))
  on('prompt.submit', (_$, e) => {
    submitted.push(e.text)
    return { text: e.text }
  })
  on('prompt.fill', (_$, e) => {
    filled.push(e.text)
    return { isFilled: true }
  })
  // The engine's own band, drawn when the plugin has nothing to show.
  on('ui.render', { component: 'AbovePrompt' }, ($$, e) => {
    const { Box } = $$.ui.resolve(e)
    return h(Box, { key: 'engine-band' }) as RenderElement
  })
  mock.store(on, store)
  const session = mock.session(on)
  return { calls, submitted, filled, toasts, session }
}

const start = ($: Engine) => $.session.start({ cwd: '/repo', surface: 'terminal', isInteractive: true })
const band = ($: Engine) => $.ui.mount({ plugin: 'proof9', surface: 'terminal', component: 'AbovePrompt', props: PROPS })

describe('failing requirement band', () => {
  test('names the failing requirement and its test', async ($, on) => {
    world(on, [FAILING])
    await start($)
    const ui = await band($)
    const text = (await ui.find({ type: 'Text', text: /REQ-0003/ }))?.text ?? ''
    expect(text).toContain('Login 500s on an empty form')
    expect(text).toContain('test_unit_req_0003')
    expect(text).not.toContain('REQ-0004')
  })

  test('Ask Claude to fix queues a prompt naming the failure', async ($, on) => {
    const w = world(on, [FAILING])
    await start($)
    const ui = await band($)
    await ui.press({ key: 'fix' })
    expect(w.submitted.length).toBe(1)
    expect(w.submitted[0]).toContain('REQ-0003')
    expect(w.submitted[0]).toContain('test_unit_req_0003')
    expect(w.submitted[0]).toMatch(/do not weaken or delete/i)
  })

  test('Show evidence appends cf proof show as a notice', async ($, on) => {
    const w = world(on, [FAILING])
    await start($)
    const ui = await band($)
    await ui.press({ key: 'evidence' })
    expect(w.calls.some(c => c.argv.join(' ') === 'cf proof show REQ-0003')).toBe(true)
    expect(JSON.stringify(w.session.appended())).toContain('Evidence (1): unit FAIL')
  })

  test('Waive… asks for a reason and calls cf proof waive, with an optional expiry', async ($, on) => {
    const w = world(on, [FAILING, FAILING, CLEAN])
    await start($)
    const ui = await band($)
    await ui.press({ key: 'waive' })
    await ui.input({ key: 'waive-reason', text: 'flaky on CI until 2099-01-31' })
    expect(w.calls.find(c => c.argv[2] === 'waive')?.argv).toEqual([
      'cf', 'proof', 'waive', 'REQ-0003', '--reason', 'flaky on CI', '--expires', '2099-01-31',
    ])
  })

  test('an empty reason is not submitted', async ($, on) => {
    const w = world(on, [FAILING])
    await start($)
    const ui = await band($)
    await ui.press({ key: 'waive' })
    await ui.input({ key: 'waive-reason', text: '   ' })
    expect(w.calls.some(c => c.argv[2] === 'waive')).toBe(false)
  })

  test('Dismiss hides it for that failure', async ($, on) => {
    world(on, [FAILING])
    await start($)
    const ui = await band($)
    await ui.press({ key: 'dismiss' })
    expect(await ui.find({ type: 'Text', text: /REQ-0003/ })).toBeUndefined()
  })

  test('a passing run clears it', async ($, on) => {
    on('tool.call', { tool: 'Bash' }, () => ({ result: { stdout: '', stderr: '', interrupted: false }, text: '' }))
    world(on, [FAILING, CLEAN])
    await start($)
    const ui = await band($)
    expect(await ui.find({ type: 'Text', text: /REQ-0003/ })).toBeDefined()
    await $.tool.call({ tool: 'Bash', command: 'git commit -m fix' })
    expect(await ui.find({ type: 'Text', text: /REQ-0003/ })).toBeUndefined()
  })
})

describe('empty ledger band', () => {
  test('offers the two ways forward', async ($, on) => {
    world(on, [EMPTY])
    await start($)
    const ui = await band($)
    expect(await ui.find({ type: 'Text', text: /No proof obligations yet/ })).toBeDefined()
  })

  test('Lock in passing tests runs the ratchet and reports it', async ($, on) => {
    const w = world(on, [EMPTY, CLEAN])
    await start($)
    const ui = await band($)
    await ui.press({ key: 'ratchet' })
    expect(w.calls.some(c => c.argv[2] === 'ratchet')).toBe(true)
    expect(JSON.stringify(w.session.appended())).toContain('Locked in 1 passing test')
    expect(await ui.find({ type: 'Text', text: /No proof obligations yet/ })).toBeUndefined()
  })

  test('Capture a bug starts /proof at the prompt', async ($, on) => {
    const w = world(on, [EMPTY])
    await start($)
    const ui = await band($)
    await ui.press({ key: 'capture' })
    expect(w.filled).toEqual(['/proof '])
  })

  test('a dismissal persists for the repository', async ($, on) => {
    const store: Record<string, unknown> = {}
    world(on, [EMPTY], store)
    await start($)
    const ui = await band($)
    await ui.press({ key: 'dismiss-empty' })
    expect(await ui.find({ type: 'Text', text: /No proof obligations yet/ })).toBeUndefined()
  })

  test('is not shown again once dismissed for this repository', async ($, on) => {
    world(on, [EMPTY], { 'emptyHidden:/repo': true })
    await start($)
    const ui = await band($)
    expect(await ui.find({ type: 'Text', text: /No proof obligations yet/ })).toBeUndefined()
  })

  test('nothing shows when the ledger has obligations and none fail', async ($, on) => {
    world(on, [CLEAN])
    await start($)
    const ui = await band($)
    expect(await ui.find({ type: 'Button' })).toBeUndefined()
    expect(await ui.find({ key: 'engine-band' })).toBeDefined()
  })
})

describe('review fixes', () => {
  const bashOk = (on: On) =>
    on('tool.call', { tool: 'Bash' }, () => ({ result: { stdout: '', stderr: '', interrupted: false }, text: '' }))

  test('Claude running cf proof run clears a band whose requirement now passes', async ($, on) => {
    bashOk(on)
    world(on, [FAILING, CLEAN])
    await start($)
    const ui = await band($)
    await $.tool.call({ tool: 'Bash', command: 'uv run pytest -q && cf proof run' })
    expect(await ui.find({ type: 'Text', text: /REQ-0003/ })).toBeUndefined()
  })

  test('an unrelated Bash command does not re-read the ledger', async ($, on) => {
    bashOk(on)
    const w = world(on, [FAILING])
    await start($)
    const before = w.calls.filter(c => c.argv[2] === 'list').length
    await $.tool.call({ tool: 'Bash', command: 'echo cf proof run' })
    expect(w.calls.filter(c => c.argv[2] === 'list').length).toBe(before)
  })

  test('a failed ledger read keeps the band instead of clearing it', async ($, on) => {
    bashOk(on)
    world(on, [FAILING, { exitCode: 1, stderr: 'database is locked' }])
    await start($)
    const ui = await band($)
    await $.tool.call({ tool: 'Bash', command: 'cf proof run' })
    expect(await ui.find({ type: 'Text', text: /REQ-0003/ })).toBeDefined()
  })

  test('a dismissal ends with its failure: a later regression shows again', async ($, on) => {
    bashOk(on)
    world(on, [FAILING, CLEAN, FAILING])
    await start($)
    const ui = await band($)
    await ui.press({ key: 'dismiss' })
    await $.tool.call({ tool: 'Bash', command: 'cf proof run' })
    await $.tool.call({ tool: 'Bash', command: 'cf proof run' })
    expect(await ui.find({ type: 'Text', text: /REQ-0003/ })).toBeDefined()
  })

  test('an empty waiver reason says a reason is required', async ($, on) => {
    const w = world(on, [FAILING])
    await start($)
    const ui = await band($)
    await ui.press({ key: 'waive' })
    await ui.input({ key: 'waive-reason', text: '  ' })
    expect(w.toasts.some(t => /reason is required/i.test(t))).toBe(true)
  })

  test('without a git repo the dismissal is keyed to the directory, not shared', async ($, on) => {
    const store: Record<string, unknown> = { 'emptyHidden:': true }
    world(on, [EMPTY], store, { noRepo: true })
    await start($)
    const ui = await band($)
    expect(await ui.find({ type: 'Text', text: /No proof obligations yet/ })).toBeDefined()
  })
})

test('a waived requirement is an accepted risk: no band even with a failed obligation', async ($, on) => {
  world(on, [ledger(req('REQ-0003', 'Login 500s on an empty form', true, 'waived'))])
  await start($)
  const ui = await band($)
  expect(await ui.find({ type: 'Text', text: /REQ-0003/ })).toBeUndefined()
})

test('a gate with no named test is not presented as a test name', async ($, on) => {
  const noRule = { ...req('REQ-0007', 'Scanner finding', true), evidence_rules: [] }
  const w = world(on, [ledger(noRule)])
  await start($)
  const ui = await band($)
  await ui.press({ key: 'fix' })
  expect(w.submitted[0]).toContain('the unit gate (no named test)')
})

test('a failed waive keeps the reason being typed', async ($, on) => {
  const w = world(on, [FAILING], {}, { waiveFails: true })
  await start($)
  const ui = await band($)
  await ui.press({ key: 'waive' })
  await ui.input({ key: 'waive-reason', text: 'later until 2099-02-30' })
  expect(w.calls.some(c => c.argv[2] === 'waive')).toBe(true)
  expect(await ui.find({ key: 'waive-reason' })).toBeDefined()
})

test('a waiver that has expired no longer hides a failure (read-only, like the merge gate)', async ($, on) => {
  const lapsed = { ...req('REQ-0003', 'Login 500s on an empty form', true, 'waived'), waiver: { reason: 'later', expired: true } }
  world(on, [ledger(lapsed)])
  await start($)
  const ui = await band($)
  expect(await ui.find({ type: 'Text', text: /REQ-0003/ })).toBeDefined()
})
